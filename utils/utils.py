"""
utils.py

Módulo de utilidades para normalización de timestamps, aplicación de extractores 
y manejo de componentes implícitos en registros de logs.
"""

import re
from datetime import datetime
from config.general_config import TIMESTAMP_PATTERNS, MONTH_MAP, MONTH_NAME_TO_NUM, MONTH_MAP_CAPITALIZED, MONTH_MAP_LOWERCASE, MONTH_MAP_UPPERCASE, MONTH_MAP_SPANISH
from typing import List, Dict, Any, Tuple
import os

def detect_and_normalize_timestamp(timestamp_str: str, timestamp_patterns=None) -> dict:
    """
    Detecta el formato del timestamp usando los patrones proporcionados (o generales)
    y lo normaliza a formato dd/mm/yy hh:mm:ss.ms
    
    Args:
        timestamp_str (str): Timestamp a normalizar.
        timestamp_patterns (list, optional): Lista de patrones regex específicos para este origen.

    Returns:
        dict: {'timestamp_normalized': str or None}
    """
    from config.general_config import TIMESTAMP_PATTERNS as GENERAL_PATTERNS

    if not timestamp_str:
        return {'timestamp_normalized': None}

    # Usar patrones específicos si se proporcionan, si no los generales
    patterns_to_use = timestamp_patterns or GENERAL_PATTERNS

    timestamp_str = timestamp_str.strip()

    for idx, pattern in enumerate(patterns_to_use):
        match = re.search(pattern, timestamp_str)
        if match:
            try:
                groups = match.groupdict()

                year = groups.get('year')
                if not year:
                    year = '2026'

                # Convertir mes a número con TODOS los mapeos
                month = None
                
                if groups.get('month_name'):
                    month_name_raw = groups['month_name']
                    # Intentar en este orden: lowercase → capitalized → uppercase
                    month = (
                        MONTH_MAP_LOWERCASE.get(month_name_raw.lower())
                        or MONTH_MAP_CAPITALIZED.get(month_name_raw)
                        or MONTH_MAP_UPPERCASE.get(month_name_raw.upper())
                        or MONTH_NAME_TO_NUM.get(month_name_raw.upper())
                        or MONTH_MAP.get(month_name_raw)
                    )
                
                elif groups.get('month'):
                    month = groups['month']
                
                # Por defecto enero si no se encontró
                month = month or '01'

                day = groups.get('day', '01')
                if not day:
                    day = '01'

                hour = groups.get('hour', '00')
                minute = groups.get('minute', '00')
                second = groups.get('second', '00')

                if not hour:
                    hour = '00'
                if not minute:
                    minute = '00'
                if not second:
                    second = '00'

                # Manejo de milisegundos vs microsegundos
                milliseconds = '000'
                if groups.get('milliseconds'):
                    milliseconds = groups['milliseconds'][:3].ljust(3, '0')
                elif groups.get('microseconds'):
                    microseconds = groups['microseconds']
                    milliseconds = microseconds[:3].ljust(3, '0')

                # Padding correcto
                day = str(day).zfill(2)
                month = str(month).zfill(2)
                hour = str(hour).zfill(2)
                minute = str(minute).zfill(2)
                second = str(second).zfill(2)
                milliseconds = str(milliseconds).zfill(3)

                # Año corto (últimos 2 dígitos)
                year_short = str(year)[-2:]
                normalized = f"{day}/{month}/{year_short} {hour}:{minute}:{second}.{milliseconds}"

                return {
                    'timestamp_normalized': normalized
                }

            except Exception as e:
                print(f"❌ Error normalizando timestamp '{timestamp_str}': {str(e)}")
                continue

    return {
        'timestamp_normalized': None
    }

def normalize_records(records: list, timestamp_patterns=None, debug=True) -> tuple:
    """
    Normaliza todos los registros con timestamps válidos.

    Args:
        records: Lista de registros (dicts) con campo 'timestamp'.
        timestamp_patterns: Lista de patrones regex específicos para este origen.
        debug: Si es True, imprime información de depuración.

    Returns:
        tuple: (normalized_records, stats)
        - normalized_records: Lista de registros con timestamps normalizados.
        - stats: Diccionario con estadísticas de normalización.
    """
    normalized_records = []
    
    stats = {
        'total': len(records),
        'normalized': 0,
        'failed': 0,
        'no_timestamp': 0,
        'failed_examples': [],
    }

    for idx, record in enumerate(records):
        # Validación básica
        if not isinstance(record, dict):
            stats['no_timestamp'] += 1
            normalized_records.append(record)
            continue

        normalized_record = record.copy()
        raw_ts = record.get('timestamp', '').strip() if record.get('timestamp') else ''

        if not raw_ts:
            stats['no_timestamp'] += 1
            normalized_records.append(normalized_record)
            continue

        normalized_ts = _normalize_timestamp_debug(
            raw_ts, 
            timestamp_patterns or [],
            debug=debug,
            record_idx=idx,
            log_file=record.get('file', 'unknown')
        )

        if normalized_ts:
            normalized_record['timestamp'] = normalized_ts
            stats['normalized'] += 1
            if debug and idx < 5:
                print(f"  ✅ Registro {idx}: '{raw_ts}' → '{normalized_ts}'")
        else:
            stats['failed'] += 1
            normalized_record['timestamp'] = None
            stats['failed_examples'].append({
                'index': idx,
                'raw': raw_ts,
                'file': record.get('file', 'unknown')
            })
            if debug and len(stats['failed_examples']) <= 5:
                print(f"  ❌ Registro {idx} NO se normalizó: '{raw_ts}'")

        normalized_records.append(normalized_record)

    if debug:
        print(f"\n📊 ESTADÍSTICAS DE NORMALIZACIÓN:")
        print(f"  Total: {stats['total']}")
        print(f"  Normalizados: {stats['normalized']}")
        print(f"  Fallidos: {stats['failed']}")
        print(f"  Sin timestamp: {stats['no_timestamp']}")
        if stats['failed_examples']:
            print(f"\n  Ejemplos de fallos:")
            for ex in stats['failed_examples'][:3]:
                print(f"    - Idx {ex['index']}: '{ex['raw']}' en {ex['file']}")

    return normalized_records, stats

def _normalize_timestamp_debug(timestamp_str: str, patterns: list, debug=False, record_idx=0, log_file='') -> str:
    """
    Intenta normalizar un timestamp con debug completo.
    
    Args:
        timestamp_str: Timestamp a normalizar.
        patterns: Lista de patrones regex específicos para este origen.
        debug: Si es True, imprime información de depuración.
        record_idx: Índice del registro (para debug).
        log_file: Nombre del archivo fuente (para debug).

    Returns:
        str: Timestamp normalizado o None si no se pudo normalizar.
    """
    try:
        from config.general_config import (
            MONTH_MAP_SPANISH, MONTH_MAP_CAPITALIZED, MONTH_MAP_LOWERCASE
        )
    except ImportError:
        # Fallback si no están en general_config
        MONTH_MAP_SPANISH = {
            'ene': '01', 'feb': '02', 'mar': '03', 'abr': '04',
            'may': '05', 'jun': '06', 'jul': '07', 'ago': '08',
            'sep': '09', 'oct': '10', 'nov': '11', 'dic': '12',
        }
        MONTH_MAP_CAPITALIZED = {
            'Jan': '01', 'Feb': '02', 'Mar': '03', 'Apr': '04',
            'May': '05', 'Jun': '06', 'Jul': '07', 'Aug': '08',
            'Sep': '09', 'Oct': '10', 'Nov': '11', 'Dec': '12',
        }
        MONTH_MAP_LOWERCASE = {
            'jan': '01', 'feb': '02', 'mar': '03', 'apr': '04',
            'may': '05', 'jun': '06', 'jul': '07', 'aug': '08',
            'sep': '09', 'oct': '10', 'nov': '11', 'dec': '12',
        }

    if not timestamp_str:
        return None

    timestamp_str = timestamp_str.strip()

    # ESTRATEGIA 0: Oracle/Listener format
    # "23-DEC-2024 11:44:26" o "23-Dec-2024 11:44:26"
    oracle_format = re.match(
        r'^(\d{1,2})-(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC|ene|feb|mar|abr|may|jun|jul|ago|sep|oct|nov|dic)-(\d{4})\s+(\d{2}):(\d{2}):(\d{2})',
        timestamp_str,
        re.IGNORECASE
    )
    if oracle_format:
        day, month_name, year, hour, minute, second = oracle_format.groups()
        
        # Intentar español primero, luego inglés
        month_num = (
            MONTH_MAP_SPANISH.get(month_name.lower())
            or MONTH_MAP_CAPITALIZED.get(month_name.capitalize())
            or MONTH_MAP_LOWERCASE.get(month_name.lower())
        )
        
        if month_num:
            yy = year[-2:]
            result = f"{day.zfill(2)}/{month_num}/{yy} {hour}:{minute}:{second}.000"
            if debug and record_idx < 3:
                print(f"  ✅ Oracle/Listener: '{timestamp_str}' → '{result}'")
            return result

    # ESTRATEGIA 1: Syslog CON día de la semana (JDE)
    # "Sun Aug  9 02:00:07.608092"
    syslog_with_weekday = re.match(
        r'^(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s{1,2}(\d{1,2})\s+(\d{2}):(\d{2}):(\d{2})\.(\d{6})',
        timestamp_str,
        re.IGNORECASE
    )
    if syslog_with_weekday:
        month_name, day, hour, minute, second, microsecond = syslog_with_weekday.groups()
        month_num = MONTH_MAP_CAPITALIZED.get(month_name.capitalize())
        
        if month_num:
            current_year = datetime.now().year
            yy = str(current_year)[-2:]
            ms = microsecond[:3].ljust(3, '0')
            day_padded = str(day).zfill(2)
            
            result = f"{day_padded}/{month_num}/{yy} {hour}:{minute}:{second}.{ms}"
            if debug and record_idx < 3:
                print(f"  ✅ JDE (con weekday): '{timestamp_str}' → '{result}'")
            return result

    # ESTRATEGIA 2: Syslog SIN día de la semana (JDEDEBUG, BSSV, AIS)
    # "Aug 20 19:14:03.206883" o "Aug  7 12:49:21.108103"
    syslog_without_weekday = re.match(
        r'^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s{1,2}(\d{1,2})\s+(\d{2}):(\d{2}):(\d{2})\.(\d{6})',
        timestamp_str,
        re.IGNORECASE
    )
    if syslog_without_weekday:
        month_name, day, hour, minute, second, microsecond = syslog_without_weekday.groups()
        month_num = MONTH_MAP_CAPITALIZED.get(month_name.capitalize())
        
        if month_num:
            current_year = datetime.now().year
            yy = str(current_year)[-2:]
            ms = microsecond[:3].ljust(3, '0')
            day_padded = str(day).zfill(2)
            
            result = f"{day_padded}/{month_num}/{yy} {hour}:{minute}:{second}.{ms}"
            if debug and record_idx < 3:
                print(f"  ✅ Syslog (sin weekday): '{timestamp_str}' → '{result}'")
            return result

    # ESTRATEGIA 3: BSSV/AIS con coma (español e inglés)
    # "31 jul 2026 23:34:03,027" o "07 ago 2026 01:51:46,148"
    bssv_format = re.match(
        r'^(\d{1,2})\s+(ene|feb|mar|abr|may|jun|jul|ago|sep|oct|nov|dic|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{4})\s+(\d{2}):(\d{2}):(\d{2})[,.](\d{3})',
        timestamp_str,
        re.IGNORECASE
    )
    if bssv_format:
        day, month_name, year, hour, minute, second, ms = bssv_format.groups()

        month_num = (
            MONTH_MAP_SPANISH.get(month_name.lower())
            or MONTH_MAP_CAPITALIZED.get(month_name.capitalize())
        )

        if month_num:
            yy = year[-2:]
            day_padded = str(day).zfill(2)
            result = f"{day_padded}/{month_num}/{yy} {hour}:{minute}:{second}.{ms}"
            if debug and record_idx < 3:
                print(f"  ✅ BSSV/AIS: '{timestamp_str}' → '{result}'")
            return result

    # ESTRATEGIA 4: ISO 8601
    # "2020-02-14T20:14:34.807103"
    iso_match = re.match(
        r'^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})\.(\d+)',
        timestamp_str
    )
    if iso_match:
        year, month, day, hour, minute, second, microsecond = iso_match.groups()
        ms = microsecond[:3].ljust(3, '0')
        yy = year[2:]
        result = f"{day}/{month}/{yy} {hour}:{minute}:{second}.{ms}"
        if debug and record_idx < 3:
            print(f"  ✅ ISO 8601: '{timestamp_str}' → '{result}'")
        return result

    # ESTRATEGIA 5: Numérico variado
    # "dd/mm/yyyy hh:mm:ss.ms" o "mm/dd/yyyy hh:mm:ss.ms"
    numeric_match = re.match(
        r'^(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s+(\d{2}):(\d{2}):(\d{2})(?:\.(\d+))?',
        timestamp_str
    )
    if numeric_match:
        part1, part2, year, hour, minute, second, microsecond = numeric_match.groups()
        part1_int = int(part1)
        part2_int = int(part2)

        if part1_int > 12:
            day, month = part1, part2
        elif part2_int > 12:
            month, day = part1, part2
        else:
            day, month = part1, part2

        day_int = int(day)
        month_int = int(month)

        if day_int < 1 or day_int > 31 or month_int < 1 or month_int > 12:
            if debug and record_idx < 3:
                print(f"  ❌ Patrón numérico INVÁLIDO: día={day_int}, mes={month_int}")
            return None

        yy = year[-2:] if len(year) > 2 else year
        ms = (microsecond[:3].ljust(3, '0')) if microsecond else '000'
        result = f"{int(day):02d}/{int(month):02d}/{yy} {hour}:{minute}:{second}.{ms}"
        if debug and record_idx < 3:
            print(f"  ✅ Patrón NUMÉRICO detectado: '{result}'")
        return result

    # ESTRATEGIA 2: Syslog SIN día de la semana (JDEDEBUG, BSSV, AIS)
    # "Aug 20 19:14:03.206883" o "Aug  7 12:49:21.108103"
    syslog_without_weekday = re.match(
        r'^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s{1,2}(\d{1,2})\s+(\d{2}):(\d{2}):(\d{2})\.(\d{6})',
        timestamp_str,
        re.IGNORECASE
    )
    if syslog_without_weekday:
        month_name, day, hour, minute, second, microsecond = syslog_without_weekday.groups()
        month_num = MONTH_MAP_CAPITALIZED.get(month_name.capitalize())
        
        if month_num:
            current_year = datetime.now().year
            yy = str(current_year)[-2:]
            ms = microsecond[:3].ljust(3, '0')
            day_padded = str(day).zfill(2)
            
            result = f"{day_padded}/{month_num}/{yy} {hour}:{minute}:{second}.{ms}"
            if debug and record_idx < 3:
                print(f"  ✅ Syslog (sin weekday): '{timestamp_str}' → '{result}'")
            return result

    # ESTRATEGIA 2b: Syslog clásico SIN microsegundos (Linux estándar)
    # "Jun 14 15:16:01" (sin día de la semana, sin fracción de segundo)
    syslog_no_fraction = re.match(
        r'^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s{1,2}(\d{1,2})\s+(\d{2}):(\d{2}):(\d{2})\s*$',
        timestamp_str,
        re.IGNORECASE
    )
    if syslog_no_fraction:
        month_name, day, hour, minute, second = syslog_no_fraction.groups()
        month_num = MONTH_MAP_CAPITALIZED.get(month_name.capitalize())

        if month_num:
            current_year = datetime.now().year
            yy = str(current_year)[-2:]
            day_padded = str(day).zfill(2)

            result = f"{day_padded}/{month_num}/{yy} {hour}:{minute}:{second}.000"
            if debug and record_idx < 3:
                print(f"  ✅ Syslog clásico (sin fracción): '{timestamp_str}' → '{result}'")
            return result

    # ❌ NINGÚN PATRÓN COINCIDIÓ
    if debug and record_idx < 3:
        print(f"  ❌ NINGÚN PATRÓN COINCIDIÓ: '{timestamp_str}' en {log_file}")

    return None

def apply_extractors(records: list, extractor_patterns=None) -> list:
    """
    Aplica extractores con soporte para múltiples regex por extractor.
    
    Cada extractor puede tener:
    - "regex": "pattern" (string único) → se convierte a ["pattern"]
    - "regex": ["pattern1", "pattern2", ...] (lista) → se usa directamente
    
    Args:
        records: Lista de registros
        extractor_patterns: Lista o dict de extractores específicos
    
    Returns:
        list: Registros con campos 'extracted' añadidos
    """
    # Normalizar y combinar extractores (genéricos + específicos)
    by_name = {}
    order = []

    # Overlay de específicos (reemplazan o añaden)
    if extractor_patterns:
        if isinstance(extractor_patterns, dict):
            for name, pat in extractor_patterns.items():
                by_name[name] = {"extractor": name, "regex": pat, "anchor": None}
                if name not in order:
                    order.append(name)
        elif isinstance(extractor_patterns, list):
            for e in extractor_patterns:
                n = e.get("extractor")
                if not n or not e.get("regex"):
                    continue
                by_name[n] = e
                if n not in order:
                    order.append(n)

    # Construir lista final de extractores en el orden definido
    extractors_list = [by_name[n] for n in order if n in by_name]

    # Normalizar regex (string → lista) y compilar patrones
    compiled = []
    for e in extractors_list:
        name = e.get("extractor")
        pat = e.get("regex")
        anchor = e.get("anchor")
        
        if not name or not pat:
            continue
        
        # Convertir string único a lista
        if isinstance(pat, str):
            pat = [pat]
        elif not isinstance(pat, list):
            continue  # Skip si no es string ni lista
        
        # Compilar todos los regex de este extractor
        compiled_regex_list = []
        for regex_pattern in pat:
            try:
                cre = re.compile(regex_pattern, re.IGNORECASE)
                compiled_regex_list.append(cre)
            except re.error as e:
                print(f"⚠️  Error compilando regex '{regex_pattern}': {e}")
                continue
        
        if compiled_regex_list:
            compiled.append({
                "extractor": name,
                "regex_compiled_list": compiled_regex_list,  # ✅ Lista de regex compilados
                "anchor": anchor
            })

    WINDOW = 400

    # Aplicar extractores a cada registro
    for rec in records:
        # Obtener texto fuente
        text_sources = []
        if isinstance(rec.get('message'), str):
            text_sources.append(rec['message'])
        if isinstance(rec.get('raw_line'), str):
            text_sources.append(rec['raw_line'])
        
        if not text_sources:
            rec['extracted'] = {}
            continue
        
        txt = "\n".join(text_sources)
        extracted = {}

        # Aplicar cada extractor (con múltiples regex)
        for item in compiled:
            name = item['extractor']
            regex_list = item['regex_compiled_list']
            anchor = item.get('anchor')
            found = []

            # Cada regex del extractor
            for cre in regex_list:
                
                # Si hay anchor, buscar en ventanas
                if anchor:
                    try:
                        pattern_contains_anchor = bool(
                            re.search(re.escape(anchor), cre.pattern, re.IGNORECASE)
                        )
                    except Exception:
                        pattern_contains_anchor = False

                    # Buscar anchor en el texto
                    for m_anchor in re.finditer(re.escape(anchor), txt, re.IGNORECASE):
                        end = min(len(txt), m_anchor.end() + WINDOW)

                        if pattern_contains_anchor:
                            start = m_anchor.start()
                        else:
                            post = txt[m_anchor.end():end]
                            m_first = re.search(r'[A-Za-z0-9_\-/.@]', post)
                            start = m_anchor.end() + (m_first.start() if m_first else 0)

                        window_txt = txt[start:end]
                        m = cre.search(window_txt)
                        
                        if m:
                            if m.groupdict():
                                for v in m.groupdict().values():
                                    if v and v.strip():
                                        found.append(v.strip())
                            else:
                                val = m.group(0)
                                if val and val.strip():
                                    found.append(val.strip())

                    # Si no encontró con anchor, buscar en todo el texto
                    if not found:
                        for m in cre.finditer(txt):
                            if m.groupdict():
                                for v in m.groupdict().values():
                                    if v and v.strip():
                                        found.append(v.strip())
                            else:
                                val = m.group(0)
                                if val and val.strip():
                                    found.append(val.strip())

            # Deduplicar y validar resultados
            seen = set()
            dedup = []
            
            for v in found:
                if v in seen:
                    continue
                seen.add(v)
                
                # Validación especial para puertos
                if name == 'port':
                    try:
                        vi = int(re.sub(r'\D', '', v))
                        if 0 <= vi <= 65535:
                            dedup.append(str(vi))
                    except Exception:
                        continue
                else:
                    dedup.append(v)

            if dedup:
                extracted[name] = dedup

        rec['extracted'] = extracted if extracted else {}

    return records

def apply_default_component(records: list, default_component: str = None) -> list:
    """
    Rellena el campo 'component' en aquellos registros donde no viene informado
    (None, vacío o ausente), usando el valor por defecto definido en el config
    module correspondiente (DEFAULT_COMPONENT).

    Args:
        records: Lista de registros ya parseados
        default_component: Valor a usar cuando 'component' no está informado

    Returns:
        Lista de registros con 'component' completado donde aplicaba
    """
    if not default_component:
        return records

    for record in records:
        if not record.get('component'):
            record['component'] = default_component

    return records

def apply_implicit_level(records: list, implicit_level_patterns: dict) -> list:
    """
    Rellena el campo 'level' en aquellos registros donde no viene informado
    (None o vacío), infiriéndolo a partir del contenido de 'message' usando
    IMPLICIT_LEVEL_PATTERNS (definido en config/general_config.py).

    Se espera que implicit_level_patterns tenga la forma:
        {
            "ERROR": [regex1, regex2, ...],
            "WARN": [regex1, regex2, ...],
        }
    Cualquier registro que no matchee ningún patrón de ERROR ni WARN se
    clasifica como "INFO".

    Args:
        records: Lista de registros ya parseados
        implicit_level_patterns: dict con listas de regex por nivel

    Returns:
        Lista de registros con 'level' completado donde no venía informado
    """
    if not implicit_level_patterns:
        return records

    error_patterns = [re.compile(p, re.IGNORECASE) for p in implicit_level_patterns.get('ERROR', [])]
    warn_patterns = [re.compile(p, re.IGNORECASE) for p in implicit_level_patterns.get('WARN', [])]

    for record in records:
        if record.get('level'):
            continue

        message = record.get('message') or ''

        if any(p.search(message) for p in error_patterns):
            record['level'] = 'ERROR'
        elif any(p.search(message) for p in warn_patterns):
            record['level'] = 'WARN'
        else:
            record['level'] = 'INFO'

    return records

def apply_level_mapping(records: list, level_mapping: dict) -> list:
    """
    Normaliza el campo 'level' cuando el log usa una nomenclatura propia
    (ej. e1root: MANDATORY, SEVERE, APP...) a los niveles estándar
    ERROR / WARN / INFO / DEBUG, usando LEVEL_MAPPING definido en el
    config module correspondiente.

    Si el valor de 'level' no está en el mapping, se deja tal cual
    (no se sobreescribe con algo desconocido).

    Args:
        records: Lista de registros ya parseados
        level_mapping: dict {nivel_nativo: nivel_estandar}, case-insensitive

    Returns:
        Lista de registros con 'level' normalizado donde aplicaba
    """
    if not level_mapping:
        return records

    # Normalizar claves del mapping a mayúsculas para comparación case-insensitive
    normalized_mapping = {k.upper(): v for k, v in level_mapping.items()}

    for record in records:
        level = record.get('level')
        if not level:
            continue

        mapped = normalized_mapping.get(level.strip().upper())
        if mapped:
            record['level'] = mapped

    return records

def list_logs(folder_path):
    """
    Recorre recursivamente la carpeta y subcarpetas buscando archivos .log.
    Devuelve una lista de tuplas: (ruta_completa, ruta_relativa_para_nombrar_salida)
    """
    log_files = []
    for root, dirs, files in os.walk(folder_path):
        for f in files:
            if f.endswith(".log"):
                full_path = os.path.join(root, f)
                rel_path = os.path.relpath(full_path, folder_path)
                log_files.append((full_path, rel_path))
    return log_files


def get_date_key(timestamp: str):
    """
    Extrae (año, mes, día) de un timestamp normalizado dd/mm/yy hh:mm:ss.ms
    Devuelve None si no se puede parsear.
    """
    try:
        date_part, _ = timestamp.split(' ')
        day, month, year_short = date_part.split('/')
        year_full = f"20{year_short}" if len(year_short) == 2 else year_short
        return (year_full, month, day)
    except Exception:
        return None

def group_records_by_day(records: list, source_file: str):
    """
    Agrupa los registros por (año, mes, día).
    Añade el campo 'source_file' a cada registro para trazabilidad.
    Los registros sin timestamp válido van a la clave 'sin_fecha'.
    """
    groups = {}
    for record in records:
        record = dict(record)  # copia para no mutar el original fuera de contexto
        record['source_file'] = source_file
        ts = record.get('timestamp')
        key = get_date_key(ts) if ts else None
        group_key = key if key else "sin_fecha"
        groups.setdefault(group_key, []).append(record)
    return groups
