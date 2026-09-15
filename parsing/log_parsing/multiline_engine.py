"""
multiline_engine.py

Módulo de parseo de logs multilínea.
"""

import re
from typing import List
from .text_preprocessing import (
    ORCHESTRATION_LINE_RE,
    _condense_match,
    strip_leading_separator_lines,
    filter_ignored_lines,
)
from parsing.log_parsing.multiline_utils import compile_timestamp_patterns, line_starts_new_event

def find_event_spans(full_text: str, compiled_patterns: dict) -> list:
    """
    Localiza los límites de cada "evento" (posible bloque multilínea) en
    full_text, usando TODOS los patrones estructurados del origen
    (compiled_patterns), con el mismo sistema de prioridad y resolución
    de solapamientos que usa parse_multiline().

    Args:
        full_text (str): texto completo del fichero de log.
        compiled_patterns (dict): {pattern_name: compiled_regex}, en el
            mismo orden de prioridad que declara el config del origen
            (PATTERNS, dict insertion order = prioridad).

    Returns:
        List[Tuple[int, int, str, re.Match]]: lista de
        (start, end_header, pattern_name, match) de los matches
        ACEPTADOS (ya resueltos los solapamientos), ordenados por
        posición de inicio. 'end_header' es el fin del match de
        cabecera; el CONTENIDO de cada evento va desde ahí hasta el
        'start' del siguiente elemento de la lista (o EOF).
    """
    all_matches = []
    for pattern_name, compiled_regex in compiled_patterns.items():
        for match in compiled_regex.finditer(full_text):
            all_matches.append((match.start(), match.end(), pattern_name, match))

    pattern_priority = {name: i for i, name in enumerate(compiled_patterns.keys())}
    all_matches.sort(key=lambda m: (m[0], pattern_priority[m[2]]))

    accepted = []
    occupied_until = -1
    for start, end, pattern_name, match in all_matches:
        if start < occupied_until:
            continue
        accepted.append((start, end, pattern_name, match))
        occupied_until = end

    return accepted

def parse_multiline(full_text, compiled_patterns, compiled_ignore, log_type, file_name):
    """
    Motor de parseo para configs con MULTILINE=True.

    Recolecta TODOS los matches de TODOS los patrones con su posición
    (start, end), y se queda solo con el de mayor prioridad cuando dos
    patrones matchean el mismo tramo de texto (ej: un patrón específico
    con timestamp vs. el catch-all "jdedebug_continuation" que matchea
    cualquier línea).

    Args:
        full_text (str): Contenido completo del archivo (ya preprocesado).
        compiled_patterns (dict): {pattern_name: compiled_regex}.
        compiled_ignore (List[re.Pattern]): Patrones de ignore compilados.
        log_type (str): Tipo de log detectado.
        file_name (str): Nombre del archivo de log.

    Returns:
        List[dict]: Lista de registros parseados (no hay unmatched en modo multiline).
    """
    # Preprocesado: condensar líneas ORCHESTRATION TRACING gigantes,
    # conservando type/name/output pero eliminando input/token/etc, que
    # causan backtracking catastrófico y no aportan valor.
    if 'ORCHESTRATION TRACING:' in full_text:
        original_len = len(full_text)
        full_text = ORCHESTRATION_LINE_RE.sub(_condense_match, full_text)
        saved = original_len - len(full_text)
        if saved > 0:
            print(f"  🧹 ORCHESTRATION TRACING condensado (-{saved:,} bytes)")

    print(f"  🔄 Procesando texto completo ({len(full_text):,} bytes)...")
    pattern_matches = {name: 0 for name in compiled_patterns.keys()}

    # Identificar todos los matches de todos los patrones, y resolver solapamientos
    # (límites de cada "evento")
    all_matches = find_event_spans(full_text, compiled_patterns)

    def should_ignore(text):
        return any(p.search(text) for p in compiled_ignore)

    records = []
    ignored_count = 0

    # Para cada evento, el mensaje es el contenido desde el final del match de cabecera 
    # hasta el inicio del siguiente match (o EOF).
    for idx, (start, end, pattern_name, match) in enumerate(all_matches):
        groups = match.groupdict()

        groups = match.groupdict()

        if 'message' in groups:
            message = groups.get('message', '')
        else:
            next_start = all_matches[idx + 1][0] if idx + 1 < len(all_matches) else len(full_text)
            message = full_text[end:next_start]

        # Eliminar líneas de separación iniciales (ej: "-----") que no aportan valor
        message = strip_leading_separator_lines(message)
        if compiled_ignore:
            # Filtrar líneas de ignore dentro del mensaje 
            # (ej: "continuation" que matchea cualquier línea)
            message = filter_ignored_lines(message, compiled_ignore)
            if not message:
                ignored_count += 1
                occupied_until = end
                continue

        record = {
            'file': file_name,
            'log_type': log_type,
            'pattern': pattern_name,
            'timestamp': groups.get('timestamp'),
            'level': groups.get('level'),
            'user': groups.get('user'),
            'component': groups.get('component'),
            'message': message.strip() if message else None,
            'pid': groups.get('pid'),
        }

        record.update({k: v for k, v in groups.items() if k not in record and v})

        records.append(record)
        pattern_matches[pattern_name] += 1
        occupied_until = end

    print(f"\n  📊 Matches:")
    for name, count in sorted(pattern_matches.items(), key=lambda x: -x[1]):
        if count > 0:
            print(f"    - {name}: {count:,}")

    if ignored_count > 0:
        print(f"  🚫 Ignorados: {ignored_count:,}")

    return records

def group_multiline_logs(lines: List[str], stats: dict, timestamp_patterns: List[str] = None,
                          compiled_patterns: dict = None) -> List[str]:
    """
    Agrupa líneas continuadas en un solo log.

    Args:
        lines (List[str]): Lista de líneas del log.
        stats (dict): Diccionario para acumular estadísticas de multiline.
        timestamp_patterns (List[str]): Patrones regex (sin compilar) que
            marcan el INICIO de un nuevo evento. Usado SOLO como fallback
            si no se proporciona compiled_patterns.
        compiled_patterns (dict): {pattern_name: compiled_regex} con TODOS
            los patrones estructurados declarados en PATTERNS del config
            del origen (mismo dict que usa parse_multiline). Si se
            proporciona, la frontera de cada evento se calcula con
            find_event_spans() — LA MISMA lógica de prioridad y
            resolución de solapamientos que usa el pipeline de parseo
            estructurado (parsing/log_parsing/multiline_engine.py)..

    Returns:
        List[str]: Lista de grupos de líneas (cada grupo es un string con
        saltos de línea internos).
    """
    full_text = '\n'.join(lines)

    if compiled_patterns:
        # Misma lógica que parse_multiline: fronteras de evento
        # resueltas con prioridad de patrones + no solapamiento.
        spans = find_event_spans(full_text, compiled_patterns)

        if not spans:
            return [full_text] if full_text.strip() else []

        grouped = []
        # Para cada match de cabecera, el contenido del evento va desde el final del match
        # hasta el inicio del siguiente match (o EOF). Se descartan eventos vacíos.
        for idx, (start, end, pattern_name, match) in enumerate(spans):
            next_start = spans[idx + 1][0] if idx + 1 < len(spans) else len(full_text)
            event_text = full_text[start:next_start].rstrip('\n')
            if event_text.strip():
                grouped.append(event_text)
                stats['multiline_groups'] += 1
                # nº de líneas de continuación = líneas totales del bloque - 1 (cabecera)
                stats['continuation_lines'] += event_text.count('\n')

        return grouped

    # --- Fallback ---
    grouped = []
    current_group = ""

    compiled_timestamp_patterns = compile_timestamp_patterns(timestamp_patterns)

    def _is_continuation(line: str) -> bool:
        if compiled_timestamp_patterns:
            return not line_starts_new_event(line, compiled_timestamp_patterns)
        return bool(line and line[0] in (' ', '\t', '.', '|'))

    # Por cada línea, si es continuación se añade al grupo actual; si no, 
    # se cierra el grupo y se inicia uno nuevo.
    for line in lines:
        # Si la línea está vacía, se ignora (no se añade a ningún grupo)
        if _is_continuation(line):
            if current_group:
                current_group += '\n' + line
                stats['continuation_lines'] += 1
            else:
                current_group = line
        else:
            if current_group:
                grouped.append(current_group)
                stats['multiline_groups'] += 1
            current_group = line

    if current_group:
        grouped.append(current_group)
        stats['multiline_groups'] += 1

    return grouped

