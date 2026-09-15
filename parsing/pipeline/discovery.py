"""
discovery.py

Determina qué archivos de log deben procesarse en la ejecución actual,
comparando contra el registro de archivos ya procesados.
"""
def should_process_file(storage, file_path, rel_path, registry, force=False):
    """
    Determina si un archivo debe procesarse.

    Args:
        storage: Backend de storage
        file_path: Ruta completa del archivo
        rel_path: Ruta relativa
        registry: Registro de archivos procesados
        force: Forzar reprocesamiento

    Returns:
        Tuple[bool, str]: (debe_procesarse, motivo)
    """
    if force:
        return True, "Forzado por usuario"

    if rel_path not in registry:
        return True, "Archivo nuevo"

    registered = registry[rel_path]

    if registered.get('needs_reprocessing', False):
        unmatched_count = registered.get('unmatched_lines', 0)
        return True, f"Tiene {unmatched_count} líneas en learning queue"

    try:
        current_size = storage.get_file_size(file_path)
    except Exception:
        return True, "No se pudo verificar tamaño"

    registered_size = registered.get('size_bytes', 0)

    if current_size != registered_size:
        return True, f"Tamaño cambió: {registered_size} → {current_size} bytes"

    last_processed = registered.get('last_processed', 'N/A')
    return False, f"Ya procesado completamente el {last_processed}"