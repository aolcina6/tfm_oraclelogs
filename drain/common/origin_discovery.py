"""
origin_discovery.py 

Localización de ficheros por origen.
"""
import os
import re
from collections import defaultdict
from typing import List, Tuple, Dict, Any
from utils.log_detector import detect_log_type
from config.log_types_config import LOG_TYPES
from utils.log_detector import detect_log_type, load_config_module
from drain.common.drain_profile import get_drain_profile_params
from storage.decompress import extract_archives

def find_files_for_origin(storage, origin: str, output_folder: str) -> List[Tuple]:
    """
    Localiza los ficheros .log que pertenecen a un origen concreto.

    Args:
        storage: backend de almacenamiento
        origin (str): origen del log a buscar
        output_folder (str): carpeta de salida para excluir ficheros
    Returns:
        List[Tuple]: (file_path, rel_path, compression_type)
    """
    execution_mode = "S3" if hasattr(storage, 'bucket') else "LOCAL"
    log_folder = "" if execution_mode == "S3" else "logs/"

    # Listamos todos los ficheros con la extensión log
    all_log_files = storage.list_files(prefix=log_folder, extension=".log", exclude_prefix=output_folder)

    origin_files = []
    for file_info in all_log_files:
        if isinstance(file_info, tuple) and len(file_info) == 3:
            file_path, rel_path, compression_type = file_info
        else:
            file_path, rel_path = file_info
            compression_type = None

        file_name = os.path.basename(rel_path)
        # Detectamos el tipo de log usando la función detect_log_type
        log_type = detect_log_type(file_name, storage=storage, file_path=rel_path)

        if log_type == "unknown":
            log_type = file_name.replace('.log', '').replace('.txt', '').lower()

        if log_type == origin:
            origin_files.append((file_path, rel_path, compression_type))

    return origin_files

# ============================================================
# UTILIDADES PARA LOGS PARSEADOS (parsed_logs/{origin}.json)
# ============================================================
def detect_available_parsed_origins(storage, parsed_folder: str = "parsed_logs",
                                     parsed_format: str = "parquet") -> List[str]:
    """
    Escanea parsed_logs/ (ruta plana) y detecta todos los orígenes
    disponibles a partir de ficheros con nomenclatura
    '{year}_{month}_{day}_{origin}.<ext>' (ver derive_parquet_path()/
    derive_json_path()), o 'sin_fecha_{origin}.<ext>' para registros sin
    fecha detectada.

    El origen se extrae como todo lo que queda tras el 3er '_' (o tras
    'sin_fecha_'), soportando orígenes con guion bajo en el nombre
    (ej. 'e1_root').

    Args:
        storage: Backend de almacenamiento (local o S3).
        parsed_folder (str): Carpeta donde están los parsed_logs.
        parsed_format (str): 'parquet' (default) o 'json'. Determina la
            extensión de fichero que se escanea.

    Returns:
        List[str]: Lista de nombres de orígenes detectados.
    """
    if parsed_format not in ("parquet", "json"):
        raise ValueError(f"parsed_format debe ser 'parquet' o 'json', recibido: '{parsed_format}'")

    extension = f".{parsed_format}"
    print(f"\n🔍 Detectando orígenes disponibles en {parsed_folder}/... (formato={parsed_format})")

    origins = set()
    matched_files = storage.list_files(prefix=parsed_folder, extension=extension)

    for file_path, rel_path in matched_files:
        file_name = os.path.basename(rel_path)
        name_without_ext = file_name[:-len(extension)] if file_name.endswith(extension) else file_name

        if name_without_ext.startswith('sin_fecha_'):
            origin = name_without_ext[len('sin_fecha_'):]
        else:
            parts = name_without_ext.split('_')
            if len(parts) < 4:
                print(f"  ⚠️  Nombre de fichero inesperado, se omite: {file_name}")
                continue
            
            origin = '_'.join(parts[3:])

        if origin:
            origins.add(origin)

    origins_list = sorted(origins)
    print(f"✓ Orígenes detectados: {', '.join(origins_list)}")
    return origins_list


def discover_available_configs() -> List[str]:
    """
    Descubre todos los orígenes disponibles a partir del registro
    LOG_TYPES (config/log_types_config.py), NO escaneando el filesystem
    directamente. Si LOG_TYPES está desincronizado respecto a los
    ficheros reales en config/{origin}_config.py, esta función devolverá
    orígenes "fantasma" (sin fichero de config real) o se le pueden
    escapar orígenes nuevos si no se registran en LOG_TYPES.

    Returns:
        List[str]: Lista de nombres de orígenes detectados.
    """
    origins = sorted(LOG_TYPES.keys())
    return origins

def load_config_for_origin(origin: str) -> Dict[str, Any]:
    """
    Carga TIMESTAMP_PATTERNS, IGNORE_PATTERNS, MULTILINE y el perfil DRAIN_CONFIG.

    Args:
        origin (str): Nombre del origen de logs.
    
    Returns:    
    Dict[str, Any]: Diccionario con la configuración cargada para el origen.
    """
    config = {
        'timestamp_patterns': [],
        'ignore_patterns': [],
        'multiline': True,
        'compiled_patterns': None,  # dict {name: compiled_regex} o None
    }
    try:
        config_module = load_config_module(origin)
        if hasattr(config_module, 'TIMESTAMP_PATTERNS'):
            config['timestamp_patterns'] = config_module.TIMESTAMP_PATTERNS
        if hasattr(config_module, 'IGNORE_PATTERNS'):
            config['ignore_patterns'] = config_module.IGNORE_PATTERNS
        if hasattr(config_module, 'MULTILINE'):
            config['multiline'] = config_module.MULTILINE
        if hasattr(config_module, 'PATTERNS'):
            config['compiled_patterns'] = {
                name: re.compile(pattern, re.MULTILINE)
                for name, pattern in config_module.PATTERNS.items()
            }
        print(f"  ✓ Configuración cargada desde {origin}_config.py")
    except Exception as e:
        print(f"  ⚠️  Error cargando config para {origin}: {e}")
        print(f"  → Usando configuración por defecto")

    config['drain_profile'] = get_drain_profile_params(origin)
    return config

def discover_log_files_by_origin(storage, log_folder: str, output_folder: str) -> Dict[str, list]:
    """
    Descomprime, lista y agrupa por origen los ficheros .log del bucket/carpeta.
    
    Args:
        storage: backend de almacenamiento
        log_folder (str): carpeta donde buscar logs (puede ser vacía)
        output_folder (str): carpeta de salida para excluir ficheros

    Returns:
        Dict[str, list]: diccionario {origen: [(file_path, rel_path, compression_type), ...]}
    """
    print(f"\n📦 Buscando archivos comprimidos en: {log_folder or '(raíz del bucket)'}")
    extract_archives(storage, log_folder, delete_after_extract=False, exclude_prefix=output_folder)

    print(f"\nBuscando logs en: {log_folder or '(raíz del bucket)'}")
    log_files = storage.list_files(prefix=log_folder, extension=".log", exclude_prefix=output_folder)

    if not log_files:
        print("❌ No se encontraron archivos de log.")
        return {}

    print(f"✓ Archivos de log encontrados: {len(log_files)}")

    logs_by_origin = defaultdict(list)
    for file_info in log_files:
        if isinstance(file_info, tuple) and len(file_info) == 3:
            file_path, rel_path, compression_type = file_info
        else:
            file_path, rel_path = file_info
            compression_type = None

        file_name = os.path.basename(rel_path)
        origin = detect_log_type(file_name, storage=storage, file_path=rel_path)
        if origin == "unknown":
            origin = file_name.replace('.log', '').replace('.txt', '').lower()

        logs_by_origin[origin].append((file_path, rel_path, compression_type))

    print(f"\n📊 Archivos agrupados por origen:")
    for origin in sorted(logs_by_origin.keys()):
        print(f"  - {origin}: {len(logs_by_origin[origin])} archivo(s)")

    return logs_by_origin