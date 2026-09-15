"""
registry.py

Gestión del registro de archivos ya procesados completamente
(evita reprocesar archivos sin cambios entre ejecuciones de init.py).
"""
def load_processed_files_registry(storage, output_folder):
    """
    Carga el registro de archivos ya procesados completamente.
    
    Returns:
        dict: {
            'file_path': {
                'last_processed': timestamp,
                'size_bytes': int,
                'checksum': str (opcional),
                'records_count': int
            }
        }
    """
    registry_path = f"{output_folder}_processed_files.json"
    
    if storage.exists(registry_path):
        return storage.read_json(registry_path)
    
    return {}


def save_processed_files_registry(storage, output_folder, registry):
    """Guarda el registro de archivos procesados."""
    registry_path = f"{output_folder}_processed_files.json"
    storage.write_json(registry_path, registry)