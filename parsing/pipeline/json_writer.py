"""
json_writer.py

Persistencia de registros agrupados por día en ficheros JSON,
con merge/deduplicación contra el JSON existente.

Estructura simétrica a 'parquet_writer.py': mismo comportamiento de
merge/dedup, cambiando únicamente el formato de serialización de los
registros (JSON en vez de Parquet). No genera fichero de sources.
"""
import json
import os
from .debug_utils import debug_print


def _merge_and_dedup(existing_records, group_records):
    """
    Fusiona existing_records + group_records deduplicando por
    (timestamp, message).

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


def _group_key_to_str(group_key):
    """
    Normaliza group_key a un string tipo 'YYYY_MM_DD' o 'sin_fecha',
    admitiendo que venga como tupla ('YYYY','MM','DD'), como string
    ya formateado, o como el literal 'sin_fecha'.

    Args:
        group_key (str or tuple): Clave de grupo (fecha o 'sin_fecha').

    Returns:
        str: Clave de grupo normalizada como string.
    """
    if isinstance(group_key, tuple):
        return "_".join(str(part) for part in group_key)
    return str(group_key)


def derive_json_path(output_folder, group_key, log_type):
    """
    Deriva la ruta del fichero JSON de resultados:
    <output_folder>/<log_type>/YYYY_MM_DD_<log_type>.json
    (o 'sin_fecha_<log_type>.json' si group_key == 'sin_fecha').
    """
    key_str = _group_key_to_str(group_key)
    file_name = f"{key_str}_{log_type}.json"
    return os.path.join(output_folder, file_name)


def write_grouped_records_json(storage, output_folder, grouped, log_type, rel_path):
    """
    Escribe cada grupo de registros (por día) en su JSON correspondiente,
    fusionando con el contenido existente si lo hay.

    Args:
        storage: Backend de almacenamiento.
        output_folder (str): Carpeta base de salida.
        grouped (dict): {group_key: [records]} (ver group_records_by_day).
        log_type (str): Tipo de log.
        rel_path (str): Ruta relativa del archivo fuente (no usado aquí,
                         se mantiene por simetría de firma con
                         write_grouped_records de parquet_writer.py).

    Returns:
        None
    """
    for group_key, group_records in grouped.items():
        output_path = derive_json_path(output_folder, group_key, log_type)
        key_str = _group_key_to_str(group_key)

        existing_records = []
        if storage.exists(output_path):
            existing_payload = storage.read_json(output_path)
            existing_records = existing_payload.get('records', [])

        existing_con_et = sum(1 for r in existing_records if r.get('event_type'))
        new_con_et = sum(1 for r in group_records if r.get('event_type'))
        debug_print(f"  🐛 DEBUG [{key_str}] existing_records con event_type: {existing_con_et}/{len(existing_records)}")
        debug_print(f"  🐛 DEBUG [{key_str}] group_records (nuevos) con event_type: {new_con_et}/{len(group_records)}")

        merged_records = _merge_and_dedup(existing_records, group_records)

        merged_con_et = sum(1 for r in merged_records if r.get('event_type'))
        debug_print(f"  🐛 DEBUG [{key_str}] merged_records con event_type: {merged_con_et}/{len(merged_records)}")

        payload = {
            'log_type': log_type,
            'date': key_str if key_str != "sin_fecha" else None,
            'records': merged_records,
        }
        storage.write_bytes(output_path, json.dumps(payload, ensure_ascii=False, indent=2).encode('utf-8'))

        print(f"  📁 {key_str} → +{len(group_records)} registros (total: {len(merged_records)}) → {output_path}")