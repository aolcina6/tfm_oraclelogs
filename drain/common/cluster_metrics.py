"""
cluster_metrics.py 

Módulo para calcular métricas de calidad de clusters y scoring de configuraciones de Drain y Drain3. 
"""
import math
import re
from typing import List, Dict, Any, Tuple

from drain3 import TemplateMiner


# ============================================================
# MÉTRICAS DE CALIDAD DE CLUSTERS (usadas por ambos benchmarkings)
# ============================================================
def calculate_cluster_quality_metrics(clusters: List[Dict]) -> Dict[str, float]:
    """
    Calcula métricas de calidad de clusters a partir de la lista de clusters.
    Args:
        clusters (List[Dict]): Lista de diccionarios con 'cluster_id', 'template' y 'size'.

    Returns:
        Dict[str, float]: Diccionario con métricas de calidad:
            - num_clusters
            - total_logs
            - entropy
            - top_10_coverage
            - top_20_coverage
            - avg_cluster_size
            - avg_wildcards_per_template
            - gini_coefficient
    """
    if not clusters:
        return {}

    total_logs = sum(c['size'] for c in clusters)
    if total_logs == 0:
        return {}

    probabilities = [c['size'] / total_logs for c in clusters]
    entropy = -sum(p * math.log2(p) for p in probabilities if p > 0)

    sorted_by_size = sorted(clusters, key=lambda x: x['size'], reverse=True)
    top_10_coverage = sum(c['size'] for c in sorted_by_size[:10]) / total_logs
    top_20_coverage = sum(c['size'] for c in sorted_by_size[:20]) / total_logs

    avg_cluster_size = total_logs / len(clusters)

    # Contar wildcards en ambos formatos (drain3 usa <*>, el Drain
    # custom usa '*' suelto y máscaras tipo ALPHANUM/NUM/IP/HEX sin <>)
    wildcard_pattern = re.compile(
        r'<\*>|(?<!\S)\*(?!\S)|\b(?:ALPHANUM|NUM|IP|HEX|UUID|PATH|LIBCODE|JDECODE|CONTEXT_ID)\b'
    )
    wildcard_counts = [
        len(wildcard_pattern.findall(c.get('template', ''))) for c in clusters
    ]
    avg_wildcards = sum(wildcard_counts) / len(wildcard_counts) if wildcard_counts else 0

    sizes = sorted(c['size'] for c in clusters)
    n = len(sizes)
    gini = (2 * sum((i + 1) * size for i, size in enumerate(sizes))) / (n * sum(sizes)) - (n + 1) / n if n > 0 else 0

    return {
        'num_clusters': len(clusters),
        'total_logs': total_logs,
        'entropy': round(entropy, 3),
        'top_10_coverage': round(top_10_coverage, 3),
        'top_20_coverage': round(top_20_coverage, 3),
        'avg_cluster_size': round(avg_cluster_size, 2),
        'avg_wildcards_per_template': round(avg_wildcards, 2),
        'gini_coefficient': round(gini, 3),
    }

def extract_clusters_info(template_miner: TemplateMiner) -> List[Dict]:
    """
    Extrae la lista de clusters (id, template, size) de un TemplateMiner.
    
    Args:
        template_miner (TemplateMiner): Instancia de TemplateMiner de Drain3.
    
    Returns:
        List[Dict]: Lista de diccionarios con 'cluster_id', 'template' y 'size'.
    """
    clusters = sorted(template_miner.drain.clusters, key=lambda c: c.size, reverse=True)
    return [
        {'cluster_id': c.cluster_id, 'template': c.get_template(), 'size': c.size}
        for c in clusters
    ]
