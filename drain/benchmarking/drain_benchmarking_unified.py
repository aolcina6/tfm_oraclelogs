"""
drain_benchmarking_unified.py 

Módulo unificado de benchmarking de parámetros para las 4 estrategias de
clustering de logs del proyecto:

1. benchmark_origin_drain()         -> Drain CUSTOM sobre logs crudos (.log)
2. benchmark_origin_drain3()        -> Drain3 (librería oficial) sobre logs crudos (.log)
3. benchmark_origin_parsed()        -> Drain CUSTOM sobre logs YA PARSEADOS (parsed_logs/)
4. benchmark_origin_parsed_drain3() -> Drain3 sobre logs YA PARSEADOS (parsed_logs/)
"""
import os
import sys
import argparse
import time
from datetime import datetime
from typing import Dict, List, Tuple, Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__)))) 

from storage.factory import get_storage_backend

from drain_unified import *
from drain.common.drain3_utils import (
    build_template_miner_config,
    build_message_only_config,
)
from drain.common import (
    find_files_for_origin,
    load_and_preprocess_lines,
)

from drain.common.origin_discovery import (
    detect_available_parsed_origins,
    discover_available_configs,
    load_config_for_origin,
)

from drain.common.cluster_metrics import (
    calculate_cluster_quality_metrics,
    extract_clusters_info,
)
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
# CONFIGURACIONES DE PRUEBA COMPARTIDAS
# ============================================================
# Nota: las variantes "raw" (drain / drain3) incluyen max_children porque
# TemplateMiner y Drain custom lo soportan como parámetro; la variante
# "parsed" no lo usa (mismo comportamiento que los scripts originales).

MAX_LINE_LENGTH_FOR_IGNORE_PATTERNS = 4000

QUICK_CONFIGS_RAW = [
    # (depth, st, max_children, label)
    (3, 0.4, 100, "strict_shallow"),
    (4, 0.5, 100, "baseline"),
    (4, 0.6, 150, "permissive"),
    (5, 0.5, 100, "deep"),
]

QUICK_CONFIGS_PARSED = [
    # (depth, st, max_children, label)
    (3, 0.4, 100, "strict_shallow"),
    (4, 0.5, 100, "baseline"),
    (4, 0.6, 150, "permissive"),
    (5, 0.5, 100, "deep"),
]

def _print_ranking(results: List[Dict], origin: str, engine_label: str):
    """
    Imprime una tabla comparativa de configuraciones con sus métricas de calidad
    (sin un score único: entropía, nº clusters, top-10 coverage, gini, wildcards).

    Args:
        results (List[Dict]): lista de resultados de benchmarking
        origin (str): nombre del origen de logs
        engine_label (str): etiqueta del motor de clustering (Drain custom, Drain3, etc.)

    Returns:
        None
    """
    print(f"\n{'='*90}")
    print(f"COMPARATIVA DE CONFIGURACIONES ({origin.upper()}) - {engine_label}")
    print(f"{'='*90}")
    print(f"{'Label':<20} {'Clusters':<10} {'Entropy':<10} {'Top-10':<10} {'Gini':<10} {'AvgWildc.':<10}")
    print(f"{'-'*90}")
    for res in results:
        qm = res['quality_metrics']
        print(f"{res['label']:<20} "
              f"{qm.get('num_clusters', 0):<10} "
              f"{qm.get('entropy', 0):<10.3f} "
              f"{qm.get('top_10_coverage', 0)*100:>6.1f}%    "
              f"{qm.get('gini_coefficient', 0):<10.3f} "
              f"{qm.get('avg_wildcards_per_template', 0):<10.2f}")


# ============================================================
# 1) BENCHMARK: DRAIN CUSTOM sobre logs crudos (.log)
# ============================================================

def benchmark_single_config_drain(
    lines_to_parse: List[str], total_lines: int, depth: int, st: float,
    max_children: int, label: str, origin_config: Dict,
) -> Dict[str, Any]:
    """
    Benchmark de una sola configuración de Drain custom sobre logs crudos.

    Args:
        lines_to_parse (List[str]): Líneas de log a procesar.
        total_lines (int): Número total de líneas originales.
        depth (int): Profundidad del árbol de Drain.
        st (float): Umbral de similitud para clustering.
        label (str): Etiqueta descriptiva de la configuración.
        origin_config (Dict): Configuración específica del origen.

    Returns:
        Dict[str, Any]: Diccionario con métricas de benchmarking y calidad.
    """
    print(f"\n  🧪 Probando: {label} (depth={depth}, st={st})")

    core_result = process_raw_lines_with_drain(
        lines_to_parse, total_lines, depth, st, origin_config,
        max_children=max_children, collect_records=False
    )

    normalized_clusters = [
        {'cluster_id': c['cluster_id'], 'template': c['template'], 'size': c['size']}
        for c in core_result['clusters_info']
    ]
    quality_metrics = calculate_cluster_quality_metrics(normalized_clusters)
    elapsed_time = core_result['elapsed_time_sec']
    processed_lines = core_result['processed_lines']

    result = {
        'label': label,
        'params': {'depth': depth, 'st': st},
        'stats': {
            'total_lines': total_lines,
            'ignored_lines': core_result['ignored_lines_count'],
            'processed_lines': processed_lines,
            'elapsed_time_sec': elapsed_time,
            'lines_per_sec': round(processed_lines / elapsed_time, 2) if elapsed_time > 0 else 0,
        },
        'quality_metrics': quality_metrics,
        'top_5_templates': [
            {'template': c['template'], 'size': c['size']}
            for c in sorted(normalized_clusters, key=lambda x: x['size'], reverse=True)[:5]
        ],
    }

    print(f"      ✓ Completado en {elapsed_time:.2f}s")
    print(f"        Clusters: {quality_metrics.get('num_clusters', 0)} | "
          f"Entropy: {quality_metrics.get('entropy', 0):.3f} | "
          f"Gini: {quality_metrics.get('gini_coefficient', 0):.3f} | "
          f"Avg wildcards: {quality_metrics.get('avg_wildcards_per_template', 0):.2f}")

    return result

def benchmark_origin_drain(
    storage,
    origin: str,
    configs: List[Tuple],
    output_folder: str = "drain_benchmarks"
) -> Dict[str, Any]:
    """
    Ejecuta Drain custom sobre logs crudos (.log) para un origen específico,
    probando múltiples configuraciones. 

    Args:
        storage: backend de almacenamiento
        origin (str): nombre del origen de logs
        configs (List[Tuple]): lista de configuraciones a probar
            (depth, st, label)
        output_folder (str): carpeta donde guardar los resultados

    Returns:    
        Dict[str, Any]: diccionario con resultados de benchmarking y métricas
    """
    print(f"\n{'='*70}")
    print(f"BENCHMARK DRAIN (custom): {origin.upper()}")
    print(f"{'='*70}")

    origin_files = find_files_for_origin(storage, origin, output_folder)
    if not origin_files:
        print(f"❌ No se encontraron archivos para el origen '{origin}'")
        return {}

    print(f"✓ Archivos a procesar: {len(origin_files)}")
    origin_config = load_config_for_origin(origin)

    print(f"📥 Leyendo y preprocesando ficheros (una sola vez para todas las configs)...")
    read_start = time.time()
    group_stats = {'multiline_groups': 0, 'continuation_lines': 0}
    lines_to_parse, total_lines = load_and_preprocess_lines(
        storage, origin_files, origin_config['multiline'],
        grouping_fn=(
            lambda lines: group_multiline_logs(
                lines, group_stats,
                origin_config['timestamp_patterns'],
                compiled_patterns=origin_config.get('compiled_patterns'),
            )
        ) if origin_config['multiline'] else None,
    )
    print(f"✓ {total_lines:,} líneas leídas en {time.time() - read_start:.2f}s")

    results = []
    for depth, st, _max_children, label in configs:
        result = benchmark_single_config_drain(lines_to_parse, total_lines, depth, st, label, origin_config)
        results.append(result)

    _print_ranking(results, origin, "DRAIN CUSTOM")

    benchmark_result = {
        'origin': origin,
        'benchmark_date': datetime.now().isoformat(),
        'engine': 'drain_custom',
        'total_files': len(origin_files),
        'configurations_tested': len(configs),
        'results': results,
    }

    output_file = f"{output_folder}/{origin}_benchmark_drain.json"
    storage.write_json(output_file, benchmark_result)
    print(f"\n💾 Informe completo guardado en: {output_file}")

    return benchmark_result


# ============================================================
# 2) BENCHMARK: DRAIN3 (oficial) sobre logs crudos (.log)
# ============================================================

def benchmark_single_config_drain3(
    lines_to_parse: List[str], total_lines: int, depth: int, st: float,
    max_children: int, label: str, origin_config: Dict,
) -> Dict[str, Any]:
    """
    Benchmark de una sola configuración de Drain3 sobre logs crudos.

    Args:
        lines_to_parse (List[str]): Líneas de log a procesar.
        total_lines (int): Número total de líneas originales.
        depth (int): Profundidad del árbol de Drain3.
        st (float): Umbral de similitud para clustering.
        max_children (int): Máximo número de hijos por nodo en el árbol.
        label (str): Etiqueta descriptiva de la configuración.
        origin_config (Dict): Configuración específica del origen.

    Returns:
        Dict[str, Any]: Diccionario con métricas de benchmarking y calidad.
    """
    print(f"\n  🧪 Probando: {label} (depth={depth}, st={st}, max_children={max_children})")

    core_result = process_raw_lines_with_drain3(
        lines_to_parse, total_lines, depth, st, max_children,
        origin_config, persistence=None, collect_records=False
    )

    normalized_clusters = core_result['clusters_info']
    quality_metrics = calculate_cluster_quality_metrics(normalized_clusters)
    elapsed_time = core_result['elapsed_time_sec']
    processed_lines = core_result['processed_lines']

    result = {
        'label': label,
        'params': {'depth': depth, 'st': st, 'max_children': max_children},
        'stats': {
            'total_lines': total_lines,
            'ignored_lines': core_result['ignored_lines_count'],
            'processed_lines': processed_lines,
            'elapsed_time_sec': elapsed_time,
            'lines_per_sec': round(processed_lines / elapsed_time, 2) if elapsed_time > 0 else 0,
        },
        'quality_metrics': quality_metrics,
        'top_5_templates': [
            {'template': c['template'], 'size': c['size']}
            for c in sorted(normalized_clusters, key=lambda x: x['size'], reverse=True)[:5]
        ],
    }

    print(f"      ✓ Completado en {elapsed_time:.2f}s")
    print(f"        Clusters: {quality_metrics['num_clusters']} | "
          f"Entropy: {quality_metrics.get('entropy', 0):.3f} | "
          f"Gini: {quality_metrics.get('gini_coefficient', 0):.3f} | "
          f"Avg wildcards: {quality_metrics.get('avg_wildcards_per_template', 0):.2f}")

    return result


def benchmark_origin_drain3(
    storage,
    origin: str,
    configs: List[Tuple],
    output_folder: str = "drain3_benchmarks"
) -> Dict[str, Any]:
    """
    Ejecuta Drain3 sobre logs crudos (.log). Sin selección automática de "mejor" config.

    Args:
        storage: backend de almacenamiento
        origin (str): nombre del origen de logs
        configs (List[Tuple]): lista de configuraciones a probar
            (depth, st, max_children, label)
        output_folder (str): carpeta donde guardar los resultados

    Returns:
        Dict[str, Any]: diccionario con resultados de benchmarking y métricas
    """
    print(f"\n{'='*70}")
    print(f"BENCHMARK: {origin.upper()} (Drain3)")
    print(f"{'='*70}")

    origin_files = find_files_for_origin(storage, origin, output_folder)
    if not origin_files:
        print(f"❌ No se encontraron archivos para el origen '{origin}'")
        return {}

    print(f"✓ Archivos a procesar: {len(origin_files)}")
    origin_config = load_config_for_origin(origin)

    print(f"📥 Leyendo y preprocesando ficheros (una sola vez para todas las configs)...")
    read_start = time.time()
    group_stats = {'multiline_groups': 0, 'continuation_lines': 0}
    lines_to_parse, total_lines = load_and_preprocess_lines(
        storage, origin_files, origin_config['multiline'],
        grouping_fn=(
            lambda lines: group_multiline_logs(
                lines, group_stats,
                origin_config['timestamp_patterns'],
                compiled_patterns=origin_config.get('compiled_patterns'),
            )
        ) if origin_config['multiline'] else None,
    )
    print(f"✓ {total_lines:,} líneas leídas en {time.time() - read_start:.2f}s")

    results = []
    for depth, st, max_children, label in configs:
        result = benchmark_single_config_drain3(
            lines_to_parse, total_lines, depth, st, max_children, label, origin_config
        )
        results.append(result)

    _print_ranking(results, origin, "DRAIN3")

    benchmark_result = {
        'origin': origin,
        'benchmark_date': datetime.now().isoformat(),
        'engine': 'drain3',
        'total_files': len(origin_files),
        'configurations_tested': len(configs),
        'results': results,
    }

    output_file = f"{output_folder}/{origin}_benchmark.json"
    storage.write_json(output_file, benchmark_result)
    print(f"\n💾 Informe completo guardado en: {output_file}")

    return benchmark_result



# ============================================================
# 3) BENCHMARK: DRAIN CUSTOM sobre logs YA PARSEADOS
# ============================================================

def benchmark_single_config_parsed(
    messages: List[str], depth: int, st: float, max_children: int, label: str,
    origin_config: Dict,
) -> Dict[str, Any]:
    """
    Benchmark de una sola configuración de Drain custom sobre logs YA PARSEADOS.

    Args:
        messages (List[str]): Mensajes parseados a procesar.
        depth (int): Profundidad del árbol de Drain.
        st (float): Umbral de similitud para clustering.
        label (str): Etiqueta descriptiva de la configuración.
        origin_config (Dict): Configuración específica del origen.

    Returns:
        Dict[str, Any]: Diccionario con métricas de benchmarking y calidad.
    """
    print(f"\n  🧪 Probando: {label} (depth={depth}, st={st})")

    fake_records = [{'message': m} for m in messages if m and m.strip()]
    core_result = process_parsed_messages_with_drain(
        fake_records, depth, st, origin_config, max_children=max_children, collect_records=False
    )

    normalized_clusters = [
        {'cluster_id': c['cluster_id'], 'template': c['template'], 'size': c['size']}
        for c in core_result['clusters_info']
    ]
    quality_metrics = calculate_cluster_quality_metrics(normalized_clusters)
    elapsed_time = core_result['elapsed_time_sec']
    processed = core_result['processed_count']

    result = {
        'label': label,
        'params': {'depth': depth, 'st': st, 'max_children': max_children},
        'stats': {
            'total_messages': len(messages),
            'ignored_messages': core_result['ignored_count'],
            'processed_messages': processed,
            'elapsed_time_sec': elapsed_time,
            'messages_per_sec': round(processed / elapsed_time, 2) if elapsed_time > 0 else 0,
        },
        'quality_metrics': quality_metrics,
        'top_5_templates': [
            {'template': c['template'], 'size': c['size']}
            for c in sorted(normalized_clusters, key=lambda x: x['size'], reverse=True)[:5]
        ],
    }

    print(f"      ✓ Completado en {elapsed_time:.2f}s")
    print(f"        Clusters: {quality_metrics.get('num_clusters', 0)} | "
          f"Entropy: {quality_metrics.get('entropy', 0):.3f} | "
          f"Gini: {quality_metrics.get('gini_coefficient', 0):.3f} | "
          f"Avg wildcards: {quality_metrics.get('avg_wildcards_per_template', 0):.2f}")

    return result


def benchmark_origin_parsed(
    storage,
    origin: str,
    configs: List[Tuple],
    parsed_folder: str = "parsed_logs",
    output_folder: str = "drain_benchmarks_parsed",
    parsed_format: str = "parquet",
) -> Dict[str, Any]:
    """
    Ejecuta Drain custom sobre logs YA PARSEADOS. 
    
    Args:
        storage: backend de almacenamiento
        origin (str): nombre del origen de logs
        configs (List[Tuple]): lista de configuraciones a probar
            (depth, st, label)
        parsed_folder (str): carpeta donde se encuentran los logs parseados
        output_folder (str): carpeta donde guardar los resultados
        parsed_format (str): formato de los logs parseados ('parquet', 'json', etc.)

    Returns:
        Dict[str, Any]: diccionario con resultados de benchmarking y métricas
    """
    print(f"\n{'='*70}")
    print(f"BENCHMARK DRAIN CUSTOM SOBRE LOGS PARSEADOS: {origin.upper()}")
    print(f"{'='*70}")

    records = load_parsed_logs_for_origin(storage, origin, parsed_folder, parsed_format)
    if not records:
        print(f"❌ No se encontraron mensajes parseados para el origen '{origin}'")
        return {}

    messages = [r['message'] for r in records]
    print(f"✓ Mensajes a procesar: {len(messages):,}")

    origin_config = load_config_for_origin(origin)

    results = []
    for depth, st, max_children, label in configs:
        result = benchmark_single_config_parsed(messages, depth, st, max_children, label, origin_config)
        results.append(result)

    _print_ranking(results, origin, "DRAIN CUSTOM SOBRE PARSED")

    benchmark_result = {
        'origin': origin,
        'benchmark_date': datetime.now().isoformat(),
        'engine': 'drain_custom_on_parsed_messages',
        'total_messages': len(messages),
        'configurations_tested': len(configs),
        'results': results,
    }

    output_file = f"{output_folder}/{origin}_benchmark_drain_parsed.json"
    storage.write_json(output_file, benchmark_result)
    print(f"\n💾 Informe completo guardado en: {output_file}")

    return benchmark_result


# ============================================================
# 4) BENCHMARK: DRAIN3 (oficial) sobre logs YA PARSEADOS
# ============================================================

def benchmark_single_config_parsed_drain3(
    messages: List[str], total_lines: int, depth: int, st: float,
    max_children: int, label: str, origin_config: Dict,
) -> Dict[str, Any]:
    """
    Benchmark de una sola configuración de Drain3 sobre logs YA PARSEADOS.

    Args:
        messages (List[str]): Mensajes parseados a procesar.
        total_lines (int): Número total de mensajes originales.
        depth (int): Profundidad del árbol de Drain3.
        st (float): Umbral de similitud para clustering.
        max_children (int): Máximo número de hijos por nodo en el árbol.
        label (str): Etiqueta descriptiva de la configuración.
        origin_config (Dict): Configuración específica del origen.

    Returns:
        Dict[str, Any]: Diccionario con métricas de benchmarking y calidad.
    """
    print(f"\n  🧪 Probando: {label} (depth={depth}, st={st}, max_children={max_children})")

    fake_records = [{'message': m} for m in messages]
    core_result = process_parsed_messages_with_drain3(
        fake_records, depth, st, max_children, origin_config, collect_records=False
    )

    normalized_clusters = core_result['clusters_info']
    quality_metrics = calculate_cluster_quality_metrics(normalized_clusters)
    elapsed_time = core_result['elapsed_time_sec']
    processed_lines = core_result['processed_count']

    result = {
        'label': label,
        'params': {'depth': depth, 'st': st, 'max_children': max_children},
        'stats': {
            'total_lines': total_lines,
            'ignored_lines': core_result['ignored_count'],
            'processed_lines': processed_lines,
            'elapsed_time_sec': elapsed_time,
            'lines_per_sec': round(processed_lines / elapsed_time, 2) if elapsed_time > 0 else 0,
        },
        'quality_metrics': quality_metrics,
        'top_5_templates': [
            {'template': c['template'], 'size': c['size']}
            for c in sorted(normalized_clusters, key=lambda x: x['size'], reverse=True)[:5]
        ],
    }

    print(f"      ✓ Completado en {elapsed_time:.2f}s")
    print(f"        Clusters: {quality_metrics['num_clusters']} | "
          f"Entropy: {quality_metrics.get('entropy', 0):.3f} | "
          f"Gini: {quality_metrics.get('gini_coefficient', 0):.3f} | "
          f"Avg wildcards: {quality_metrics.get('avg_wildcards_per_template', 0):.2f}")

    return result

def benchmark_origin_parsed_drain3(
    storage,
    origin: str,
    configs: List[Tuple],
    parsed_folder: str = "parsed_logs",
    output_folder: str = "drain3_benchmarks_parsed",
    parsed_format: str = "parquet",
) -> Dict[str, Any]:
    """
    Ejecuta Drain3 sobre logs YA PARSEADOS.

    Args:
        storage: backend de almacenamiento
        origin (str): nombre del origen de logs
        configs (List[Tuple]): lista de configuraciones a probar
            (depth, st, max_children, label)
        parsed_folder (str): carpeta donde se encuentran los logs parseados
        output_folder (str): carpeta donde guardar los resultados
        parsed_format (str): formato de los logs parseados ('parquet', 'json', etc.)

    Returns:
        Dict[str, Any]: diccionario con resultados de benchmarking y métricas
    """
    print(f"\n{'='*70}")
    print(f"BENCHMARK DRAIN3 SOBRE LOGS PARSEADOS: {origin.upper()}")
    print(f"{'='*70}")

    records = load_parsed_logs_for_origin(storage, origin, parsed_folder, parsed_format)
    if not records:
        print(f"❌ No se encontraron mensajes parseados para el origen '{origin}'")
        return {}

    messages = [r['message'] for r in records]
    print(f"✓ Mensajes a procesar: {len(messages):,}")

    origin_config = load_config_for_origin(origin)

    results = []
    for depth, st, max_children, label in configs:
        result = benchmark_single_config_parsed_drain3(
            messages, len(messages), depth, st, max_children, label, origin_config
        )
        results.append(result)

    _print_ranking(results, origin, "DRAIN3 SOBRE PARSED")

    benchmark_result = {
        'origin': origin,
        'benchmark_date': datetime.now().isoformat(),
        'engine': 'drain3_on_parsed_messages',
        'total_messages': len(messages),
        'configurations_tested': len(configs),
        'results': results,
    }

    output_file = f"{output_folder}/{origin}_benchmark_parsed.json"
    storage.write_json(output_file, benchmark_result)
    print(f"\n💾 Informe completo guardado en: {output_file}")

    return benchmark_result

# ============================================================
#                       GENERAL
# ============================================================

def _run_and_summarize(
    storage,
    engine_key: str,
    benchmark_fn,
    origins: List[str],
    configs: List[Tuple],
    output_folder: str,
    summary_suffix: str,
    extra_kwargs: Dict = None,
) -> Dict[str, Any]:
    """
    Ejecuta un benchmark para múltiples orígenes y consolida sus métricas.
    Ya no existe un "best_config" automático: el resumen incluye, por origen
    y configuración, las métricas crudas (entropy, num_clusters, gini,
    avg_wildcards_per_template) para que la comparación/decisión sea manual.
    """
    extra_kwargs = extra_kwargs or {}
    all_results = {}

    for origin in origins:
        try:
            result = benchmark_fn(
                storage=storage, origin=origin, configs=configs,
                output_folder=output_folder, **extra_kwargs
            )
            if result:
                all_results[origin] = result
        except Exception as e:
            print(f"\n❌ Error procesando origen '{origin}': {e}")
            import traceback
            traceback.print_exc()
            continue

    if len(all_results) > 1:
        print(f"\n{'='*70}")
        print(f"RESUMEN CONSOLIDADO")
        print(f"{'='*70}")
        for origin, result in all_results.items():
            print(f"\n📁 {origin.upper()}")
            for res in result['results']:
                qm = res['quality_metrics']
                print(f"   {res['label']:<20} clusters={qm.get('num_clusters', 0):<6} "
                      f"entropy={qm.get('entropy', 0):.3f} "
                      f"gini={qm.get('gini_coefficient', 0):.3f} "
                      f"avg_wildcards={qm.get('avg_wildcards_per_template', 0):.2f}")

        summary_file = f"{output_folder}/{summary_suffix}"
        storage.write_json(summary_file, {
            'benchmark_date': datetime.now().isoformat(),
            'engine': engine_key,
            'origins_tested': list(all_results.keys()),
            'metrics_by_origin': {
                o: [
                    {'label': res['label'], 'params': res['params'], 'quality_metrics': res['quality_metrics']}
                    for res in r['results']
                ]
                for o, r in all_results.items()
            },
        })
        print(f"\n💾 Resumen consolidado guardado en: {summary_file}")

    return all_results

def main():
    parser = argparse.ArgumentParser(
        description="Suite unificada de benchmarking de parámetros: Drain custom, Drain3, y Drain custom sobre parsed_logs"
    )
    subparsers = parser.add_subparsers(dest='command', required=True)

    p_drain = subparsers.add_parser('drain', help='Benchmark de Drain custom sobre logs crudos (.log)')
    p_drain.add_argument('--origin', type=str)
    p_drain.add_argument('--all', action='store_true')
    p_drain.add_argument('--output', type=str, default='drain_benchmarks')

    p_drain3 = subparsers.add_parser('drain3', help='Benchmark de Drain3 sobre logs crudos (.log)')
    p_drain3.add_argument('--origin', type=str)
    p_drain3.add_argument('--all', action='store_true')
    p_drain3.add_argument('--output', type=str, default='drain3_benchmarks')

    p_parsed = subparsers.add_parser('parsed', help='Benchmark de Drain custom sobre logs ya parseados (parsed_logs/)')
    p_parsed.add_argument('--origin', type=str)
    p_parsed.add_argument('--all', action='store_true')
    p_parsed.add_argument('--parsed-folder', type=str, default='parsed_logs')
    p_parsed.add_argument('--parsed-format', type=str, default='parquet',
                           choices=['parquet', 'json'],
                           help="Formato de los logs parseados a leer (default: parquet)")
    p_parsed.add_argument('--output', type=str, default='drain_benchmarks_parsed')

    p_parsed3 = subparsers.add_parser('parsed3', help='Benchmark de Drain3 sobre logs ya parseados (parsed_logs/)')
    p_parsed3.add_argument('--origin', type=str)
    p_parsed3.add_argument('--all', action='store_true')
    p_parsed3.add_argument('--parsed-folder', type=str, default='parsed_logs')
    p_parsed3.add_argument('--parsed-format', type=str, default='parquet',
                            choices=['parquet', 'json'],
                            help="Formato de los logs parseados a leer (default: parquet)")
    p_parsed3.add_argument('--output', type=str, default='drain3_benchmarks_parsed')

    args = parser.parse_args()

    storage, execution_mode = get_storage_backend()
    print(f"🌐 Modo de ejecución: {execution_mode}\n")

    if not args.origin and not args.all:
        print("❌ Debes especificar --origin <nombre> o --all")
        return

    if args.command in ('drain', 'drain3'):
        configs = QUICK_CONFIGS_RAW

        origins = discover_available_configs() if args.all else [args.origin]
        if not origins:
            print("❌ No se encontraron orígenes configurados")
            return

        if args.command == 'drain':
            benchmark_fn, engine_key, suffix = benchmark_origin_drain, 'drain_custom', '_benchmark_summary_drain.json'
        else:
            benchmark_fn, engine_key, suffix = benchmark_origin_drain3, 'drain3', '_benchmark_summary.json'

        _run_and_summarize(storage, engine_key, benchmark_fn, origins, configs, args.output, suffix)

    elif args.command == 'parsed':
        configs = QUICK_CONFIGS_PARSED

        origins = (
            detect_available_parsed_origins(storage, args.parsed_folder, args.parsed_format)
            if args.all else [args.origin]
        )
        if not origins:
            print("❌ No se detectaron orígenes para procesar")
            return

        _run_and_summarize(
            storage, 'drain_custom_on_parsed_messages', benchmark_origin_parsed,
            origins, configs, args.output, '_benchmark_summary_drain_parsed.json',
            extra_kwargs={'parsed_folder': args.parsed_folder, 'parsed_format': args.parsed_format},
        )

    elif args.command == 'parsed3':
        configs = QUICK_CONFIGS_RAW

        origins = (
            detect_available_parsed_origins(storage, args.parsed_folder, args.parsed_format)
            if args.all else [args.origin]
        )
        if not origins:
            print("❌ No se detectaron orígenes para procesar")
            return

        _run_and_summarize(
            storage, 'drain3_on_parsed_messages', benchmark_origin_parsed_drain3,
            origins, configs, args.output, '_benchmark_summary_parsed.json',
            extra_kwargs={'parsed_folder': args.parsed_folder, 'parsed_format': args.parsed_format},
        )


if __name__ == "__main__":
    main()