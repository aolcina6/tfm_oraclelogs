"""
logparser_coverage.py

Ejecuta varios algoritmos de log parsing del proyecto logpai/logparser
(https://github.com/logpai/logparser) sobre un origen de example_logs/
y calcula métricas de cobertura, para comparar con el pipeline propio
(Drain3 + template_generator).

Requiere:
    pip install "logparser3 @ git+https://github.com/logpai/logparser.git"
o bien tener el repo clonado en external/logparser/ (ver README).

Uso:
    python template_generator/benchmarking/logparser_coverage.py \
        --origin ais \
        --log-file example_logs/COV_AIS_LOG.log \
        --log-format "<Date> <Time> <Level> <Content>" \
        --algorithms drain spell ael \
        --output benchmarks_logparser
"""
import argparse
import importlib
import json
import os
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# Si tienes el repo clonado localmente, esta ruta lo hace importable
_LOCAL_LOGPARSER = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "external", "logparser",
)
if os.path.isdir(_LOCAL_LOGPARSER):
    sys.path.insert(0, _LOCAL_LOGPARSER)


# Algoritmos disponibles en logpai/logparser y su módulo de importación.
# Cada entrada mapea el nombre corto -> (módulo, nombre de clase, parámetros por defecto).
ALGORITHM_REGISTRY = {
    "drain": {
        "module": "logparser.Drain",
        "class": "LogParser",
        "params": {"depth": 4, "st": 0.5},
    },
    "spell": {
        "module": "logparser.Spell",
        "class": "LogParser",
        "params": {"tau": 0.5},
    },
    "ael": {
        "module": "logparser.AEL",
        "class": "LogParser",
        "params": {},
    },
}


def _load_parser_class(algorithm_key):
    """
    Importa dinámicamente la clase LogParser del algoritmo indicado.

    Args:
        algorithm_key (str): clave del algoritmo (ej. 'drain', 'spell').

    Returns:
        tuple: (clase LogParser, dict de parámetros por defecto)
    """
    entry = ALGORITHM_REGISTRY.get(algorithm_key)
    if entry is None:
        raise ValueError(
            f"Algoritmo desconocido: '{algorithm_key}'. "
            f"Disponibles: {list(ALGORITHM_REGISTRY.keys())}"
        )
    try:
        mod = importlib.import_module(entry["module"])
    except ImportError as exc:
        raise ImportError(
            f"No se pudo importar '{entry['module']}'. "
            "Asegúrate de tener instalado logpai/logparser "
            "(pip install \"logparser3 @ git+https://github.com/logpai/logparser.git\") "
            "o el repo clonado en external/logparser/."
        ) from exc
    return getattr(mod, entry["class"]), entry["params"]


def run_algorithm(algorithm_key, log_file, log_format, indir, outdir, extra_params=None):
    """
    Ejecuta un algoritmo de logparser sobre un fichero de log y devuelve
    métricas de cobertura + tiempo de ejecución.

    Args:
        algorithm_key (str): 'drain', 'spell', 'ael' o 'iplom'.
        log_file (str): nombre del fichero de log (relativo a indir).
        log_format (str): formato de log estilo logparser, ej.
            "<Date> <Time> <Level> <Content>".
        indir (str): carpeta donde está el log_file.
        outdir (str): carpeta donde logparser escribirá sus resultados
            (<log_file>_structured.csv y <log_file>_templates.csv).
        extra_params (dict, optional): overrides de parámetros del algoritmo.

    Returns:
        dict: métricas de cobertura para este algoritmo.
    """
    parser_cls, default_params = _load_parser_class(algorithm_key)
    params = {**default_params, **(extra_params or {})}

    algo_outdir = os.path.join(outdir, algorithm_key)
    os.makedirs(algo_outdir, exist_ok=True)

    parser = parser_cls(
        indir=indir,
        outdir=algo_outdir,
        log_format=log_format,
        **params,
    )

    start = time.time()
    parser.parse(log_file)
    elapsed = time.time() - start

    structured_path = os.path.join(algo_outdir, f"{log_file}_structured.csv")
    templates_path = os.path.join(algo_outdir, f"{log_file}_templates.csv")

    return _compute_coverage(algorithm_key, structured_path, templates_path, elapsed)


def _compute_coverage(algorithm_key, structured_path, templates_path, elapsed_seconds):
    """
    Lee los CSV de salida de logparser y calcula métricas de cobertura:
    total de líneas, líneas asignadas a un EventId, nº de templates
    únicos generados y tamaño del cluster más grande.

    Args:
        algorithm_key (str): nombre del algoritmo evaluado.
        structured_path (str): ruta a '<file>_structured.csv'.
        templates_path (str): ruta a '<file>_templates.csv'.
        elapsed_seconds (float): tiempo de ejecución del algoritmo.

    Returns:
        dict: resumen de métricas de cobertura.
    """
    import pandas as pd

    if not os.path.exists(structured_path):
        return {
            "algorithm": algorithm_key,
            "error": f"No se generó '{structured_path}' (revisa log_format).",
        }

    df = pd.read_csv(structured_path)
    total_lines = len(df)
    matched = df["EventId"].notna().sum() if "EventId" in df.columns else 0
    coverage_pct = (matched / total_lines * 100) if total_lines else 0.0

    num_templates = 0
    if os.path.exists(templates_path):
        df_templates = pd.read_csv(templates_path)
        num_templates = len(df_templates)

    largest_cluster = 0
    if "EventId" in df.columns and total_lines:
        largest_cluster = int(df["EventId"].value_counts().max())

    return {
        "algorithm": algorithm_key,
        "total_lines": int(total_lines),
        "matched_lines": int(matched),
        "coverage_pct": round(coverage_pct, 2),
        "num_templates": int(num_templates),
        "largest_cluster_size": largest_cluster,
        "elapsed_seconds": round(elapsed_seconds, 3),
    }


def run_benchmark(origin, log_file_path, log_format, algorithms, output_folder):
    """
    Ejecuta uno o varios algoritmos de logparser sobre un fichero de log
    de 'origin' y guarda un resumen JSON con las métricas de cobertura
    de cada uno.

    Args:
        origin (str): nombre del origen (solo para etiquetar la salida).
        log_file_path (str): ruta completa al fichero de log a analizar.
        log_format (str): formato de log estilo logparser.
        algorithms (list[str]): algoritmos a ejecutar (ver ALGORITHM_REGISTRY).
        output_folder (str): carpeta donde se guardarán resultados y resumen.

    Returns:
        dict: resumen con las métricas de todos los algoritmos ejecutados.
    """
    indir = os.path.dirname(os.path.abspath(log_file_path))
    log_file = os.path.basename(log_file_path)
    os.makedirs(output_folder, exist_ok=True)

    results = []
    for algo in algorithms:
        print(f"▶️  Ejecutando '{algo}' sobre {log_file}...")
        try:
            metrics = run_algorithm(algo, log_file, log_format, indir, output_folder)
        except Exception as exc:  # noqa: BLE001 - queremos capturar cualquier fallo del algoritmo
            metrics = {"algorithm": algo, "error": str(exc)}
        results.append(metrics)
        if "error" in metrics:
            print(f"   ❌ {metrics['error']}")
        else:
            print(
                f"   ✅ cobertura={metrics['coverage_pct']}% "
                f"templates={metrics['num_templates']} "
                f"tiempo={metrics['elapsed_seconds']}s"
            )

    summary = {
        "origin": origin,
        "log_file": log_file,
        "log_format": log_format,
        "results": results,
    }

    summary_path = os.path.join(output_folder, f"{origin}_logparser_coverage.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(f"\n💾 Resumen guardado en: {summary_path}")
    return summary


def main():
    parser = argparse.ArgumentParser(
        description="Benchmark de cobertura usando algoritmos de logpai/logparser."
    )
    parser.add_argument("--origin", required=True, help="Nombre del origen (para etiquetar salida).")
    parser.add_argument("--log-file", required=True, help="Ruta al fichero de log a analizar.")
    parser.add_argument(
        "--log-format",
        required=True,
        help="Formato de log estilo logparser, ej. \"<Date> <Time> <Level> <Content>\".",
    )
    parser.add_argument(
        "--algorithms",
        nargs="+",
        default=["drain"],
        choices=list(ALGORITHM_REGISTRY.keys()),
        help="Algoritmos a ejecutar (default: drain).",
    )
    parser.add_argument(
        "--output",
        default="benchmarks_logparser",
        help="Carpeta de salida (default: benchmarks_logparser).",
    )
    args = parser.parse_args()

    run_benchmark(
        origin=args.origin,
        log_file_path=args.log_file,
        log_format=args.log_format,
        algorithms=args.algorithms,
        output_folder=args.output,
    )


if __name__ == "__main__":
    main()