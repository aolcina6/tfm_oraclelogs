"""
text_preprocessing.py

Módulo de preprocesamiento de texto para logs.
"""

import re
import json
from typing import List


# LÍNEAS DE SOLO SEPARADORES
SEPARATOR_LINE_PATTERN = re.compile(r'^[\*=\-]{5,}\s*$')

# PATRONES DE ORCHESTRATION TRAICNG (JSON de gran tamaño que causan backtracking)
ORCHESTRATION_LINE_RE = re.compile(
    r'ORCHESTRATION TRACING:\s*(?P<json>\[.*\])(?=\s*$)',
    re.MULTILINE
)

_FIELD_TYPE_RE = re.compile(r'"type"\s*:\s*"([^"]*)"')
_FIELD_NAME_RE = re.compile(r'"name"\s*:\s*"([^"]*)"')
_FIELD_OUTPUT_RE = re.compile(r'"output"\s*:\s*"((?:[^"\\]|\\.)*)"')


def _condense_match(m):
    """
    Condensa un match de ORCHESTRATION TRACING (objeto JSON), extrayendo solo los campos.

    Args:
        m: Match object de la regex ORCHESTRATION_LINE_RE

    Returns:
        str: Línea condensada con solo type, name y output.
    """
    json_blob = m.group('json')
    try:
        events = json.loads(json_blob)
        parts = [
            {'type': e.get('type', ''), 'name': e.get('name', ''), 'output': e.get('output', '')}
            for e in events if isinstance(e, dict)
        ]
        return 'ORCHESTRATION TRACING: ' + json.dumps(parts, ensure_ascii=False)
    except (json.JSONDecodeError, TypeError):
        types = _FIELD_TYPE_RE.findall(json_blob)
        names = _FIELD_NAME_RE.findall(json_blob)
        outputs = _FIELD_OUTPUT_RE.findall(json_blob)
        parts = [
            f'{{"type":"{t}","name":"{n}","output":"{o}"}}'
            for t, n, o in zip(types, names, outputs)
        ]
        return 'ORCHESTRATION TRACING: [' + ','.join(parts) + ']'


def strip_leading_separator_lines(message: str) -> str:
    """
    Elimina líneas compuestas únicamente por separadores (****, ====, ----)
    al PRINCIPIO del mensaje. Estas líneas no aportan información semántica
    y generan templates duplicados en Drain solo por su posición.

    Args:
        message (str): Mensaje completo del log.

    Returns:
        str: Mensaje limpio sin líneas de separadores al inicio.
    """
    if not message:
        return message

    lines = message.split('\n')
    start_idx = 0
    while start_idx < len(lines) and SEPARATOR_LINE_PATTERN.match(lines[start_idx].strip()):
        start_idx += 1

    return '\n'.join(lines[start_idx:]).strip()


def filter_ignored_lines(message: str, compiled_ignore) -> str:
    """
    Filtra las líneas de un mensaje multilínea según los patrones de ignore compilados.

    Args:
        message (str): Mensaje completo del log.
        compiled_ignore (List[re.Pattern]): Lista de patrones regex compilados para ignorar.

    Returns:
        str: Mensaje filtrado sin las líneas ignoradas.

    Note:
        En modo MULTILINE, en vez de descartar el bloque completo si CUALQUIER
        línea matchea un ignore pattern, filtramos línea a línea y reconstruimos
        el mensaje solo con las líneas que NO matchean ningún patrón.
    """
    if not compiled_ignore:
        return message

    kept_lines = []
    for line in message.split('\n'):
        if 'ORCHESTRATION TRACING:' in line:
            continue
        if not any(p.search(line) for p in compiled_ignore):
            kept_lines.append(line)

    return '\n'.join(kept_lines).strip()

def compile_ignore_patterns(ignore_patterns: List[str]):
    """
    Compila cada patrón de ignore_patterns por separado (no combinados
    con alternancia), con flags re.DOTALL | re.MULTILINE.

    Args:
        ignore_patterns (List[str]): patrones regex en crudo.

    Returns:
        List[re.Pattern]: patrones compilados (los inválidos se
        descartan con un warning, sin interrumpir el resto).
    """
    compiled = []
    for pattern in ignore_patterns:
        try:
            compiled.append(re.compile(pattern, re.MULTILINE))
        except re.error as e:
            print(f"  ⚠️  Error compilando ignore pattern '{pattern[:30]}...': {e}")
    return compiled