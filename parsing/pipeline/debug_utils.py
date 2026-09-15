"""
debug_utils.py

Utilidad centralizada para los prints de depuración relacionados con
el pipeline de event_type/severity (bug en investigación: registros
'jde' sin event_type tras classify_records/merge). Activar con:

    DEBUG_EVENT_TYPES=1 python parsing/init.py
"""
import os

DEBUG_EVENT_TYPES = os.environ.get("DEBUG_EVENT_TYPES", "0") == "1"


def debug_print(*args):
    if DEBUG_EVENT_TYPES:
        print(*args)