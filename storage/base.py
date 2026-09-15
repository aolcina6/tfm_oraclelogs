"""
base.py 

Módulo de backend de almacenamiento local para logs y JSON.
"""

import os
import json

class StorageBackend:
    """
    Backend de almacenamiento que opera sobre el sistema de ficheros local.

    Implementa la interfaz StorageBackend para leer/escribir logs y JSON
    directamente en disco, sin dependencias externas (S3, etc.). Útil para
    desarrollo local o entornos on-premise.
    """

    def list_files(self, prefix: str, extension: str = ".log", exclude_prefix: str = None) -> list:
        """
        Recorre recursivamente un directorio y devuelve todos los archivos
        que coincidan con la extensión indicada.

        Args:
            prefix: Ruta base (carpeta raíz) desde la que empezar a buscar.
            extension: Extensión de archivo a filtrar (por defecto ".log").
            exclude_prefix: Si se indica, se excluyen los archivos cuya ruta
                relativa (respecto a `prefix`) empiece por este valor.

        Returns:
            Lista de tuplas (full_path, rel_path):
                - full_path: ruta absoluta/completa del archivo encontrado.
                - rel_path: ruta relativa respecto a `prefix`.
        """
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
        """
        Lee el contenido completo de un archivo en modo binario.

        Args:
            path: Ruta del archivo a leer.

        Returns:
            Contenido completo del archivo como bytes.
        """
        with open(path, "rb") as f:
            return f.read()

    def read_bytes_from_offset(self, path: str, start: int) -> bytes:
        """
        Lee el contenido de un archivo a partir de un offset (posición en
        bytes), útil para lectura incremental de logs que van creciendo.

        Args:
            path: Ruta del archivo a leer.
            start: Posición (en bytes) desde la que comenzar la lectura.

        Returns:
            Bytes leídos desde `start` hasta el final del archivo.
        """
        with open(path, "rb") as f:
            f.seek(start)
            return f.read()

    def get_file_size(self, path: str) -> int:
        """
        Obtiene el tamaño en bytes de un archivo.

        Args:
            path: Ruta del archivo.

        Returns:
            Tamaño del archivo en bytes.

        Note:
            Este método está definido dos veces en la clase (ver también
            la versión más abajo con manejo de excepción vía `key`).
            Python usará la última definición (la que devuelve 0 si el
            archivo no existe), haciendo esta primera versión inalcanzable.
        """
        return os.path.getsize(path)

    def write_json(self, path: str, data: dict):
        """
        Serializa un diccionario a JSON y lo escribe en disco, creando
        los directorios intermedios si no existen.

        Args:
            path: Ruta destino del archivo JSON.
            data: Diccionario a serializar.
        """
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def read_json(self, path: str) -> dict:
        """
        Lee y deserializa un archivo JSON.

        Args:
            path: Ruta del archivo JSON a leer.

        Returns:
            Diccionario con el contenido deserializado del JSON.

        Raises:
            FileNotFoundError: Si el archivo no existe.
            json.JSONDecodeError: Si el contenido no es un JSON válido.
        """
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def exists(self, path: str) -> bool:
        """
        Comprueba si un archivo o directorio existe en la ruta indicada.

        Args:
            path: Ruta a comprobar.

        Returns:
            True si la ruta existe, False en caso contrario.
        """
        return os.path.exists(path)
    
    def write_bytes(self, path: str, data: bytes):
        """
        Escribe contenido binario en disco, creando los directorios
        intermedios si no existen.

        Args:
            path: Ruta destino del archivo.
            data: Contenido en bytes a escribir.
        """
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)

    def delete_file(self, path: str):
        """
        Elimina un archivo si existe. No lanza error si el archivo
        no existe (operación idempotente).

        Args:
            path: Ruta del archivo a eliminar.
        """
        if os.path.exists(path):
            os.remove(path)

    def get_file_size(self, key: str) -> int:
        """
        Obtiene el tamaño en bytes de un archivo de forma segura,
        devolviendo 0 si el archivo no existe o no es accesible.

        Args:
            key: Ruta del archivo.

        Returns:
            Tamaño del archivo en bytes, o 0 si ocurre un OSError
            (archivo inexistente, permisos, etc.).

        Note:
            ⚠️ Esta es la segunda definición de `get_file_size` en la
            clase; sobreescribe a la definida más arriba (que no
            capturaba excepciones). Considera eliminar la duplicidad
            para evitar confusión sobre qué versión se está usando.
        """
        try:
            return os.path.getsize(key)
        except OSError:
            return 0