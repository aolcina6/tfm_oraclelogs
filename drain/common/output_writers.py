"""
output_writers.py 

Escritura unificada de resultados de análisis de clustering sobre
parsed_logs/, usada tanto por Drain custom como por Drain3.
"""
from datetime import datetime
from typing import Dict, Any, List


def write_parsed_analysis_outputs(
    storage,
    origin: str,
    engine: str,
    parameters: Dict[str, Any],
    summary: Dict[str, Any],
    cluster_stats: List[Dict],
    enriched_records: List[Dict],
    output_folder: str,
    file_prefix: str,
    extra_top_level_fields: Dict[str, Any] = None,
) -> Dict[str, Any]:
    """
    Escribe los 3 ficheros de salida estándar de un análisis sobre
    parsed_logs/: JSON completo (con enriched_records), JSON solo de
    clusters, y CSV de clusters.

    Args:
        engine: identificador del motor ('drain_custom_on_parsed_messages'
            o 'drain3_on_parsed_messages').
        file_prefix: prefijo de fichero ('drain_parsed' o 'drain3_parsed').

    Returns:
        Dict[str, Any]: el objeto full_output escrito (para permitir
        seguir usándolo tras la llamada, ej. resumen consolidado).
    """
    extra_top_level_fields = extra_top_level_fields or {}
    output_path = f"{output_folder}/{origin}"
    analysis_date = datetime.now().isoformat()

    full_output = {
        'origin': origin,
        'analysis_date': analysis_date,
        'parameters': {**parameters, 'engine': engine},
        'summary': summary,
        'clusters': cluster_stats,
        'enriched_records': enriched_records,
        **extra_top_level_fields,
    }

    full_file = f"{output_path}/{origin}_{file_prefix}_full.json"
    storage.write_json(full_file, full_output)
    print(f"\n💾 Análisis completo guardado en: {full_file}")

    clusters_output = {
        'origin': origin,
        'analysis_date': analysis_date,
        'parameters': full_output['parameters'],
        'summary': summary,
        'clusters': cluster_stats,
        **extra_top_level_fields,
    }
    clusters_file = f"{output_path}/{origin}_{file_prefix}_clusters.json"
    storage.write_json(clusters_file, clusters_output)
    print(f"💾 Solo clusters guardado en: {clusters_file}")

    csv_lines = ["cluster_id,size,percentage,template"]
    for c in cluster_stats:
        csv_lines.append(f"{c['cluster_id']},{c['size']},{c['percentage']},\"{c['template']}\"")
    csv_content = '\n'.join(csv_lines)
    csv_file = f"{output_path}/{origin}_{file_prefix}_clusters.csv"
    storage.write_bytes(csv_file, csv_content.encode('utf-8'))
    print(f"💾 CSV de clusters guardado en: {csv_file}")

    return full_output

def write_raw_origin_outputs(storage, origin: str, origin_result: Dict, output_folder: str, engine_prefix: str):
    """Escribe {origin}_{engine}_analysis.json, {origin}_patterns.json,
    y además {origin}_{engine}_clusters.json/.csv en el MISMO formato
    que write_parsed_analysis_outputs, para poder comparar raw vs parsed
    directamente."""
    origin_folder = f"{output_folder}/{origin}"
    analysis_date = datetime.now().isoformat()

    output_file = f"{origin_folder}/{origin}_{engine_prefix}_analysis.json"
    storage.write_json(output_file, origin_result)
    print(f"\n💾 Análisis completo guardado en: {output_file}")

    total_processed = origin_result['processed_lines']

    # --- Normalización a formato "cluster_stats" común -------------
    # origin_result['patterns'] trae 'occurrences' (no 'size') y no
    # trae 'cluster_id' explícito -> lo generamos por posición.
    cluster_stats = [
        {
            'cluster_id': p.get('cluster_id', idx),
            'size': p['occurrences'],
            'percentage': round((p['occurrences'] / total_processed) * 100, 2) if total_processed else 0,
            'template': p['template'],
        }
        for idx, p in enumerate(origin_result['patterns'])
    ]

    # patterns.json
    patterns_file = f"{origin_folder}/{origin}_patterns.json"
    patterns_summary = {
        'origin': origin,
        'total_files': len(origin_result['files']),
        'total_lines': origin_result['total_lines'],
        'ignored_lines': origin_result['ignored_lines'],
        'processed_lines': total_processed,
        'total_clusters': origin_result['total_clusters'],
        'patterns': [
            {**p, 'percentage': round((p['occurrences'] / total_processed) * 100, 2) if total_processed else 0}
            for p in origin_result['patterns']
        ],
    }
    storage.write_json(patterns_file, patterns_summary)
    print(f"💾 Patrones guardados en: {patterns_file}")

    # clusters.json
    clusters_output = {
        'origin': origin,
        'analysis_date': analysis_date,
        'parameters': origin_result.get('parameters', {}),
        'summary': {
            'total_files': len(origin_result['files']),
            'total_lines': origin_result['total_lines'],
            'ignored_lines': origin_result['ignored_lines'],
            'processed_lines': total_processed,
            'total_clusters': origin_result['total_clusters'],
        },
        'clusters': cluster_stats,
    }
    clusters_file = f"{origin_folder}/{origin}_{engine_prefix}_clusters.json"
    storage.write_json(clusters_file, clusters_output)
    print(f"💾 Solo clusters guardado en: {clusters_file}")

    # clusters.csv
    csv_lines = ["cluster_id,size,percentage,template"]
    for c in cluster_stats:
        csv_lines.append(f"{c['cluster_id']},{c['size']},{c['percentage']},\"{c['template']}\"")
    csv_content = '\n'.join(csv_lines)
    csv_file = f"{origin_folder}/{origin}_{engine_prefix}_clusters.csv"
    storage.write_bytes(csv_file, csv_content.encode('utf-8'))
    print(f"💾 CSV de clusters guardado en: {csv_file}")


def write_consolidated_summary(storage, output_folder: str, summary_by_origin: Dict, mode: str):
    """Escribe _summary.json consolidado (formato compartido entre Drain custom y Drain3)."""
    print(f"\n{'='*60}")
    print(f"RESUMEN GENERAL CONSOLIDADO ({mode})")
    print(f"{'='*60}")
    for origin in sorted(summary_by_origin.keys()):
        s = summary_by_origin[origin]
        print(f"\n📁 {origin.upper()}")
        print(f"  Archivos: {s['files']} | Líneas: {s['total_lines']} | "
              f"Ignoradas: {s['ignored_lines']} | Clusters: {s['total_clusters']}")

    summary_file = f"{output_folder}/_summary.json"
    storage.write_json(summary_file, {
        'analysis_date': datetime.now().isoformat(),
        'mode': mode,
        'by_origin': summary_by_origin,
        'total_origins': len(summary_by_origin),
        'total_files': sum(s['files'] for s in summary_by_origin.values()),
        'total_lines': sum(s['total_lines'] for s in summary_by_origin.values()),
        'total_ignored_lines': sum(s['ignored_lines'] for s in summary_by_origin.values()),
        'total_processed_lines': sum(s['processed_lines'] for s in summary_by_origin.values()),
        'total_clusters_all': sum(s['total_clusters'] for s in summary_by_origin.values()),
    })
    print(f"\n💾 Resumen consolidado guardado en: {summary_file}")