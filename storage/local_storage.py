
"""
local_storage.py 

Implementación de StorageBackend para almacenamiento local.
"""
import os
import json
from storage.base import StorageBackend


class LocalStorage(StorageBackend):
    def list_files(self, prefix: str, 
    extension: str = ".log", 
    exclude_prefix: str = None) -> list:
        log_files = []
        for root, dirs, files in os.walk(prefix):
            for f in files:
                if f.endswith(extension):
                    full_path = os.path.join(root, f)
                    rel_path = os.path.relpath(full_path, prefix)
                    if exclude_prefix and rel_path.startswith(exclude_prefix):
                        continue
                    log_files.append((full_path, rel_path))
        return log_files

    def read_all_bytes(self, path: str) -> bytes:
        with open(path, "rb") as f:
            return f.read()

    def read_bytes_from_offset(self, path: str, start: int) -> bytes:
        with open(path, "rb") as f:
            f.seek(start)
            return f.read()

    def get_file_size(self, path: str) -> int:
        return os.path.getsize(path)

    def write_json(self, path: str, data: dict):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def read_json(self, path: str) -> dict:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def exists(self, path: str) -> bool:
        return os.path.exists(path)
    
    def write_bytes(self, path: str, data: bytes):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)

    def delete_file(self, path: str):
        if os.path.exists(path):
            os.remove(path)

    def get_file_size(self, key: str) -> int:
        """Obtiene el tamaño de un archivo local."""
        try:
            return os.path.getsize(key)
        except OSError:
            return 0