"""
file_processor.py

Procesamiento de archivos incrementales (INCREMENTAL=True en config
de origen): lee solo las líneas nuevas desde el último offset guardado.
"""
import os

from parsing.incremental import read_new_lines
from parsing.log_parsing import parse_lines_with_config


def process_incremental_file(storage, file_path, rel_path, offsets_state, log_type, cfg_module):
    """
    Procesa un archivo incremental usando el backend de storage (local o S3).

    Args:
        storage: Backend de almacenamiento
        file_path: Ruta completa del archivo
        rel_path: Ruta relativa
        offsets_state: Estado de offsets
        log_type: Tipo de log ya detectado
        cfg_module: Módulo de configuración ya cargado

    Returns:
        dict o None: resultado del parseo, o None si no hay líneas nuevas.
    """
    file_name = os.path.basename(rel_path)
    print(f"  ✓ Tipo detectado: {log_type}")

    # Lee solo las líneas nuevas desde el último offset guardado
    lines, new_offset, pending_buffer = read_new_lines(
        storage, file_path, rel_path, offsets_state,
        timestamp_patterns=getattr(cfg_module, 'TIMESTAMP_PATTERNS', None),
    )

    if not lines:
        print(f"  ⏭️  Sin líneas nuevas en {rel_path} (offset actual: {new_offset})")
        offsets_state[rel_path] = {"offset": new_offset, "pending": pending_buffer}
        return None

    print(f"  📥 {len(lines)} líneas nuevas detectadas en {rel_path}")

    full_text = '\n'.join(lines)
    records, unmatched = parse_lines_with_config(full_text, cfg_module, log_type, file_name)

    offsets_state[rel_path] = {"offset": new_offset, "pending": pending_buffer}

    return {
        'log_type': log_type,
        'records': records,
        'unmatched': unmatched,
        '_internal_config': {
            'timestamp_patterns': getattr(cfg_module, 'TIMESTAMP_PATTERNS', None),
            'extractors': getattr(cfg_module, 'EXTRACTORS', None)
        }
    }