"""
template_classifier.py 

Clasifica registros de logs según plantillas predefinidas para cada tipo de log.
"""
import os
import json
import re
from functools import lru_cache

TEMPLATES_FOLDER = "templates"


@lru_cache(maxsize=None)
def _load_regex_groups_cached(log_type: str, templates_folder: str = TEMPLATES_FOLDER):
    """
    Carga y compila el fichero '{log_type}_template_regex.json' (una única vez).

    Args:
        log_type (str): Tipo de log (ejemplo: 'e1root').
        templates_folder (str): Carpeta donde se encuentran los ficheros de templates.

    Returns:
        list: Lista de tuplas (group_id, compiled_regex, event_type, severity) para los grupos revisados.
        None: Si no se encuentra el fichero de templates para el log_type.
    """
    path = os.path.join(templates_folder, f"{log_type}_template_regex.json")
    if not os.path.exists(path):
        print(f"  ℹ️  No hay templates_regex para '{log_type}' (se esperaba: {path})")
        return None

    with open(path, encoding='utf-8') as f:
        data = json.load(f)

    compiled = []
    skipped_incomplete = 0

    for group in data.get('groups', []):
        event_type = group.get('event_type')
        severity = group.get('severity')

        # Filtro clave: solo grupos ya revisados manualmente
        if event_type is None or severity is None:
            skipped_incomplete += 1
            continue

        pattern = group.get('pattern')
        if not pattern:
            continue

        try:
            regex = re.compile(pattern, group.get('flags', 0))
            compiled.append((
                group.get('group_id'),
                regex,
                event_type,
                severity,
            ))
        except re.error as e:
            print(f"  ⚠️  Regex inválida en group_id {group.get('group_id')} de {log_type}: {e}")

    print(f"  ✓ {len(compiled)} grupo(s) clasificables cargados para '{log_type}' "
          f"({skipped_incomplete} sin revisar, omitidos)")
    return compiled


def clear_templates_cache():
    """Limpia la caché de templates (útil si se regeneran en caliente)."""
    _load_regex_groups_cached.cache_clear()


def classify_records(records: list, log_type: str, templates_folder: str = TEMPLATES_FOLDER) -> tuple:
    """
    Clasifica cada record contra los grupos ya revisados (event_type +
    severity no nulos) para ese log_type, añadiendo 'event_type' y
    'severity' cuando hay match.

    Args:
        records (list): Lista de registros a clasificar.
        log_type (str): Tipo de log (ejemplo: 'e1root').
        templates_folder (str): Carpeta donde se encuentran los ficheros de templates.

    Returns:
        list: Lista de registros clasificados (con event_type y severity añadidos cuando hay match).
        list: Lista de registros que no matchean con ningún grupo revisado, para posible uso en learning queue.
    """
    compiled_groups = _load_regex_groups_cached(log_type, templates_folder)

    # Si no hay grupos revisados para este origen, no se puede
    # clasificar: se deja tal cual y no se generan entradas de learning queue
    if not compiled_groups:
        return records

    unmatched = []

    for record in records:
        message = record.get('message', '') or ''

        matched = False
        for group_id, regex, event_type, severity in compiled_groups:
            if regex.match(message):
                record['event_type'] = event_type
                record['severity'] = severity
                record['template_group_id'] = group_id
                matched = True
                break

        if not matched:
            unmatched.append({
                'timestamp': record.get('timestamp'),
                'message': message,
                'reason': 'NO_TEMPLATE_DEFINED',
            })

    return records