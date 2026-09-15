"""
cluster_output.py 

Extracción y reporting de clusters, unificado para las 4 implementaciones
de Drain del proyecto (custom raw, drain3 raw, custom parsed, drain3 parsed).
"""
from typing import List, Dict, Any


def extract_clusters_from_drain3(template_miner) -> List[Dict]:
    """
    Extrae clusters de un TemplateMiner (Drain3), ordenados por tamaño desc.
    
    Args:
        template_miner: Instancia de TemplateMiner de Drain3.
    
    Returns:
        List[Dict]: Lista de diccionarios con información de cada cluster:
            - cluster_id: ID del cluster.
            - template: Plantilla del cluster.
            - size: Tamaño del cluster (número de logs).
    """
    clusters = sorted(template_miner.drain.clusters, key=lambda c: c.size, reverse=True)
    return [
        {'cluster_id': c.cluster_id, 'template': c.get_template(), 'size': c.size}
        for c in clusters
    ]


def extract_clusters_from_custom_drain(drain) -> List[Dict]:
    """
    Extrae clusters de una instancia de Drain custom, ordenados por tamaño desc.
    
    Args:
        drain: Instancia de Drain custom.

    Returns:
        List[Dict]: Lista de diccionarios con información de cada cluster:
            - cluster_id: ID del cluster.
            - template: Plantilla del cluster.
            - size: Tamaño del cluster (número de logs).
    """
    clusters = drain.get_clusters_info()
    return sorted(clusters, key=lambda c: c['size'], reverse=True)


def build_cluster_stats(clusters: List[Dict], total_processed: int, examples_by_cluster: Dict = None) -> List[Dict]:
    """
    Construye la lista final de estadísticas de cluster con porcentaje y
    ejemplos, formato usado por los 4 análisis "sobre parsed_logs" y por
    el reporting de patrones sobre logs crudos.

    Args:
        clusters (List[Dict]): Lista de clusters con información básica.
        total_processed (int): Número total de logs procesados.
        examples_by_cluster (Dict, optional): Diccionario con ejemplos por cluster_id.

    Returns:
        List[Dict]: Lista de diccionarios con estadísticas de cada cluster:
            - cluster_id: ID del cluster.
            - template: Plantilla del cluster.
            - size: Tamaño del cluster (número de logs).
            - percentage: Porcentaje del total de logs procesados.
            - examples: Lista de ejemplos (máx. 5) para el cluster.
    """
    examples_by_cluster = examples_by_cluster or {}
    stats = []
    for c in clusters:
        percentage = round((c['size'] / total_processed) * 100, 2) if total_processed else 0
        stats.append({
            'cluster_id': c['cluster_id'],
            'template': c['template'],
            'size': c['size'],
            'percentage': percentage,
            'examples': c.get('examples') or examples_by_cluster.get(c['cluster_id'], [])[:5],
        })
    return stats


def print_top_clusters(cluster_stats: List[Dict], top_n: int = 10):
    """
    Imprime tabla de los top-N clusters más frecuentes (formato unificado).
    
    Args:
        cluster_stats (List[Dict]): Lista de estadísticas de clusters.
        top_n (int): Número de clusters a mostrar.

    Returns:
        None
    """
    print(f"\n📊 Top {top_n} clusters más frecuentes:\n")
    print(f"{'#':<4} {'Size':<8} {'%':<8} {'Template':<60}")
    print(f"{'-'*80}")
    for i, cluster in enumerate(cluster_stats[:top_n], 1):
        print(f"{i:<4} {cluster['size']:<8} {cluster['percentage']:<7.2f}% {cluster['template'][:60]}")