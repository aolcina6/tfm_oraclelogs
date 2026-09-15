"""
enrichment.py

Etapas de enriquecimiento aplicadas a los registros ya parseados:
normalización de timestamps, extractores, componente por defecto,
mapeo de nivel de log y clasificación contra templates (event_type/severity).
"""
from utils.utils import (
    normalize_records,
    apply_extractors,
    apply_default_component,
    apply_level_mapping,
    apply_implicit_level,
)
from config.general_config import IMPLICIT_LEVEL_PATTERNS
from parsing.template_classifier import classify_records, _load_regex_groups_cached
from .debug_utils import debug_print


def enrich_records(result, log_type):
    """
    Aplica, en orden, todas las etapas de enriquecimiento sobre
    result['records'], mutando y devolviendo el propio 'result'.

    Args:
        result (dict): Resultado del parseo (con 'records' y '_internal_config'/'config').
        log_type (str): Tipo de log detectado.

    Returns:
        tuple: (result actualizado, template_unmatched)
    """
    print(f"\n🔄 Normalizando timestamps...")
    ts_patterns = (
        result.get('_internal_config', {}).get('timestamp_patterns')
        or result.get('config', {}).get('timestamp_patterns', None)
    )
    result['records'], norm_stats = normalize_records(result['records'], ts_patterns)
    result['normalization_stats'] = norm_stats

    print(f"\n🔎 Aplicando extractores...")
    extractor_patterns = (
        result.get('_internal_config', {}).get('extractors')
        or result.get('config', {}).get('extractors', None)
    )
    result['records'] = apply_extractors(result['records'], extractor_patterns)

    default_component = (
        result.get('_internal_config', {}).get('default_component')
        or result.get('config', {}).get('default_component', None)
    )
    result['records'] = apply_default_component(result['records'], default_component)

    level_mapping = (
        result.get('_internal_config', {}).get('level_mapping')
        or result.get('config', {}).get('level_mapping', None)
    )
    result['records'] = apply_level_mapping(result['records'], level_mapping)

    result['records'] = apply_implicit_level(result['records'], IMPLICIT_LEVEL_PATTERNS)

    print(f"\n🏷️  Clasificando contra templates ({log_type})...")
    debug_groups = _load_regex_groups_cached(log_type)

    result['records'] = classify_records(result['records'], log_type)
    
    return result