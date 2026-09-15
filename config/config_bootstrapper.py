"""
config_boostrapper.py 

Herramienta para generar una versión inicial (provisional) de
'config/<origin>_config.py' a partir de una muestra de logs crudos de
un origen desconocido.

Infiere:
  - TIMESTAMP_PATTERNS / TIMESTAMP_RE: probando un catálogo de formatos
    de timestamp conocidos (reutilizados de configs existentes) contra
    una muestra de líneas, y quedándose con el que mejor cobertura dé.
  - Nivel de log (LEVEL_MAPPING): detecta palabras típicas (INFO,
    ERROR, WARN...) cerca del timestamp.
  - PATTERNS["<origin>_event"]: regex de línea con grupos nombrados
    'timestamp' y 'level', dejando 'message' implícito (todo lo que
    sigue).
  - DRAIN_CONFIG: ejecuta Drain3 con el perfil 'very_permissive' sobre
    los mensajes ya extraídos, solo para dar una primera estimación de
    cuántos clusters salen (a validar con benchmark real después).

Uso:
    python parsing/config_bootstrapper.py \
        --origin nuevo_origen \
        --sample-logs "example_logs_raw/nuevo_origen/*.log" \
        --sample-size 500 \
        --output-config config/nuevo_origen_config.py
"""
import argparse
import glob
import json
import os
import random
import re
import sys
from collections import Counter
from typing import Dict, List, Optional, Tuple
import textwrap

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.general_config import TIMESTAMP_PATTERNS as GENERAL_TIMESTAMP_PATTERNS


# --- Catálogo de timestamps conocidos, extraídos de configs existentes ---
KNOWN_TIMESTAMP_PATTERNS: Dict[str, str] = {
    f"general_pattern_{i:02d}": pattern
    for i, pattern in enumerate(GENERAL_TIMESTAMP_PATTERNS)
}

# --- Palabras de nivel de log conocidas (reutilizadas de LEVEL_MAPPING típico) ---
KNOWN_LEVEL_WORDS = [
    "SEVERE", "ERROR", "FATAL", "CRITICAL",
    "MANDATORY", "WARNING", "WARN",
    "APP", "INFO", "NOTICE",
    "DEBUG", "TRACE", "VERBOSE",
]

DEFAULT_LEVEL_MAPPING = {
    "SEVERE": "ERROR", "ERROR": "ERROR", "FATAL": "ERROR", "CRITICAL": "ERROR",
    "MANDATORY": "WARN", "WARNING": "WARN", "WARN": "WARN",
    "APP": "INFO", "INFO": "INFO", "NOTICE": "INFO",
    "DEBUG": "DEBUG", "TRACE": "DEBUG", "VERBOSE": "DEBUG",
}


def load_sample_lines(sample_glob: str, sample_size: int) -> List[str]:
    """
    Carga una muestra aleatoria de líneas no vacías desde ficheros .log.
    
    Args:
        sample_glob (str): Patrón glob para localizar los ficheros de muestra.
        sample_size (int): Número máximo de líneas a muestrear.

    Returns:    
        List[str]: Lista de líneas no vacías muestreadas.
    """
    files = glob.glob(sample_glob, recursive=True)
    if not files:
        raise FileNotFoundError(f"No se encontraron ficheros con el patrón '{sample_glob}'")

    all_lines: List[str] = []
    for path in files:
        with open(path, encoding="utf-8", errors="ignore") as f:
            all_lines.extend(line.rstrip("\n") for line in f if line.strip())

    if not all_lines:
        raise ValueError(f"Los ficheros encontrados ({len(files)}) no contienen líneas no vacías")

    if len(all_lines) > sample_size:
        all_lines = random.sample(all_lines, sample_size)

    print(f"📄 {len(files)} fichero(s) encontrados, {len(all_lines)} línea(s) en la muestra")
    return all_lines


def detect_best_timestamp_pattern(lines: List[str], min_coverage: float = 0.66) -> Tuple[str, str, float]:
    """
    Prueba cada patrón del catálogo KNOWN_TIMESTAMP_PATTERNS contra la
    muestra y devuelve (nombre, regex, cobertura) del que más líneas
    matchea al inicio de línea.

    Args:
        lines (List[str]): Lista de líneas de log a analizar.
    
    Returns:
        Tuple[str, str, float]: (nombre del patrón, regex del patrón, cobertura como float entre 0 y 1)
    """
    best_name, best_pattern, best_coverage = None, None, 0.0

    for name, pattern in KNOWN_TIMESTAMP_PATTERNS.items():
        compiled = re.compile(pattern)
        matches = sum(1 for line in lines if compiled.match(line))
        coverage = matches / len(lines) if lines else 0.0
        print(f"  · {name}: {matches}/{len(lines)} líneas ({coverage*100:.1f}%)")
        if coverage > best_coverage:
            best_name, best_pattern, best_coverage = name, pattern, coverage

    if best_coverage == 0.0:
        raise ValueError(
            "Ningún patrón de timestamp conocido matchea la muestra. "
            "Añade un nuevo patrón a KNOWN_TIMESTAMP_PATTERNS en "
            "config_bootstrapper.py con el formato real de este origen."
        )

    if best_coverage < min_coverage:
        raise ValueError(
            f"El mejor patrón encontrado ('{best_name}') solo cubre "
            f"{best_coverage*100:.1f}% de la muestra (< {min_coverage*100:.0f}% "
            f"mínimo exigido). Es probable que el catálogo no tenga el "
            f"formato real de este origen — revisa manualmente 2-3 líneas "
            f"de muestra y añade el patrón correcto a "
            f"KNOWN_TIMESTAMP_PATTERNS antes de reintentar."
        )

    return best_name, best_pattern, best_coverage


def detect_level_word(lines: List[str], timestamp_pattern: str) -> Optional[str]:
    """
    Busca, en el texto que sigue al timestamp, la primera palabra de
    KNOWN_LEVEL_WORDS que aparezca con frecuencia razonable. Devuelve
    None si no se detecta un nivel de log claro (algunos orígenes no
    lo tienen).

    Args:
        lines (List[str]): Lista de líneas de log a analizar.
        timestamp_pattern (str): Regex del patrón de timestamp detectado.

    Returns:
        Optional[str]: La palabra de nivel detectada o None si no se detecta.
    """
    ts_re = re.compile(timestamp_pattern)
    level_counter = Counter()

    for line in lines:
        m = ts_re.search(line)
        if not m:
            continue
        remainder = line[m.end():m.end() + 60]  # ventana corta tras el timestamp
        for word in KNOWN_LEVEL_WORDS:
            if re.search(rf"\b{word}\b", remainder):
                level_counter[word] += 1
                break

    if not level_counter:
        return None

    total_matches = sum(level_counter.values())
    coverage = total_matches / len(lines) if lines else 0
    print(f"  · Niveles detectados: {dict(level_counter)} (cobertura: {coverage*100:.1f}%)")
    return "detected" if coverage > 0.3 else None


def build_line_pattern(origin: str, timestamp_pattern: str, has_level: bool) -> str:
    """
    Construye el regex de PATTERNS["<origin>_event"] con grupos
    nombrados 'timestamp' y (opcionalmente) 'level'.

    Args:
        origin (str): Nombre del origen de logs.
        timestamp_pattern (str): Regex del patrón de timestamp detectado.
        has_level (bool): Indica si se detectó un nivel de log.

    Returns:
        str: Regex completo para la línea de log.
    """
    if has_level:
        level_group = r"\s*\[?(?P<level>" + "|".join(KNOWN_LEVEL_WORDS) + r")\]?"
        return rf'(?P<timestamp>{timestamp_pattern}){level_group}\s*'
    # Patrón greedy
    return rf'(?P<timestamp>{timestamp_pattern})\s*'


def run_quick_drain3_estimate(lines: List[str], line_pattern: str) -> Tuple[Optional[int], Optional[list]]:
    """
    Extrae el mensaje (lo que queda tras aplicar line_pattern) y
    ejecuta una pasada rápida de Drain3 (perfil 'very_permissive') solo
    para dar una cifra orientativa de nº de clusters. No falla el
    bootstrapper si Drain3 no está disponible/importable.

    Devuelve (num_clusters, clusters) donde 'clusters' es la lista de
    objetos Cluster de drain3 (o None si no se pudo ejecutar), para
    poder extraer después el top de clusters más repetitivos.

    Args:
        lines (List[str]): Lista de líneas de log a analizar.
        line_pattern (str): Regex de línea con grupos nombrados 'timestamp' y 'level'.
    
    Returns:
        Tuple[Optional[int], Optional[list]]: (número de clusters, lista de clusters)
    """
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "drain"))
        from drain3 import TemplateMiner
        from drain3.template_miner_config import TemplateMinerConfig
    except ImportError:
        print("  ⚠️  No se pudo importar drain3, se omite la estimación de clusters.")
        return None, None

    pattern_re = re.compile(line_pattern)
    messages = []
    for line in lines:
        m = pattern_re.search(line)
        messages.append(line[m.end():] if m else line)

    config = TemplateMinerConfig()
    config.drain_sim_th = 0.5
    config.drain_depth = 4
    config.drain_max_children = 100
    miner = TemplateMiner(config=config)

    for msg in messages:
        miner.add_log_message(msg)

    clusters = list(miner.drain.clusters)
    num_clusters = len(clusters)
    print(f"  · Drain3 (config provisional): {num_clusters} clusters sobre {len(messages)} mensajes")
    return num_clusters, clusters


def save_top_clusters(origin: str, clusters: list, output_dir: Optional[str] = None,
                       top_n: int = 10) -> Optional[str]:
    """
    Ordena los clusters de Drain3 por nº de ocurrencias (size) y guarda
    los 'top_n' más repetitivos en '<output_dir>/top_clusters.json',
    para poder revisar a mano si hay patrones claros a extraer con
    EXTRACTORS o líneas de ruido a añadir a IGNORE_PATTERNS.

    'output_dir' por defecto es una carpeta con el nombre del origen
    (ej. 'nuevo_origen/'), creada si no existe.

    Args:
        origin (str): Nombre del origen de logs.
        clusters (list): Lista de clusters de Drain3.
        output_dir (Optional[str]): Directorio donde guardar el JSON (por defecto, 'origin/').
        top_n (int): Número de clusters más repetitivos a guardar.

    Returns:
        Optional[str]: Ruta del fichero JSON guardado, o None si no se guardó nada.
    """
    if not clusters:
        print("  ⚠️  No hay clusters disponibles, se omite el top de clusters")
        return None

    output_dir = output_dir or origin
    os.makedirs(output_dir, exist_ok=True)

    sorted_clusters = sorted(clusters, key=lambda c: c.size, reverse=True)
    top_clusters = sorted_clusters[:top_n]

    total_messages = sum(c.size for c in clusters)
    top_data = [
        {
            "rank": i + 1,
            "cluster_id": c.cluster_id,
            "size": c.size,
            "percentage": round(c.size / total_messages * 100, 2) if total_messages else 0.0,
            "template": c.get_template(),
        }
        for i, c in enumerate(top_clusters)
    ]

    output_path = os.path.join(output_dir, "top_clusters.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump({"origin": origin, "total_clusters": len(clusters),
                    "total_messages": total_messages, "top_clusters": top_data},
                   f, indent=2, ensure_ascii=False)

    print(f"\n🏆 TOP {len(top_clusters)} CLUSTERS MÁS REPETITIVOS")
    print(f"{'='*70}")
    for entry in top_data:
        print(f"  #{entry['rank']:2d} | {entry['size']:5d} msgs ({entry['percentage']:5.2f}%) | "
              f"{entry['template'][:80]}")
    print(f"{'='*70}")
    print(f"💾 Guardado en: {output_path}")

    return output_path

def register_origin_in_log_types_config(origin: str, log_types_config_path: str = "config/log_types_config.py") -> bool:
    """
    Añade el nuevo origen a 'config/log_types_config.py', el registro
    central de orígenes conocidos por el sistema.

    Se inserta la entrada '"<origin>": "<origin>_config"' justo antes
    del cierre del dict. 

    Args:
        origin (str): Nombre del nuevo origen de logs.
        log_types_config_path (str): Ruta al fichero log_types_config.py.

    Returns:
        bool: True si se añadió o ya estaba presente, False si hubo un
              problema y no se pudo añadir automáticamente.

    Nota:
        Si el origen ya está presente, no se duplica.
        Si el fichero no existe o no tiene el formato esperado, se informa
        y NO se falla el bootstrapper (la config del origen ya se generó
        correctamente en su propio fichero).
    """
    if not os.path.exists(log_types_config_path):
        print(f"  ⚠️  No existe '{log_types_config_path}', no se ha podido registrar "
              f"el origen automáticamente. Añádelo a mano.")
        return False

    with open(log_types_config_path, encoding="utf-8") as f:
        content = f.read()

    if re.search(rf'^\s*["\']{re.escape(origin)}["\']\s*:', content, re.MULTILINE):
        print(f"  ℹ️  El origen '{origin}' ya está presente en '{log_types_config_path}'")
        return True

    match = re.search(r'(LOG_TYPES\s*=\s*\{)(.*?)(\n\s*\})', content, re.DOTALL)
    if not match:
        print(f"  ⚠️  No se encontró un dict 'LOG_TYPES = {{...}}' en "
              f"'{log_types_config_path}'. Añade '{origin}' manualmente.")
        return False

    prefix, body, suffix = match.groups()
    new_entry = f'    "{origin}": "{origin}_config",\n'
    new_body = body.rstrip() + "\n" + new_entry.rstrip("\n")
    new_content = content[:match.start()] + prefix + new_body + suffix + content[match.end():]

    with open(log_types_config_path, "w", encoding="utf-8") as f:
        f.write(new_content)

    print(f"  ✅ Origen '{origin}': '{origin}_config' añadido a '{log_types_config_path}'")
    return True

def generate_config_file(
    origin: str,
    timestamp_pattern: str,
    has_level: bool,
    line_pattern: str,
    num_clusters_estimate: Optional[int],
    output_path: str,
) -> None:
    """
    Escribe config/<origin>_config.py con la estructura estándar del proyecto.
    
    Args:
        origin (str): Nombre del origen de logs.
        timestamp_pattern (str): Regex del patrón de timestamp detectado.
        has_level (bool): Indica si se detectó un nivel de log.
        line_pattern (str): Regex completo para la línea de log.
        num_clusters_estimate (Optional[int]): Estimación del nº de clusters Drain3.
        output_path (str): Ruta donde guardar el fichero de config generado.

    Returns:
        None
    """
    level_mapping_block = (
        "LEVEL_MAPPING = " + repr(DEFAULT_LEVEL_MAPPING)
        if has_level else
        "# LEVEL_MAPPING: no se detectó un nivel de log claro en la muestra.\n"
        "# Si este origen SÍ tiene niveles, añádelo manualmente:\n"
        "# LEVEL_MAPPING = {\"ERROR\": \"ERROR\", \"WARN\": \"WARN\", \"INFO\": \"INFO\", \"DEBUG\": \"DEBUG\"}"
    )

    _LEVEL_MAPPING_PLACEHOLDER = "__LEVEL_MAPPING_BLOCK__"

    content = textwrap.dedent(f'''\
    """
    Config PROVISIONAL generada automáticamente por config_bootstrapper.py
    para el origen '{origin}'.

    ⚠️  REVISAR ANTES DE USAR EN PRODUCCIÓN:
    - FILENAME_PATTERNS: ajustar al patrón real de nombres de fichero.
    - EXTRACTORS: vacío, añadir los campos de negocio a extraer.
    - IGNORE_PATTERNS: vacío, añadir líneas de ruido a descartar.
    - DRAIN_CONFIG: estimado con perfil 'very_permissive', validar con
        'drain_benchmarking_unified.py parsed3 --origin {origin} --quick'
        tras generar los parquet parseados.

    Nº de clusters Drain3 estimado sobre la muestra: {num_clusters_estimate if num_clusters_estimate is not None else 'N/A'}
    """

    LOG_TYPE = "{origin}"
    MULTILINE = True
    DRAIN_CONFIG = "very_permissive"

    FILENAME_PATTERNS = [
        r'^{origin}_\\d+',
        r'^{origin}[\\._-]',
        r'^{origin}',
        r'.*[_-]{origin}[_-].*',
    ]

    TIMESTAMP_PATTERNS = [
        r"{timestamp_pattern}",
    ]

    TIMESTAMP_RE = r"{timestamp_pattern}"

    PATTERNS = {{
        "{origin}_event": (
            r'{line_pattern}'
        ),
    }}

    EXTRACTORS = [
        # TODO: añadir extractores de negocio específicos de '{origin}'
        # Ejemplo:
        # {{
        #     "anchor": "Job",
        #     "extractor": "job_number",
        #     "regex": r"jobNumber['\\"]?\\s*[:=]\\s*['\\"]?(?P<job_num>\\d+)"
        # }},
    ]

    IGNORE_PATTERNS = [
        # TODO: añadir líneas de ruido a ignorar, ej:
        # r'AIS Version:.*',
    ]

    {_LEVEL_MAPPING_PLACEHOLDER}''')

    content = content.replace(_LEVEL_MAPPING_PLACEHOLDER, level_mapping_block)

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"\n✅ Config provisional generada en: {output_path}")


def bootstrap_config(origin: str, sample_glob: str, sample_size: int,
                      output_path: str, top_clusters_n: int = 10, 
                      log_types_config_path: str = "config/log_types_config.py") -> str:
    """
    Genera config/<origin>_config.py a partir de una muestra de logs crudos.
    
    Args:
        origin (str): Nombre del origen de logs.
        sample_glob (str): Patrón glob para localizar los ficheros de muestra.
        sample_size (int): Número máximo de líneas a muestrear.
        output_path (str): Ruta donde guardar el fichero de config generado.
        top_clusters_n (int): Nº de clusters más repetitivos a guardar en JSON.
        log_types_config_path (str): Ruta al fichero log_types_config.py.

    Returns:
        str: Ruta del fichero de config generado.
    """
    print(f"\n{'='*70}")
    print(f"🔍 Analizando muestra de logs para origen desconocido: '{origin}'")
    print(f"{'='*70}\n")

    lines = load_sample_lines(sample_glob, sample_size)

    print(f"\n📅 Probando catálogo de timestamps conocidos...")
    ts_name, ts_pattern, ts_coverage = detect_best_timestamp_pattern(lines)
    print(f"\n✓ Mejor timestamp: '{ts_name}' ({ts_coverage*100:.1f}% cobertura)")

    print(f"\n🏷️  Buscando nivel de log...")
    level_result = detect_level_word(lines, ts_pattern)
    has_level = level_result is not None
    print(f"✓ Nivel de log {'detectado' if has_level else 'NO detectado'}")

    line_pattern = build_line_pattern(origin, ts_pattern, has_level)
    print(f"\n🧩 Patrón de línea propuesto:\n  {line_pattern}")

    print(f"\n🌀 Estimando clusters con Drain3 (perfil provisional)...")
    num_clusters, clusters = run_quick_drain3_estimate(lines, line_pattern)

    # --- Top 10 clusters más repetitivos, guardados junto a los logs de muestra ---
    top_clusters_path = None
    if clusters:
        sample_dir = os.path.dirname(sample_glob) or "."
        top_clusters_path = save_top_clusters(origin, clusters, output_dir=sample_dir, top_n=top_clusters_n)

    print(f"\n{'='*70}")
    print(f"📋 RESUMEN")
    print(f"{'='*70}")
    print(f"  Timestamp:        {ts_name} (cobertura {ts_coverage*100:.1f}%)")
    print(f"  Nivel de log:     {'sí' if has_level else 'no detectado'}")
    print(f"  Clusters Drain3:  {num_clusters if num_clusters is not None else 'N/A'}")
    print(f"  Top clusters:     {top_clusters_path or 'N/A'}")
    print(f"  Fichero destino:  {output_path}")
    print(f"{'='*70}")

    generate_config_file(
        origin=origin,
        timestamp_pattern=ts_pattern,
        has_level=has_level,
        line_pattern=line_pattern,
        num_clusters_estimate=num_clusters,
        output_path=output_path,
    )

    print(f"\n📝 Registrando origen en log_types_config.py...")
    register_origin_in_log_types_config(origin, log_types_config_path)

    return output_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Genera una config provisional para un origen de logs desconocido"
    )
    parser.add_argument("--origin", type=str, required=True,
                         help="Nombre del nuevo origen (ej: 'nuevo_origen')")
    parser.add_argument("--sample-logs", type=str, required=True,
                         help="Patrón glob a los ficheros .log de muestra "
                              "(ej: 'example_logs_raw/nuevo_origen/*.log')")
    parser.add_argument("--sample-size", type=int, default=500,
                         help="Nº máximo de líneas a muestrear (default: 500)")
    parser.add_argument("--output-config", type=str, default=None,
                         help="Ruta de salida (default: config/<origin>_config.py)")
    parser.add_argument("--top-clusters", type=int, default=10,
                         help="Nº de clusters más repetitivos a guardar en "
                              "'<origin>/top_clusters.json' (default: 10)")

    args = parser.parse_args()
    output_path = args.output_config or f"config/{args.origin}_config.py"

    bootstrap_config(
        origin=args.origin,
        sample_glob=args.sample_logs,
        sample_size=args.sample_size,
        output_path=output_path,
        top_clusters_n=args.top_clusters,
    )