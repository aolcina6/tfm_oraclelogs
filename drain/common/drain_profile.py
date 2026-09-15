"""
drain_profile.py 

Configuración de perfiles de Drain3 para evaluación automática.
Cada perfil es un diccionario con los parámetros de Drain3:
- depth: profundidad del árbol de Drain3.
- st: umbral de similitud para agrupar mensajes en un cluster.
- max_children: número máximo de hijos por nodo en el árbol de Drain3.
"""
import re
import os
import random
from typing import List, Dict, Any

from drain3 import TemplateMiner

from drain.common.cluster_metrics import (
    calculate_cluster_quality_metrics,
    extract_clusters_info,
)

from utils.log_detector import load_config_module

from drain.common.drain3_utils import (
    build_message_only_config,
)

DRAIN_PROFILES = {
    "very_strict": {"depth": 3, "st": 0.3, "max_children": 100},
    "strict_shallow": {"depth": 3, "st": 0.4, "max_children": 100},
    "balanced_shallow": {"depth": 3, "st": 0.5, "max_children": 100},
    "strict_medium": {"depth": 4, "st": 0.3, "max_children": 100},
    "balanced_medium": {"depth": 4, "st": 0.4, "max_children": 100},
    "baseline": {"depth": 4, "st": 0.5, "max_children": 100},
    "permissive_medium": {"depth": 4, "st": 0.6, "max_children": 150},
    "strict_deep": {"depth": 5, "st": 0.4, "max_children": 100},
    "deep": {"depth": 5, "st": 0.5, "max_children": 100},
    "permissive_deep": {"depth": 5, "st": 0.6, "max_children": 150},
    "very_deep": {"depth": 6, "st": 0.5, "max_children": 100},
}

DEFAULT_DRAIN_PROFILE = "permissive_medium"


def get_drain_profile_params(origin: str) -> Dict[str, Any]:
    """
    Carga el perfil de Drain (DRAIN_CONFIG) declarado en {origin}_config.py
    y devuelve sus parámetros (depth, st, max_children). 
    
    Args:
        origin (str): Nombre del origen de logs.
    
    Returns:
        Dict[str, Any]: Diccionario con los parámetros del perfil de Drain.
    Note: 
        Si el origen no declara DRAIN_CONFIG, o el valor no es un perfil reconocido, se usa
        DEFAULT_DRAIN_PROFILE ("permissive_medium").
    """
    profile_name = DEFAULT_DRAIN_PROFILE
    try:
        config_module = load_config_module(origin)
        declared_profile = getattr(config_module, 'DRAIN_CONFIG', None)
        if declared_profile:
            if declared_profile in DRAIN_PROFILES:
                profile_name = declared_profile
            else:
                print(f"  ⚠️  DRAIN_CONFIG='{declared_profile}' no reconocido en "
                      f"{origin}_config.py. Perfiles válidos: {list(DRAIN_PROFILES.keys())}. "
                      f"Usando '{DEFAULT_DRAIN_PROFILE}'.")
    except Exception as e:
        print(f"  ⚠️  Error cargando DRAIN_CONFIG para {origin}: {e}. "
              f"Usando perfil '{DEFAULT_DRAIN_PROFILE}'.")

    params = dict(DRAIN_PROFILES[profile_name])
    params['profile'] = profile_name
    print(f"  ✓ Perfil de Drain para '{origin}': {profile_name} "
          f"(depth={params['depth']}, st={params['st']}, max_children={params['max_children']})")
    return params
