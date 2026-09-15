"""
drain_unified.py 

Módulo unificado con las 3 estrategias de clustering de logs del proyecto:

1. analyze_logs_by_origin()         -> Drain CUSTOM sobre logs crudos (.log)
2. analyze_logs_by_origin_drain3()  -> Drain3 (librería oficial) sobre logs crudos (.log)
3. analyze_parsed_logs_with_drain() -> Drain CUSTOM sobre logs YA PARSEADOS (parsed_logs/),
                                        usando solo el campo 'message'
"""
import os
import re
import sys
import argparse
from collections import defaultdict
from datetime import datetime
from typing import List, Dict, Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from parsing.log_parsing.multiline_utils import compile_timestamp_patterns, line_starts_new_event

from config.general_config import TIMESTAMP_PATTERNS
from storage.factory import get_storage_backend
from storage.decompress import extract_archives
from utils.log_detector import detect_log_type, load_config_module
from parsing.log_parsing.text_preprocessing import (
    ORCHESTRATION_LINE_RE,
    _condense_match,
    filter_ignored_lines,
)
from drain.common import find_files_for_origin, load_and_preprocess_lines
from drain.common.cluster_output import (
    build_cluster_stats,
    print_top_clusters,
)
from drain.common.output_writers import write_parsed_analysis_outputs

from drain.drain_custom import Node, LogCluster, Drain
from drain.drain3_wrapper import Drain3Wrapper
from drain.common.origin_discovery import (
    detect_available_parsed_origins,
    load_config_for_origin,
    discover_log_files_by_origin,
)
from drain.common.drain3_utils import (
    build_template_miner_config, 
    StoragePersistence,
)
from drain.common.drain_profile import (
    get_drain_profile_params,
)
from drain.common.output_writers import (
    write_raw_origin_outputs,
    write_consolidated_summary,
)
from parsing.parquet_io import parquet_bytes_to_records
from drain.core import (
    process_raw_lines_with_drain,
    process_raw_lines_with_drain3,
    process_parsed_messages_with_drain,
    process_parsed_messages_with_drain3,
)
from parsing.log_parsing.multiline_engine import (
    group_multiline_logs,
)

# ============================================================
# 1) DRAIN CUSTOM sobre logs crudos (.log)
# ============================================================

def analyze_logs_by_origin(storage, log_folder: str = "logs",
                            depth: int = 4, st: float = 0.5,
                            remove_timestamps: bool = True, remove_numbers: bool = True,
                            output_folder: str = "drain_results",
                            origin_filter: List[str] = None):
    """
    Análisis de logs crudos (.log) usando Drain CUSTOM, agrupando por origen. 
    Se detectan los ficheros de logs por origen, se cargan y preprocesan.

    Args:
        storage: backend de almacenamiento (local o S3)
        log_folder (str): carpeta base donde se encuentran los logs
        depth (int): profundidad del árbol de Drain
        st (float): umbral de similitud para clustering
        remove_timestamps (bool): si True, se eliminan timestamps antes de parsear
        remove_numbers (bool): si True, se eliminan números antes de parsear
        output_folder (str): carpeta donde se guardarán los resultados
        origin_filter (List[str]): lista de orígenes a procesar; si None, todos los encontrados

    Returns:
        None. Los resultados se guardan en 'output_folder' y se imprime un resumen por origen.
    """
    print(f"🔍 DRAIN - Autodescubrimiento de patrones en logs (agrupado por origen)")
    print(f"Parámetros: depth={depth}, st={st}")

    execution_mode = "S3" if hasattr(storage, 'bucket') else "LOCAL"
    log_folder = "" if execution_mode == "S3" else "logs/"

    logs_by_origin = discover_log_files_by_origin(storage, log_folder, output_folder)
    if not logs_by_origin:
        return

    if origin_filter:
        missing = [o for o in origin_filter if o not in logs_by_origin]
        if missing:
            print(f"⚠️  Orígenes no encontrados y se ignorarán: {missing}")
        logs_by_origin = {o: v for o, v in logs_by_origin.items() if o in origin_filter}
        if not logs_by_origin:
            print(f"❌ Ninguno de los orígenes indicados en --origin existe: {origin_filter}")
            return

    summary_by_origin = {}

    for origin in sorted(logs_by_origin.keys()):
        print(f"\n{'='*70}")
        print(f"PROCESANDO ORIGEN: {origin.upper()}")
        print(f"{'='*70}")

        origin_config = load_config_for_origin(origin)
        timestamp_patterns = origin_config['timestamp_patterns']
        ignore_patterns = origin_config['ignore_patterns']
        multiline = origin_config['multiline']

        files_for_origin = logs_by_origin[origin]

        print(f"  ✓ Modo multilínea: {'ACTIVADO' if multiline else 'DESACTIVADO'}")
        print(f"  ✓ Ignore patterns: {len(ignore_patterns)}")

        stats = {'multiline_groups': 0, 'continuation_lines': 0}
        lines_to_parse, total_lines = load_and_preprocess_lines(
            storage, files_for_origin, origin_config['multiline'],
            grouping_fn=(
                lambda lines: group_multiline_logs(
                    lines, stats,
                    origin_config['timestamp_patterns'],
                    compiled_patterns=origin_config.get('compiled_patterns'),
                )
            ) if origin_config['multiline'] else None,
        )

        result = process_raw_lines_with_drain(
            lines_to_parse, total_lines, depth, st, origin_config, collect_records=True
        )
        clusters = result['clusters_info']
        all_parsed_logs = result['records']
        patterns = [{'template': c['template'], 'occurrences': c['size']} for c in clusters]

        origin_result = {
            'origin': origin,
            'files': [{'path': rel_path, 'filename': os.path.basename(rel_path)}
                      for _, rel_path, _ in files_for_origin],
            'total_lines': total_lines,
            'ignored_lines': result['ignored_lines_count'],
            'processed_lines': len(all_parsed_logs),
            'total_clusters': len(clusters),
            'clusters': clusters,
            'patterns': patterns,
            'parsed_logs': all_parsed_logs,
            'parameters': {
                'depth': depth, 'similarity_threshold': st,
                'ignore_patterns': list(ignore_patterns),
                'multiline': multiline, 'engine': 'drain_custom',
            }
        }

        write_raw_origin_outputs(storage, origin, origin_result, output_folder, 'drain')

        summary_by_origin[origin] = {
            'files': len(files_for_origin),
            'total_clusters': len(clusters),
            'total_lines': total_lines,
            'ignored_lines': result['ignored_lines_count'],
            'processed_lines': len(all_parsed_logs),
        }

    write_consolidated_summary(storage, output_folder, summary_by_origin, mode='drain_custom')
    


# ============================================================
# 2) DRAIN3 (librería oficial) sobre logs crudos (.log)
# ============================================================

def analyze_logs_by_origin_drain3(storage, log_folder: str = "logs",
                                   depth: int = 4,
                                   st: float = 0.5,
                                   max_children: int = 100,
                                   output_folder: str = "drain3_results",
                                   persist_state: bool = True,
                                   origin_filter: List[str] = None):
    """
    Autodescubrimiento de patrones en logs usando Drain3 (librería oficial),
    agrupando por origen igual que analyze_logs_by_origin().

    Args:
        storage: backend de almacenamiento (local o S3)
        log_folder (str): carpeta base donde se encuentran los logs
        depth (int): profundidad del árbol de Drain3
        st (float): umbral de similitud para clustering
        max_children (int): máximo número de hijos por nodo en Drain3
        output_folder (str): carpeta donde se guardarán los resultados
        persist_state (bool): si True, guarda el estado del árbol entre ejecuciones
        origin_filter (List[str]): lista de orígenes a procesar; si None, todos los encontrados

    Returns:
        Dict[str, Any]: resultados completos por origen, incluyendo clusters y logs parseados
    """
    print(f"🔍 DRAIN3 - Autodescubrimiento de patrones en logs (agrupado por origen)")
    print(f"Parámetros: depth={depth}, st={st}, max_children={max_children}\n")

    execution_mode = "S3" if hasattr(storage, 'bucket') else "LOCAL"
    log_folder = "" if execution_mode == "S3" else "logs/"

    logs_by_origin = discover_log_files_by_origin(storage, log_folder, output_folder)
    if not logs_by_origin:
        return

    if origin_filter:
        missing = [o for o in origin_filter if o not in logs_by_origin]
        if missing:
            print(f"⚠️  Orígenes no encontrados y se ignorarán: {missing}")
        logs_by_origin = {o: v for o, v in logs_by_origin.items() if o in origin_filter}
        if not logs_by_origin:
            print(f"❌ Ninguno de los orígenes indicados en --origin existe: {origin_filter}")
            return

    summary_by_origin = {}
    all_results = {}

    for origin in sorted(logs_by_origin.keys()):
        print(f"\n{'='*60}")
        print(f"PROCESANDO ORIGEN: {origin.upper()} (Drain3)")
        print(f"{'='*60}")

        origin_config = load_config_for_origin(origin)
        timestamp_patterns = origin_config['timestamp_patterns']
        ignore_patterns = origin_config['ignore_patterns']
        multiline = origin_config['multiline']

        print(f"  ✓ Modo multilínea: {'ACTIVADO' if multiline else 'DESACTIVADO'}")
        print(f"  ✓ Ignore patterns: {len(ignore_patterns)}")

        miner_config = build_template_miner_config(timestamp_patterns, depth, st, max_children)

        persistence = None
        if persist_state:
            state_path = f"{output_folder}/{origin}/{origin}_drain3_state.json"
            persistence = StoragePersistence(storage, state_path)

        files_for_origin = logs_by_origin[origin]

        stats = {'multiline_groups': 0, 'continuation_lines': 0}
        lines_to_parse, total_lines = load_and_preprocess_lines(
            storage, files_for_origin, origin_config['multiline'],
            grouping_fn=(
                lambda lines: group_multiline_logs(
                    lines, stats,
                    origin_config['timestamp_patterns'],
                    compiled_patterns=origin_config.get('compiled_patterns'),
                )
            ) if origin_config['multiline'] else None,
        )

        result = process_raw_lines_with_drain3(
            lines_to_parse, total_lines, depth, st, max_children,
            origin_config, persistence=persistence, collect_records=True
        )
        clusters_info = result['clusters_info']
        all_parsed_logs = result['records']
        ignored_lines_count = result['ignored_lines_count']

        examples_by_cluster = defaultdict(list)
        for log in all_parsed_logs:
            cid = log['cluster_id']
            if len(examples_by_cluster[cid]) < 5:
                examples_by_cluster[cid].append(log['original'])

        patterns = [
            {
                'template': c['template'],
                'occurrences': c['size'],
                'cluster_id': c['cluster_id'],
                'examples': examples_by_cluster.get(c['cluster_id'], [])
            }
            for c in clusters_info
        ]

        print(f"\n✓ Análisis completado para {origin.upper()}")
        print(f"  - Total archivos: {len(files_for_origin)}")
        print(f"  - Total líneas: {total_lines}")
        print(f"  - Líneas ignoradas: {ignored_lines_count}")
        print(f"  - Líneas procesadas: {len(all_parsed_logs)}")
        print(f"  - Total clusters descubiertos: {len(clusters_info)}")
        if multiline:
            print(f"  - Grupos multilínea: {stats['multiline_groups']}")
            print(f"  - Líneas de continuación: {stats['continuation_lines']}")

        print(f"\n📊 Top 10 patrones más frecuentes ({origin.upper()}):")
        for i, pattern in enumerate(patterns[:10], 1):
            pct = (pattern['occurrences'] / len(all_parsed_logs)) * 100 if all_parsed_logs else 0
            print(f"  {i:2d}. [{pattern['occurrences']:4d} veces, {pct:5.1f}%] {pattern['template'][:60]}")

        origin_result = {
            'origin': origin,
            'files': [{'path': rel_path, 'filename': os.path.basename(rel_path)}
                      for _, rel_path, _ in files_for_origin],
            'total_lines': total_lines,
            'ignored_lines': ignored_lines_count,
            'processed_lines': len(all_parsed_logs),
            'total_clusters': len(clusters_info),
            'clusters': clusters_info,
            'patterns': patterns,
            'parsed_logs': all_parsed_logs,
            'parameters': {
                'depth': depth,
                'similarity_threshold': st,
                'max_children': max_children,
                'ignore_patterns': list(ignore_patterns),
                'multiline': multiline,
                'engine': 'drain3'
            }
        }

        write_raw_origin_outputs(storage, origin, origin_result, output_folder, 'drain3')

        summary_by_origin[origin] = {
            'files': len(files_for_origin),
            'total_clusters': len(clusters_info),
            'total_lines': total_lines,
            'ignored_lines': ignored_lines_count,
            'processed_lines': len(all_parsed_logs),
        }
        all_results[origin] = origin_result

    write_consolidated_summary(storage, output_folder, summary_by_origin, mode='drain3')

    return all_results


# ============================================================
# 3) DRAIN CUSTOM sobre logs YA PARSEADOS (parsed_logs/)
# ============================================================

def analyze_parsed_logs_with_drain(storage, origin: str,
                                    depth: int = 4,
                                    st: float = 0.5,
                                    parsed_folder: str = "parsed_logs",
                                    output_folder: str = "drain_parsed_results", 
                                    parsed_format: str = "parquet") -> Dict[str, Any]:
    """
    Análisis de logs ya parseados (Parquet o JSON) usando Drain CUSTOM, sobre el campo 'message'.

    Args:
        storage: backend de almacenamiento (local o S3)
        origin (str): origen de los logs a procesar
        depth (int): profundidad del árbol de Drain
        st (float): umbral de similitud para clustering
        parsed_folder (str): carpeta donde se encuentran los logs parseados
        output_folder (str): carpeta donde se guardarán los resultados
        parsed_format (str): formato de los logs parseados ('parquet' o 'json')

    Returns:
        Dict[str, Any]: resultados del análisis, incluyendo clusters y logs parseados
    """
    print(f"\n{'='*70}")
    print(f"DRAIN CUSTOM SOBRE LOGS PARSEADOS: {origin.upper()}")
    print(f"{'='*70}")
    print(f"Parámetros: depth={depth}, st={st}\n")

    records_with_message = load_parsed_logs_for_origin(storage, origin, parsed_folder, parsed_format)
    if not records_with_message:
        return {}

    print(f"✓ Mensajes válidos: {len(records_with_message)}")

    origin_config = load_config_for_origin(origin)
    ignore_patterns = origin_config['ignore_patterns']

    result = process_parsed_messages_with_drain(
        records_with_message, depth, st, origin_config, collect_records=True
    )
    records_with_message = result['records']
    clusters = result['clusters_info']
    total_processed = result['processed_count']
    cluster_stats = build_cluster_stats(clusters, total_processed)

    print(f"\n📊 Clusters descubiertos: {len(clusters)}")
    print_top_clusters(cluster_stats)

    summary = {
        'records_with_message': len(records_with_message),
        'processed_messages': total_processed,
        'ignored_messages': len(records_with_message) - total_processed,
        'total_clusters': len(clusters),
    }

    return write_parsed_analysis_outputs(
        storage, origin,
        engine='drain_custom_on_parsed_messages',
        parameters={'depth': depth, 'similarity_threshold': st},
        summary=summary,
        cluster_stats=cluster_stats,
        enriched_records=records_with_message,
        output_folder=output_folder,
        file_prefix='drain_parsed',
    )

# ============================================================
# 4) DRAIN3 (librería oficial) sobre logs YA PARSEADOS (parsed_logs/, Parquet)
# ============================================================
def load_parsed_logs_for_origin(
    storage,
    origin: str,
    parsed_folder: str = "parsed_logs",
    parsed_format: str = "parquet",
) -> List[Dict[str, Any]]:
    """
    Carga logs parseados desde ficheros Parquet o JSON, particionados
    por fecha, con nomenclatura '{year}_{month}_{day}_{origin}.<ext>'
    dentro de 'parsed_folder' (ver derive_parquet_path()/derive_json_path()).

    Args:
        parsed_format (str): 'parquet' (default) o 'json'. Determina la
            extensión buscada y el método de deserialización usado.

    Se listan todos los ficheros del formato indicado en 'parsed_folder'
    cuyo nombre termine en '_{origin}.<ext>', se reconstruyen a records
    y se concatenan en una única lista.
    """
    if parsed_format not in ("parquet", "json"):
        raise ValueError(f"parsed_format debe ser 'parquet' o 'json', recibido: '{parsed_format}'")

    extension = f".{parsed_format}"
    print(f"\n🔍 Cargando logs parseados ({parsed_format.upper()}) para origen: {origin}")

    all_files = storage.list_files(prefix=parsed_folder, extension=extension)

    suffix = f"_{origin}{extension}"
    origin_files = sorted(
        (fp, rp) for fp, rp in all_files
        if os.path.basename(rp).endswith(suffix)
    )

    if not origin_files:
        print(f"❌ No se encontraron ficheros {parsed_format.upper()} para origen '{origin}' en '{parsed_folder}/'")
        return []

    print(f"✓ {len(origin_files)} fichero(s) {parsed_format.upper()} encontrados para '{origin}'")

    records_with_message: List[Dict[str, Any]] = []
    for full_path, rel_path in origin_files:
        try:
            if parsed_format == "json":
                payload = storage.read_json(full_path)
                records = payload.get('records', []) if isinstance(payload, dict) else payload
            else:
                raw_bytes = storage.read_all_bytes(full_path)
                records = parquet_bytes_to_records(raw_bytes)

            records_with_message.extend(records)
            print(f"  ✓ {rel_path}: {len(records)} registros")
        except Exception as e:
            print(f"  ✗ Error leyendo {rel_path}: {e}")

    records_with_message = [
        r for r in records_with_message
        if r.get('message') and str(r['message']).strip()
    ]

    print(f"\n📊 Total mensajes cargados: {len(records_with_message)}")
    return records_with_message

def analyze_parsed_logs_with_drain3(
    storage, origin: str, depth: int = 5, st: float = 0.4, max_children: int = 100,
    parsed_folder: str = "parsed_logs", output_folder: str = "drain3_parsed_results",
    current_profile: str = None, auto_update_profile: bool = True,
    parsed_format: str = "parquet",
) -> Dict[str, Any]:
    """
    Análisis de logs ya parseados (Parquet o JSON) usando Drain3 (librería oficial),
    sobre el campo 'message'.

    Args:
        storage: backend de almacenamiento (local o S3)
        origin (str): origen de los logs a procesar
        depth (int): profundidad del árbol de Drain3
        st (float): umbral de similitud para clustering
        max_children (int): máximo número de hijos por nodo en Drain3
        parsed_folder (str): carpeta donde se encuentran los logs parseados
        output_folder (str): carpeta donde se guardarán los resultados
        current_profile (str): perfil DRAIN_CONFIG actual del origen, usado para comparación
        auto_update_profile (bool): si True, actualiza el perfil DRAIN_CONFIG si se encuentra uno mejor
        parsed_format (str): formato de los logs parseados ('parquet' o 'json')

    Returns:
        Dict[str, Any]: resultados del análisis, incluyendo clusters y logs parseados
    """
    print(f"\n{'='*70}")
    print(f"DRAIN3 SOBRE LOGS PARSEADOS: {origin.upper()}")
    print(f"{'='*70}")
    print(f"Parámetros: depth={depth}, st={st}, max_children={max_children}\n")

    records_with_message = load_parsed_logs_for_origin(storage, origin, parsed_folder, parsed_format)
    if not records_with_message:
        return {}

    print(f"✓ Mensajes válidos: {len(records_with_message)}")

    origin_config = load_config_for_origin(origin)
    ignore_patterns = origin_config['ignore_patterns']
    print(f"  ✓ Ignore patterns aplicados: {len(ignore_patterns)}")

    print(f"\n🔄 Procesando mensajes con Drain3...")
    result = process_parsed_messages_with_drain3(
        records_with_message, depth, st, max_children, origin_config, collect_records=True
    )
    records_with_message = result['records']
    clusters = result['clusters_info']

    examples_by_cluster = defaultdict(list)
    for r in records_with_message:
        cid = r.get('cluster_id')
        if len(examples_by_cluster[cid]) < 5:
            examples_by_cluster[cid].append(r.get('message', ''))

    cluster_stats = build_cluster_stats(clusters, len(records_with_message), examples_by_cluster)

    print(f"\n📊 Clusters descubiertos: {len(clusters)}")
    print_top_clusters(cluster_stats)

    summary = {
        'records_with_message': len(records_with_message),
        'total_clusters': len(clusters),
    }

    return write_parsed_analysis_outputs(
        storage, origin,
        engine='drain3_on_parsed_messages',
        parameters={
            'depth': depth, 'similarity_threshold': st, 'max_children': max_children,
            'used_profile': current_profile,
        },
        summary=summary,
        cluster_stats=cluster_stats,
        enriched_records=records_with_message,
        output_folder=output_folder,
        file_prefix='drain3_parsed',
    )

def main():
    parser = argparse.ArgumentParser(
        description="Suite unificada de clustering de logs: Drain custom, Drain3, y Drain custom sobre parsed_logs"
    )
    subparsers = parser.add_subparsers(dest='command', required=True)

    # --- Subcomando: drain (custom sobre logs crudos) ---
    p_drain = subparsers.add_parser('drain', help='Drain custom sobre logs crudos (.log)')
    p_drain.add_argument('--origin', type=str, default=None,
                          help='Origen(es) a procesar, separados por coma (ej: jde,alert_jde). Si se omite, usa --all')
    p_drain.add_argument('--all', action='store_true', help='Procesar todos los orígenes descubiertos')
    p_drain.add_argument('--folder', type=str, default='logs')
    p_drain.add_argument('--depth', type=int, default=4)
    p_drain.add_argument('--st', type=float, default=0.5)
    p_drain.add_argument('--no-remove-timestamps', action='store_true')
    p_drain.add_argument('--no-remove-numbers', action='store_true')
    p_drain.add_argument('--output', type=str, default='drain_results')

    # --- Subcomando: drain3 (oficial sobre logs crudos) ---
    p_drain3 = subparsers.add_parser('drain3', help='Drain3 (librería oficial) sobre logs crudos (.log)')
    p_drain3.add_argument('--origin', type=str, default=None,
                           help='Origen(es) a procesar, separados por coma (ej: jde,alert_jde). Si se omite, usa --all')
    p_drain3.add_argument('--all', action='store_true', help='Procesar todos los orígenes descubiertos')
    p_drain3.add_argument('--folder', type=str, default='logs')
    p_drain3.add_argument('--depth', type=int, default=4)
    p_drain3.add_argument('--st', type=float, default=0.5)
    p_drain3.add_argument('--max-children', type=int, default=100)
    p_drain3.add_argument('--output', type=str, default='drain3_results')
    p_drain3.add_argument('--no-persist', action='store_true')

    # --- Subcomando: parsed (custom sobre parsed_logs) ---
    p_parsed = subparsers.add_parser('parsed', help='Drain custom sobre logs ya parseados (parsed_logs/)')
    p_parsed.add_argument('--origin', type=str, default=None,
                           help='Origen(es) a procesar, separados por coma (ej: jde,alert_jde). Si se omite, usa --all')
    p_parsed.add_argument('--all', action='store_true', help='Procesar todos los orígenes descubiertos')
    p_parsed.add_argument('--depth', type=int, default=4)
    p_parsed.add_argument('--st', type=float, default=0.5)
    p_parsed.add_argument('--parsed-folder', type=str, default='parsed_logs')
    p_parsed.add_argument('--parsed-format', type=str, default='parquet',
                           choices=['parquet', 'json'],
                           help="Formato de los logs parseados a leer (default: parquet)")
    p_parsed.add_argument('--output', type=str, default='drain_parsed_results')

    # --- Subcomando: parsed3 (Drain3 oficial sobre parsed_logs, Parquet) ---
    p_parsed3 = subparsers.add_parser('parsed3', help='Drain3 sobre logs ya parseados (Parquet, parsed_logs/)')
    p_parsed3.add_argument('--origin', type=str, default=None,
                           help='Origen(es) a procesar, separados por coma (ej: jde,alert_jde). Si se omite, usa --all')
    p_parsed3.add_argument('--all', action='store_true', help='Procesar todos los orígenes descubiertos')
    p_parsed3.add_argument('--depth', type=int, default=None,
                            help='Si no se indica, se usa el perfil DRAIN_CONFIG del origen')
    p_parsed3.add_argument('--st', type=float, default=None)
    p_parsed3.add_argument('--max-children', type=int, default=None)
    p_parsed3.add_argument('--parsed-folder', type=str, default='parsed_logs')
    p_parsed3.add_argument('--parsed-format', type=str, default='parquet',
            choices=['parquet', 'json'],
            help="Formato de los logs parseados a leer (default: parquet)")
    p_parsed3.add_argument('--output', type=str, default='drain3_parsed_results')
    p_parsed3.add_argument('--no-auto-update', action='store_true')


    args = parser.parse_args()

    storage, execution_mode = get_storage_backend()
    print(f"🌐 Modo de ejecución: {execution_mode}")

    if args.command == 'drain':
        if not args.origin and not args.all:
            print("\n❌ Debes especificar --origin <nombre> o --all")
            return

        origin_filter = None if args.all else args.origin.split(',')

        analyze_logs_by_origin(
            storage, args.folder,
            depth=args.depth, st=args.st,
            remove_timestamps=not args.no_remove_timestamps,
            remove_numbers=not args.no_remove_numbers,
            output_folder=args.output,
            origin_filter=origin_filter,
        )

    elif args.command == 'drain3':
        if not args.origin and not args.all:
            print("\n❌ Debes especificar --origin <nombre> o --all")
            return

        origin_filter = None if args.all else args.origin.split(',')

        analyze_logs_by_origin_drain3(
            storage, args.folder,
            depth=args.depth, st=args.st,
            max_children=args.max_children,
            output_folder=args.output,
            persist_state=not args.no_persist,
            origin_filter=origin_filter,
        )
    
    elif args.command == 'parsed':
        if not args.origin and not args.all:
            print("\n❌ Debes especificar --origin <nombre> o --all")
            return

        origins_to_process = (
            detect_available_parsed_origins(storage, args.parsed_folder, args.parsed_format)
            if args.all else args.origin.split(',')
        )
        if not origins_to_process:
            print("❌ No se detectaron orígenes en la carpeta especificada")
            return

        print(f"\n📋 Orígenes a procesar: {', '.join(origins_to_process)}")
        print(f"{'='*70}\n")

        all_results = {}
        for origin in origins_to_process:
            try:
                result = analyze_parsed_logs_with_drain(
                    storage, origin=origin,
                    depth=args.depth, st=args.st,
                    parsed_folder=args.parsed_folder,
                    output_folder=args.output,
                    parsed_format=args.parsed_format,
                )
                if result:
                    all_results[origin] = result
            except Exception as e:
                print(f"\n❌ Error procesando origen '{origin}': {e}")
                import traceback
                traceback.print_exc()
                continue

        print(f"\n✅ Procesamiento completado: {len(all_results)}/{len(origins_to_process)} orígenes exitosos")

    elif args.command == 'parsed3':
        if not args.origin and not args.all:
            print("\n❌ Debes especificar --origin <nombre> o --all")
            return

        origins_to_process = (
            detect_available_parsed_origins(storage, args.parsed_folder, args.parsed_format)
            if args.all else args.origin.split(',')
        )
        if not origins_to_process:
            print("❌ No se detectaron orígenes en la carpeta especificada")
            return

        print(f"\n📋 Orígenes a procesar: {', '.join(origins_to_process)}")
        print(f"{'='*70}\n")

        all_results = {}
        for origin in origins_to_process:
            try:
                profile_params = get_drain_profile_params(origin)
                depth = args.depth if args.depth is not None else profile_params['depth']
                st = args.st if args.st is not None else profile_params['st']
                max_children = args.max_children if args.max_children is not None else profile_params['max_children']

                result = analyze_parsed_logs_with_drain3(
                    storage, origin=origin,
                    depth=depth, st=st, max_children=max_children,
                    parsed_folder=args.parsed_folder, output_folder=args.output,
                    current_profile=profile_params['profile'],
                    auto_update_profile=not args.no_auto_update,
                    parsed_format=args.parsed_format,
                )
                if result:
                    result['parameters']['drain_profile'] = profile_params['profile']
                    all_results[origin] = result
            except Exception as e:
                print(f"\n❌ Error procesando origen '{origin}': {e}")
                import traceback
                traceback.print_exc()
                continue

        if len(all_results) > 1:
            print(f"\n{'='*70}")
            print(f"RESUMEN CONSOLIDADO DE TODOS LOS ORÍGENES (Drain3)")
            print(f"{'='*70}")
            for origin, result in all_results.items():
                summary = result.get('summary', {})
                print(f"\n📁 {origin.upper()}")
                print(f"   Registros procesados: {summary.get('records_with_message', 0):,}")
                print(f"   Clusters generados: {summary.get('total_clusters', 0)}")

            summary_file = f"{args.output}/_all_origins_summary.json"
            storage.write_json(summary_file, {
                'analysis_date': datetime.now().isoformat(),
                'engine': 'drain3_on_parsed_messages',
                'origins_processed': list(all_results.keys()),
                'summaries': {o: r.get('summary', {}) for o, r in all_results.items()}
            })
            print(f"\n💾 Resumen consolidado guardado en: {summary_file}")

        print(f"\n✅ Procesamiento completado: {len(all_results)}/{len(origins_to_process)} orígenes exitosos")


if __name__ == "__main__":
    main()