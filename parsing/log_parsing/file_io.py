"""
file_io.py 

Módulo de extracción de datos de ficheros. 
"""

def extract_from_file(file_path: str, storage=None):
    """
    Extrae el contenido de un archivo como string completo, usando storage si está disponible.

    Args:
        file_path (str): Ruta al archivo.
        storage: Backend de almacenamiento (opcional).

    Returns:
        str: Contenido del archivo como string, o "" si hubo error.
    """
    try:
        if storage is not None:
            try:
                content = storage.read_all_bytes(file_path)
                return content.decode('utf-8', errors='replace')
            except Exception as e:
                print(f"   ⚠️  Error leyendo desde storage: {e}")

        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            return f.read()

    except Exception as e:
        print(f"   ❌ Error fatal extrayendo {file_path}: {e}")
        return ""