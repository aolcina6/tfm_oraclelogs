"""
singleline_engine.py

Módulo de motor de parseo para logs de una sola línea (MULTILINE=False).
"""

def parse_singleline(full_text, compiled_patterns, compiled_ignore, log_type, file_name):
    """
    Motor de parseo para configs con MULTILINE=False (una línea = un registro).

    Args:
        full_text (str): Contenido completo del archivo.
        compiled_patterns (dict): {pattern_name: compiled_regex}.
        compiled_ignore (List[re.Pattern]): Patrones de ignore compilados.
        log_type (str): Tipo de log detectado.
        file_name (str): Nombre del archivo de log.

    Returns:
        Tuple[List[dict], List[dict]]: Registros parseados y líneas sin match.
    """
    lines = full_text.split('\n')
    print(f"  🔄 Procesando {len(lines):,} líneas...")

    if compiled_ignore:
        print(f"  🔧 Pre-filtrando...")
        original = len(lines)

        lines = [
            line for line in lines
            if line.strip() and not any(p.search(line) for p in compiled_ignore)
        ]

        filtered = original - len(lines)
        print(f"    ✓ Filtradas {filtered:,} líneas ({len(lines):,} restantes)")

    records = []
    pattern_matches = {name: 0 for name in compiled_patterns.keys()}
    unmatched_lines = []

    # Parsear línea por línea, buscando el primer patrón que matchee
    for i, line in enumerate(lines, 1):
        if not line.strip():
            continue

        matched = False
        # Buscar el primer patrón que matchee la línea
        for pattern_name, compiled_regex in compiled_patterns.items():
            match = compiled_regex.match(line)
            if match:
                groups = match.groupdict()
                record = {
                    'file': file_name,
                    'log_type': log_type,
                    'pattern': pattern_name,
                    **{k: v for k, v in groups.items() if v is not None}
                }
                records.append(record)
                matched = True
                pattern_matches[pattern_name] += 1
                break

        if not matched:
            unmatched_lines.append({'file': file_name, 'log_type': log_type, 'raw_line': line})

        if i % 100000 == 0:
            print(f"    → {i:,}/{len(lines):,} líneas...")

    print(f"\n  📊 Matches:")
    for name, count in sorted(pattern_matches.items(), key=lambda x: -x[1]):
        if count > 0:
            print(f"    - {name}: {count:,}")

    if unmatched_lines:
        pct = len(unmatched_lines) / len(lines) * 100 if lines else 0
        print(f"  ⚠️  Sin match: {len(unmatched_lines):,} ({pct:.1f}%)")
        for i, um in enumerate(unmatched_lines[:3], 1):
            print(f"    [{i}] {um['raw_line'][:80]}...")

    return records, unmatched_lines