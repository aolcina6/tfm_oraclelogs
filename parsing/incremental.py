"""
incremental.py

Lectura incremental de archivos de log (solo líneas nuevas desde el
último offset), usando el backend de storage abstracto (soporta local y S3).
"""
import sys
import os
from parsing.log_parsing.multiline_utils import compile_timestamp_patterns, line_starts_new_event

def read_new_lines(storage, path, rel_path, offsets_state, timestamp_patterns=None):
    """
    Lee solo las líneas nuevas desde el último offset guardado.
    'storage' es una instancia de StorageBackend (Local o S3).

    Args:
        storage: Backend de almacenamiento (LocalStorage o S3Storage).
        path (str): Ruta completa al archivo en el storage.
        rel_path (str): Ruta relativa del archivo (clave para offsets_state).
        offsets_state (dict): Diccionario que mantiene el offset y buffer pendiente
                              para cada archivo procesado.
        timestamp_patterns (List[str], opcional): Patrones regex que marcan
            el INICIO de un nuevo evento multilínea. Si se proporcionan, el
            último evento del chunk (todo lo que sigue al último timestamp
            detectado) se retiene como pending_buffer, ya que no podemos
            saber si el fichero terminó de escribirlo. Sin esto, un evento
            multilínea partido justo tras su timestamp (línea "completa"
            con \n) se procesaba truncado, y el resto llegaba en la
            siguiente ejecución SIN su timestamp de cabecera, perdiendo el
            evento o generando 'unmatched'. Confirmado como causa real de
            fragmentación en alert_jde/jde en producción.

    Returns:
        tuple: (new_lines, new_offset, pending_buffer)
            - new_lines (list): Lista de nuevas líneas completas y seguras
              de procesar (excluye el último evento potencialmente
              incompleto si se usa timestamp_patterns).
            - new_offset (int): Nuevo offset después de la lectura.
              ⚠️ Si se retiene un evento como pending, el offset avanza
              solo hasta el punto seguro, no hasta file_size.
            - pending_buffer (str): Buffer de texto pendiente (línea
              incompleta, o evento completo pendiente de más contenido).
    """
    file_size = storage.get_file_size(path)
    state = offsets_state.get(rel_path, {"offset": 0, "pending": ""})
    last_offset = state.get("offset", 0)
    pending = state.get("pending", "")

    if last_offset >= file_size:
        return [], last_offset, pending

    new_bytes = storage.read_bytes_from_offset(path, last_offset)
    new_text = pending + new_bytes.decode("utf-8", errors="replace")

    lines = new_text.splitlines(keepends=True)

    if lines and not lines[-1].endswith(("\n", "\r")):
        pending_buffer = lines[-1]
        lines = lines[:-1]
    else:
        pending_buffer = ""

    if timestamp_patterns and lines:
        compiled = compile_timestamp_patterns(timestamp_patterns)

        if compiled:
            last_event_start_idx = None
            for idx, line in enumerate(lines):
                if line_starts_new_event(line, compiled):
                    last_event_start_idx = idx

            # Si el último timestamp encontrado no es la propia última
            # línea del chunk, significa que hay contenido de mensaje
            # después de él pero no sabemos si está completo -> lo
            # retenemos igualmente para unirlo con la siguiente lectura.
            if last_event_start_idx is not None:
                held_lines = lines[last_event_start_idx:]
                lines = lines[:last_event_start_idx]
                pending_buffer = ''.join(held_lines) + pending_buffer

    consumed_text = ''.join(lines)
    safe_new_text_from_bytes = new_text[len(pending):]
    total_retained = len(pending_buffer)
    retained_from_new_bytes = pending_buffer[len(pending):] if pending_buffer.startswith(pending) else pending_buffer
    new_offset = file_size - len(retained_from_new_bytes.encode("utf-8", errors="replace"))

    return lines, new_offset, pending_buffer