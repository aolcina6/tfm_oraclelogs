"""
multiline_utils.py

Lógica compartida para detectar el inicio de un nuevo evento multilínea
a partir de timestamp_patterns.
"""
import re
from typing import List, Optional

TIMESTAMP_NEAR_START_MAX_PREFIX = 20


def compile_timestamp_patterns(timestamp_patterns: Optional[List[str]]) -> List["re.Pattern"]:
    """
    Compila los patrones de timestamp proporcionados en expresiones regulares.

    Args:
        timestamp_patterns (Optional[List[str]]): Lista de patrones de timestamp como cadenas.

    Returns:
        List[re.Pattern]: Lista de patrones de timestamp compilados como expresiones regulares.
    """
    compiled = []
    if not timestamp_patterns:
        return compiled
    for p in timestamp_patterns:
        try:
            compiled.append(re.compile(p))
        except Exception:
            continue
    return compiled


def line_starts_new_event(line: str, compiled_timestamp_patterns: List["re.Pattern"]) -> bool:
    """
    Determina si una línea de log indica el inicio de un nuevo evento multilínea
    basado en los patrones de timestamp compilados.

    Args:
        line (str): Línea de log a evaluar.
        compiled_timestamp_patterns (List[re.Pattern]): Lista de patrones de timestamp compilados.

    Returns:
        bool: True si la línea indica el inicio de un nuevo evento, False en caso contrario.
    """
    for p in compiled_timestamp_patterns:
        m = p.search(line)
        if m and m.start() <= TIMESTAMP_NEAR_START_MAX_PREFIX:
            return True
    return False

