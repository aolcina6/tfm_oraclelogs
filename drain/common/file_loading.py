"""
file_loading.py 

Lectura + decompresión + condensado ORCHESTRATION TRACING + agrupado
multilínea.
"""
from typing import List, Tuple, Dict, Optional, Callable
from parsing.log_parsing.text_preprocessing import ORCHESTRATION_LINE_RE, _condense_match

def _read_file_content(storage, file_path: str, compression_type) -> str:
    """
    Lee y decodifica el contenido de un fichero desde el backend de almacenamiento,
    aplicando descompresión si corresponde.

    Args:
        storage: backend de almacenamiento
        file_path (str): ruta del fichero a leer
        compression_type: tipo de compresión del fichero (si aplica)

    Returns:
        str: contenido del fichero decodificado como UTF-8
    """
    if hasattr(storage, 'read_and_decompress'):
        return storage.read_and_decompress(file_path, compression_type)
    raw_bytes = storage.read_all_bytes(file_path)
    return raw_bytes.decode('utf-8', errors='replace')


def load_and_preprocess_lines(
    storage,
    files: List[Tuple],
    multiline: bool,
    grouping_fn: Optional[Callable[[List[str]], List[str]]] = None,
    stats: Optional[Dict] = None,
) -> Tuple[List[str], int]:
    """
    Lee y decodifica todos los ficheros de un origen, condensando
    ORCHESTRATION TRACING y aplicando agrupado multilínea si corresponde.

    Args:
        storage: backend de almacenamiento
        files: lista de (file_path, rel_path, compression_type)
        multiline: si True, aplica grouping_fn sobre las líneas
        grouping_fn: función que agrupa líneas continuadas. Recibe
            List[str] y devuelve List[str]. Puede ser:
              - drain.group_multiline_logs (método de instancia de Drain)
              - lambda lines: group_multiline_logs(lines, stats) (drain3_common)
            Si es None y multiline=True, no se agrupa (se devuelven líneas sueltas).
        stats: dict opcional para acumular estadísticas de agrupado
            (usado por la variante drain3_common, que también rellena
            stats['multiline_groups'] / stats['continuation_lines'] si la
            grouping_fn se lo pasa por closure).

    Returns:
        Tuple[List[str], int]: (líneas listas para parsear, total_lines crudo)
    """
    all_lines = []
    total_lines = 0

    for file_path, rel_path, compression_type in files:
        try:
            content = _read_file_content(storage, file_path, compression_type)

            # Son líneas de JSON enormes que dejan colgado el pipeline
            if 'ORCHESTRATION TRACING:' in content:
                content = ORCHESTRATION_LINE_RE.sub(_condense_match, content)

            lines = content.split('\n')
        except Exception as e:
            print(f"      ✗ Error leyendo {rel_path}: {e}")
            continue

        total_lines += len(lines)

        if multiline and grouping_fn is not None:
            lines = grouping_fn(lines)

        all_lines.extend(lines)

    return all_lines, total_lines