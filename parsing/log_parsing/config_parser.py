"""
config_parser.py 

Módulo principal de parsing de logs. Detecta la configuración adecuada y delega en el 
motor de parseo correspondiente (multilínea o singleline).
"""
import re
import os

from .file_io import extract_from_file
from .multiline_engine import parse_multiline
from .singleline_engine import parse_singleline


def parse_lines_with_config(full_text, cfg_module, log_type, file_name):
    """
    Dispatcher de parseo: elige el motor (multiline/singleline) según la
    config del origen y delega en el módulo correspondiente.

    Args:
        full_text (str): Contenido completo del archivo de log.
        cfg_module: Módulo de configuración cargado dinámicamente.
        log_type (str): Tipo de log detectado.
        file_name (str): Nombre del archivo de log.

    Returns:
        Tuple[List[dict], List[dict]]: Lista de registros parseados y lista de líneas sin match.
    """
    patterns = getattr(cfg_module, 'PATTERNS', {})
    ignore_patterns = getattr(cfg_module, 'IGNORE_PATTERNS', [])
    multiline = getattr(cfg_module, 'MULTILINE', False)

    if not patterns:
        print(f"  ❌ No hay PATTERNS para {log_type}")
        return [], []

    print(f"  ✓ {len(patterns)} pattern(s), {len(ignore_patterns)} ignore(s)")
    if multiline:
        print(f"  ✓ Modo MULTILINE")

    # ===== PRE-COMPILAR PATRONES =====
    compiled_patterns = {}
    for pattern_name, pattern_regex in patterns.items():
        try:
            # Cada config gestiona su propio multilínea (lookaheads negativos,
            # \n? explícitos, etc.). Solo activamos MULTILINE para que ^ y $
            # funcionen por línea; NO forzamos DOTALL para no romper esa lógica.
            flags = re.MULTILINE if multiline else 0
            compiled_patterns[pattern_name] = re.compile(pattern_regex, flags)
        except re.error as e:
            print(f"  ⚠️  Error en '{pattern_name}': {e}")

    # ===== PRE-COMPILAR IGNORE PATTERNS =====
    compiled_ignore = []
    if ignore_patterns:
        for pattern in ignore_patterns:
            try:
                compiled_ignore.append(re.compile(pattern))
            except re.error as e:
                print(f"  ⚠️  Error ignore: {pattern[:30]}... → {e}")

    #   ===== DELEGAR AL MOTOR CORRESPONDIENTE =====
    if multiline:
        records = parse_multiline(full_text, compiled_patterns, compiled_ignore, log_type, file_name)
        return records, []
    else:
        return parse_singleline(full_text, compiled_patterns, compiled_ignore, log_type, file_name)


def autodiscover_config(file_path: str, storage=None, log_type=None, cfg_module=None):
    """
    Detecta automáticamente la configuración de parsing para un archivo de log dado,
    usando un módulo de configuración específico.

    Args:
        file_path (str): Ruta al archivo de log.
        storage: Backend de almacenamiento (opcional).
        log_type (str): Tipo de log detectado (ej: 'jde', 'jdedebug').
        cfg_module: Módulo de configuración cargado dinámicamente.

    Returns:
        dict: Diccionario con la configuración detectada, registros parseados y líneas sin match.
    """
    filename = os.path.basename(file_path)

    if not log_type:
        print(f"  ❌ ERROR: autodiscover_config() requiere log_type")
        return None

    full_text = extract_from_file(file_path, storage)
    if not full_text:
        print(f"  ❌ Archivo vacío")
        return None

    line_count = full_text.count('\n')
    print(f"  ✓ Leídas ~{line_count:,} líneas")

    print(f"  → Parseando con {log_type}...")
    records, unmatched = parse_lines_with_config(full_text, cfg_module, log_type, filename)

    print(f"  ✓ {len(records):,} registros, {len(unmatched):,} sin match")

    return {
        'config': {
            'log_type': log_type,
            'timestamp_format': getattr(cfg_module, 'TIMESTAMP_PATTERNS', [None])[0],
            'timestamp_patterns': getattr(cfg_module, 'TIMESTAMP_PATTERNS', None),
            'delimiter': getattr(cfg_module, 'DELIMITER', ' '),
            'important_keywords': getattr(cfg_module, 'IMPORTANT_KEYWORDS', []),
            'extractors': getattr(cfg_module, 'EXTRACTORS', None)
        },
        'records': records,
        'unmatched': unmatched
    }