"""
decompress.py 

Módulo para descomprimir archivos comprimidos (.tbz2, .tar.bz2, .tar.gz, .tgz) 
y subir los archivos extraídos al mismo prefijo relativo en el backend de storage.
"""
import os
import io
import tarfile
import tempfile


COMPRESSED_EXTENSIONS = (".tbz2", ".tar.bz2", ".tar.gz", ".tgz")


def extract_archives(storage, prefix: str, delete_after_extract: bool = False, exclude_prefix: str = None):
    """
    Busca archivos comprimidos (.tbz2, .tar.bz2, .tar.gz, .tgz) bajo 'prefix',
    los descomprime, y sube los archivos extraídos (típicamente .log) al mismo
    prefijo relativo dentro de 'prefix', usando el backend de storage abstracto.

    Funciona tanto en local como en S3 (o cualquier otro StorageBackend).

    Devuelve la lista de rutas/keys de los archivos extraídos.

    Args: 
        storage: Instancia de StorageBackend (local, S3, etc.).
        prefix: Prefijo (carpeta raíz) donde buscar los archivos comprimidos.
        delete_after_extract: Si es True, elimina el archivo comprimido después
            de extraerlo.
        exclude_prefix: Si se indica, se excluyen los archivos cuya ruta
            relativa (respecto a `prefix`) empiece por este valor.
    
    Returns: 
        Lista de rutas/keys de los archivos extraídos.
    """
    all_files = []
    for ext in COMPRESSED_EXTENSIONS:
        all_files.extend(storage.list_files(prefix, ext, exclude_prefix=exclude_prefix))

    if not all_files:
        print("  ℹ️  No se encontraron archivos comprimidos nuevos.")
        return []

    extracted_paths = []

    for archive_path, rel_path in all_files:
        print(f"  📦 Descomprimiendo: {rel_path}")
        # ...existing code sin cambios...

        try:
            raw_bytes = storage.read_all_bytes(archive_path)
        except Exception as e:
            print(f"  ✗ Error leyendo {archive_path}: {e}")
            continue

        # Determinar modo de apertura de tarfile según extensión
        if archive_path.endswith((".tbz2", ".tar.bz2")):
            mode = "r:bz2"
        elif archive_path.endswith((".tar.gz", ".tgz")):
            mode = "r:gz"
        else:
            mode = "r"

        try:
            with tarfile.open(fileobj=io.BytesIO(raw_bytes), mode=mode) as tar:
                for member in tar.getmembers():
                    if not member.isfile():
                        continue

                    extracted_file = tar.extractfile(member)
                    if extracted_file is None:
                        continue

                    content = extracted_file.read()

                    # ✅ Reconstruir ruta destino: misma carpeta que el .tbz2 original
                    archive_dir = os.path.dirname(rel_path)
                    dest_rel_path = os.path.join(archive_dir, os.path.basename(member.name))
                    dest_full_path = os.path.join(prefix, dest_rel_path).replace("\\", "/")

                    if storage.exists(dest_full_path):
                        print(f"    ⏭️  Ya existe, se omite: {dest_rel_path}")
                    else:
                        storage.write_bytes(dest_full_path, content)
                        print(f"    ✅ Extraído: {dest_rel_path}")

                    extracted_paths.append(dest_full_path)

            if delete_after_extract:
                storage.delete_file(archive_path)
                print(f"  🗑️  Archivo comprimido eliminado: {rel_path}")

        except Exception as e:
            print(f"  ✗ Error descomprimiendo {rel_path}: {e}")
            continue

    return extracted_paths