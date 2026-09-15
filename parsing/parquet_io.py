"""
parquet_io.py

Utilidades para leer/escribir los resultados parseados en formato
Parquet en vez de JSON, con nomenclatura {year}_{month}_{day}_{origin}.parquet
"""
import io
import json
import pandas as pd


def _sanitize_record(record: dict) -> dict:
    """
    Convierte campos dict/list anidados a JSON string antes de pasar a
    Parquet. Esto evita que pyarrow infiera 'struct' types (que fallan
    si el dict está vacío en todos los records, ej. 'extracted': {}
    cuando ningún extractor matchea) y también evita problemas de
    esquema inconsistente entre records con distintas claves anidadas.

    Args:
        record (dict): Registro a sanear.

    Returns:
        dict: Registro saneado con campos dict/list convertidos a JSON string.
    """
    sanitized = {}
    for key, value in record.items():
        if isinstance(value, (dict, list)):
            sanitized[key] = json.dumps(value, ensure_ascii=False)
        else:
            sanitized[key] = value
    return sanitized


def records_to_parquet_bytes(records: list) -> bytes:
    """
    Convierte una lista de dicts (records) a bytes Parquet.
    Los campos dict/list (ej. 'extracted') se serializan como JSON
    string para evitar errores de 'struct with no child field' cuando
    están vacíos, y para tolerar esquemas heterogéneos entre records.

    Args:
        records (list): Lista de registros (dicts) a convertir.

    Returns:
        bytes: Contenido Parquet serializado.
    """
    sanitized_records = [_sanitize_record(r) for r in records]
    df = pd.DataFrame(sanitized_records)
    buffer = io.BytesIO()
    df.to_parquet(buffer, engine='pyarrow', index=False)
    return buffer.getvalue()


def _deserialize_record(record: dict, json_fields=("extracted",)) -> dict:
    """
    Revierte la serialización JSON aplicada en _sanitize_record() para
    los campos conocidos que originalmente eran dict/list.

    Args:
        record (dict): Registro a deserializar.
        json_fields (tuple): Campos que se espera que sean JSON string.

    Returns:
        dict: Registro con campos JSON string convertidos de vuelta a dict/list.
    """
    for field in json_fields:
        if field in record and isinstance(record[field], str):
            try:
                record[field] = json.loads(record[field])
            except (json.JSONDecodeError, TypeError):
                pass
    return record


def parquet_bytes_to_records(data: bytes) -> list:
    """
    Reconstruye la lista de dicts (records) desde bytes Parquet,
    deserializando de vuelta los campos JSON string a dict/list.

    Args:
        data (bytes): Contenido Parquet serializado.

    Returns:
        list: Lista de registros (dicts) reconstruidos.
    """
    buffer = io.BytesIO(data)
    df = pd.read_parquet(buffer, engine='pyarrow')
    records = df.to_dict(orient='records')
    return [_deserialize_record(r) for r in records]


def derive_parquet_path(output_folder: str, group_key, log_type: str) -> str:
    """
    Deriva la ruta de salida con nomenclatura {year}_{month}_{day}_{origin}.parquet,
    en carpeta plana (no year/month/day/ como antes).

    Args:
        output_folder (str): Carpeta base de salida.
        group_key: Tupla (year, month, day) o "sin_fecha".
        log_type (str): Tipo de log.

    Returns:
        str: Ruta de salida completa para el Parquet.
    """
    if group_key == "sin_fecha":
        file_name = f"sin_fecha_{log_type}.parquet"
    else:
        year, month, day = group_key
        file_name = f"{year}_{month}_{day}_{log_type}.parquet"

    return f"{output_folder}{file_name}"