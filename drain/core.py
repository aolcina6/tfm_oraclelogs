"""
core.py 

Núcleo de procesamiento compartido por drain_unified.py (análisis completo,
1 configuración, guarda todos los resultados) y
drain/benchmarking/drain_benchmarking_unified.py (N configuraciones,
solo calcula métricas de calidad, descarta los registros individuales).
"""
import time
from typing import Dict, List, Any, Optional

from drain.drain_custom import Drain
from drain.drain3_wrapper import Drain3Wrapper
from drain.common.drain3_utils import build_template_miner_config, build_message_only_config  

def process_raw_lines_with_drain(
    lines_to_parse: List[str],
    total_lines: int,
    depth: int,
    st: float,
    origin_config: Dict[str, Any],
    max_children: int = 100,
    collect_records: bool = True,
) -> Dict[str, Any]:
    """
    Procesa líneas crudas (.log) con Drain custom.

    Args:
        lines_to_parse: líneas ya leídas/preprocesadas (multilínea agrupado si aplica).
        total_lines: nº total de líneas leídas (antes de filtrar vacías/ignoradas).
        depth, st, max_children: hiperparámetros de Drain.
        origin_config: dict devuelto por load_config_for_origin(origin).
        collect_records: si True, guarda un registro por línea procesada
            (necesario para escribir parsed_logs completos en análisis).
            Si False, solo se acumulan los clusters (usado en benchmarking,
            evita guardar millones de registros en memoria).

    Returns:
        Dict con: 'clusters_info', 'ignored_lines_count', 'processed_lines',
        'total_lines', 'elapsed_time_sec', 'records' (solo si collect_records).
    """
    drain = Drain(
        depth=depth, st=st,
        ignore_patterns=origin_config['ignore_patterns'],
        timestamp_patterns=origin_config['timestamp_patterns'],
        multiline=False,  # el agrupado multilínea ya se hizo antes de llamar aquí
    )

    records = [] if collect_records else None
    processed_lines = 0
    start_time = time.time()

    for idx, line in enumerate(lines_to_parse):
        line = line.strip()
        if not line:
            continue
        result = drain.parse(line, log_id=processed_lines)
        if result.get('ignored', False):
            continue
        processed_lines += 1
        if collect_records:
            records.append({'line_number': idx + 1, **result})

    elapsed_time = time.time() - start_time

    output = {
        'clusters_info': drain.get_clusters_info(),
        'ignored_lines_count': drain.ignored_lines_count,
        'processed_lines': processed_lines,
        'total_lines': total_lines,
        'elapsed_time_sec': round(elapsed_time, 2),
        'parameters': {
            'depth': depth,
            'st': st,
            'max_children': max_children,
            'engine': 'drain_custom',
        },
    }
    if collect_records:
        output['records'] = records
    return output


def process_raw_lines_with_drain3(
    lines_to_parse: List[str],
    total_lines: int,
    depth: int,
    st: float,
    max_children: int,
    origin_config: Dict[str, Any],
    persistence=None,
    collect_records: bool = True,
) -> Dict[str, Any]:
    """
    Procesa líneas crudas (.log) con Drain3 (vía Drain3Wrapper).

    Args:
        persistence: PersistenceHandler opcional (solo usado en análisis
            completo con persist_state=True; en benchmarking se deja None).
        (resto igual que process_raw_lines_with_drain)

    Returns:
        Igual que process_raw_lines_with_drain, con 'records' incluyendo
        además 'change_type' de Drain3.
    """
    miner_config = build_template_miner_config(
        origin_config['timestamp_patterns'], depth, st, max_children
    )
    wrapper = Drain3Wrapper(miner_config, ignore_patterns=origin_config['ignore_patterns'])
    if persistence is not None:
        wrapper._template_miner.persistence_handler = persistence
        wrapper._template_miner.load_state()

    records = [] if collect_records else None
    processed_lines = 0
    start_time = time.time()

    for idx, line in enumerate(lines_to_parse):
        line = line.strip()
        if not line:
            continue
        result = wrapper.parse(line, log_id=processed_lines)
        if result.get('ignored', False):
            continue
        processed_lines += 1
        if collect_records:
            records.append({
                'line_number': idx + 1,
                'original': line,
                'cluster_id': result['cluster_id'],
                'template': result['template_mined'],
                'change_type': result['change_type'],
            })

    elapsed_time = time.time() - start_time

    output = {
        'clusters_info': wrapper.get_clusters_info(),
        'ignored_lines_count': wrapper.ignored_lines_count,
        'processed_lines': processed_lines,
        'total_lines': total_lines,
        'elapsed_time_sec': round(elapsed_time, 2),
        'parameters': {
            'depth': depth,
            'st': st,
            'max_children': max_children,
            'engine': 'drain3',
        },
    }
    if collect_records:
        output['records'] = records
    return output


def process_parsed_messages_with_drain(
    records_with_message: List[Dict[str, Any]],
    depth: int,
    st: float,
    origin_config: Dict[str, Any],
    max_children: int = 100,
    collect_records: bool = True,
) -> Dict[str, Any]:
    """
    Procesa mensajes YA parseados (parsed_logs/, campo 'message') con Drain custom.

    Args:
        records_with_message: registros con al menos la clave 'message'.
        max_children: máximo número de hijos por nodo del árbol antes de
            generalizar a '<*>' (usado por el árbol de prefijos de Drain).
        collect_records: si True, enriquece cada record IN-PLACE con
            'cluster_id'/'template' y los devuelve en 'records' (análisis).
            Si False, no modifica los records (benchmarking).

    Returns:
        Dict con 'clusters_info', 'ignored_count', 'processed_count',
        'total_messages', 'elapsed_time_sec', 'records' (si collect_records).
    """
    drain = Drain(
        depth=depth, st=st, max_children=max_children,
        ignore_patterns=origin_config['ignore_patterns'],
        timestamp_patterns=[], multiline=False,
    )

    processed_count = 0
    start_time = time.time()

    for idx, record in enumerate(records_with_message):
        message = record['message'].strip()
        result = drain.parse(message, log_id=idx)
        if result.get('ignored', False):
            if collect_records:
                record['cluster_id'] = None
                record['template'] = None
            continue
        processed_count += 1
        if collect_records:
            record['cluster_id'] = result['cluster_id']
            record['template'] = result['template']

    elapsed_time = time.time() - start_time

    output = {
        'clusters_info': drain.get_clusters_info(),
        'ignored_count': drain.ignored_lines_count,
        'processed_count': processed_count,
        'total_messages': len(records_with_message),
        'elapsed_time_sec': round(elapsed_time, 2),
        'parameters': {
            'depth': depth,
            'st': st,
            'max_children': max_children,
            'engine': 'drain_custom',
        },
    }
    if collect_records:
        output['records'] = records_with_message
    return output


def process_parsed_messages_with_drain3(
    records_with_message: List[Dict[str, Any]],
    depth: int,
    st: float,
    max_children: int,
    origin_config: Dict[str, Any],
    collect_records: bool = True,
) -> Dict[str, Any]:
    """
    Procesa mensajes YA parseados (parsed_logs/, campo 'message') con Drain3.

    Igual semántica que process_parsed_messages_with_drain, pero usando
    Drain3Wrapper. Si collect_records=False, los records que no matchean
    (ignorados) simplemente no se cuentan pero tampoco se filtran de la
    lista original (a diferencia de collect_records=True, que devuelve
    una NUEVA lista solo con los procesados, igual que hacía
    analyze_parsed_logs_with_drain3 originalmente).

    Args:
        records_with_message: registros con al menos la clave 'message'.
        collect_records: si True, enriquece cada record IN-PLACE con
            'cluster_id'/'template'/'change_type' y los devuelve en 'records'
            (análisis). Si False, no modifica los records (benchmarking).

    Returns:
        Dict con 'clusters_info', 'ignored_count', 'processed_count',
        'total_messages', 'elapsed_time_sec', 'records' (si collect_records).
    """
    config = build_template_miner_config([], depth, st, max_children) \
        if False else None  # noqa: nunca se usa message_only aquí realmente
    config = build_message_only_config(depth, st, max_children)
    wrapper = Drain3Wrapper(config, ignore_patterns=origin_config['ignore_patterns'])

    processed_records = [] if collect_records else None
    processed_count = 0
    start_time = time.time()

    for record in records_with_message:
        message = record['message'].strip()
        result = wrapper.parse(message)
        if result.get('ignored', False):
            continue
        processed_count += 1
        if collect_records:
            record['cluster_id'] = result['cluster_id']
            record['template'] = result['template_mined']
            record['change_type'] = result['change_type']
            processed_records.append(record)

    elapsed_time = time.time() - start_time

    output = {
        'clusters_info': wrapper.get_clusters_info(),
        'ignored_count': wrapper.ignored_lines_count,
        'processed_count': processed_count,
        'total_messages': len(records_with_message),
        'elapsed_time_sec': round(elapsed_time, 2),
        'parameters': {
            'depth': depth,
            'st': st,
            'max_children': max_children,
            'engine': 'drain3',
        },
    }
    if collect_records:
        output['records'] = processed_records
    return output