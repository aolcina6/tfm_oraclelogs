"""
factory.py 

Módulo de fábrica para seleccionar el backend de almacenamiento 
según la variable de entorno EXECUTION_MODE.
"""
import os
from storage.local_storage import LocalStorage

S3_BUCKET_NAME = ""
S3_REGION = ""


def get_storage_backend():
    """
    Selecciona el backend según la variable de entorno EXECUTION_MODE.
    Valores soportados: 'LOCAL' (por defecto), 'S3'

    Args: 
        None
    
    Returns:
        storage_backend: Instancia del backend de almacenamiento seleccionado.
        mode: Modo de ejecución detectado ('LOCAL' o 'S3').
    """
    mode = os.environ.get("EXECUTION_MODE", "LOCAL").upper()

    if mode == "S3":
        from storage.s3_storage import S3Storage 
        return S3Storage(S3_BUCKET_NAME, S3_REGION), mode
    else:
        return LocalStorage(), mode