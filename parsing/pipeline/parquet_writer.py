"""
parquet_writer.py

Persistencia de registros agrupados por día en ficheros Parquet,
con merge/deduplicación contra el Parquet existente y sidecar JSON
de metadata (log_type, date, source_files).
"""
from parsing.parquet_io import records_to_parquet_bytes, parquet_bytes_to_records, derive_parquet_path
from .debug_utils import debug_print


def _merge_and_dedup(existing_records, group_records):
    """
    Fusiona existing_records + group_records deduplicando por
    (timestamp, message). Se ejecuta UNA sola vez (antes había un
    bloque duplicado idéntico que repetía este trabajo dos veces).

    Args:
        existing_records (list): Lista de registros existentes.
        group_records (list): Lista de registros nuevos a agregar.

    Returns:
        list: Lista de registros fusionados y deduplicados.
    """
    seen_keys = set()
    merged_records = []
    for r in existing_records + group_records:
        dedup_key = (r.get('timestamp'), r.get('message'))
        if dedup_key not in seen_keys:
            seen_keys.add(dedup_key)
            merged_records.append(r)
    return merged_records


def write_grouped_records(storage, output_folder, grouped, log_type, rel_path):
    """
    Escribe cada grupo de registros (por día) en su Parquet correspondiente,
    fusionando con el contenido existente si lo hay.

    Args:
        storage: Backend de almacenamiento.
        output_folder (str): Carpeta base de salida.
        grouped (dict): {group_key: [records]} (ver group_records_by_day).
        log_type (str): Tipo de log.
        rel_path (str): Ruta relativa del archivo fuente (para source_files).

    Returns:
        None
    """
    for group_key, group_records in grouped.items():
        output_path = derive_parquet_path(output_folder, group_key, log_type)

        existing_records = []
        existing_sources = []
        if storage.exists(output_path):
            existing_bytes = storage.read_all_bytes(output_path)
            existing_records = parquet_bytes_to_records(existing_bytes)

        sources_path = output_path.replace('.parquet', '_sources.json')
        if storage.exists(sources_path):
            existing_sources = storage.read_json(sources_path).get('source_files', [])

        existing_con_et = sum(1 for r in existing_records if r.get('event_type'))
        new_con_et = sum(1 for r in group_records if r.get('event_type'))
        debug_print(f"  🐛 DEBUG [{group_key}] existing_records con event_type: {existing_con_et}/{len(existing_records)}")
        debug_print(f"  🐛 DEBUG [{group_key}] group_records (nuevos) con event_type: {new_con_et}/{len(group_records)}")

        merged_records = _merge_and_dedup(existing_records, group_records)

        merged_con_et = sum(1 for r in merged_records if r.get('event_type'))
        debug_print(f"  🐛 DEBUG [{group_key}] merged_records con event_type: {merged_con_et}/{len(merged_records)}")

        merged_sources = list(existing_sources)
        if rel_path not in merged_sources:
            merged_sources.append(rel_path)

        parquet_bytes = records_to_parquet_bytes(merged_records)
        storage.write_bytes(output_path, parquet_bytes)

        storage.write_json(sources_path, {
            'log_type': log_type,
            'date': group_key if group_key != "sin_fecha" else None,
            'source_files': merged_sources,
        })

        print(f"  📁 {group_key} → +{len(group_records)} registros (total: {len(merged_records)}) → {output_path}")