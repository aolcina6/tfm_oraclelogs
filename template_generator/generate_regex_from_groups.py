#!/usr/bin/env python3
"""
generate_regex_from_groups.py

Toma el resultado de semantic_grouping.py (x_template_semantic_groups.json)
y genera/actualiza un 'x_template_regex.json' donde CADA GRUPO conserva su
propia estructura (group_id, representative_cluster_id,
representative_template, regex, event_type, severity, member_cluster_ids).

El regex de cada grupo se genera fusionando (token a token) las plantillas
de TODOS sus member_cluster_ids -no solo la representativa-, generalizando
con <*> las posiciones donde los miembros difieren entre sí. Esto evita
generar un patrón demasiado estricto que solo cubra la plantilla
representativa y no al resto de miembros agrupados semánticamente.

Uso:
    python template_generator/generate_regex_from_groups.py templates/alert_jde_template_semantic_groups.json
"""
import difflib
import json
import os
import re
import argparse
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from template_generator.template_to_regex import (
    template_to_regex,
    _PLACEHOLDER_PATTERNS,
    _PLACEHOLDER_ORDER,
    _TOKEN_TEMPLATE,
)
_ALTERNATION_THRESHOLD = 6  # máx. nº de alternativas literales antes de caer a '<*>'

_KNOWN_PLACEHOLDER_RE = re.compile(
    '|'.join(re.escape(p) for p in _PLACEHOLDER_PATTERNS)
)

_WHITESPACE_SPLIT_RE = re.compile(r'(\s+)')


_SIMILARITY_THRESHOLD = 0.5  # ratio mínimo de difflib para intentar fusión token a token


def _templates_similarity(t1: str, t2: str) -> float:
    """
    Ratio de similitud [0, 1] entre dos plantillas, basado en
    difflib.SequenceMatcher sobre sus tokens (palabras). Se usa para
    decidir si tiene sentido fusionarlas palabra a palabra o si son
    estructuralmente demasiado distintas.

    Args:
        t1 (str): Primera plantilla.
        t2 (str): Segunda plantilla.

    Returns:
        float: Ratio de similitud entre 0 y 1.
    """
    return difflib.SequenceMatcher(
        a=_tokenize(t1), b=_tokenize(t2), autojunk=False
    ).ratio()


def _templates_are_mergeable(templates: list, threshold: float = _SIMILARITY_THRESHOLD) -> bool:
    """
    Determina si un conjunto de plantillas es lo bastante similar entre
    sí (comparando cada una contra la más larga, como referencia) como
    para intentar una fusión token a token con generalización local.

    Si alguna plantilla difiere demasiado en estructura/longitud de las
    demás, se considera que NO son "mergeables" y se debe recurrir a
    una alternancia de patrones completos en su lugar, para no arriesgar
    perder cobertura de los miembros más distintos.

    Args:
        templates (list): Lista de plantillas a evaluar.
        threshold (float): Ratio mínimo de similitud para considerar
            que dos plantillas son "mergeables".

    Returns:
        bool: True si todas las plantillas son suficientemente similares
            entre sí, False si alguna difiere demasiado.
    """
    unique = list(dict.fromkeys(templates))
    if len(unique) <= 1:
        return True
    reference = max(unique, key=len)
    return all(
        _templates_similarity(reference, t) >= threshold
        for t in unique if t != reference
    )


def _contains_known_placeholder(text: str) -> bool:
    """True si 'text' ya contiene un placeholder de Drain3 (<*>, <NUM>...)."""
    return bool(_KNOWN_PLACEHOLDER_RE.search(text))


def _fragment_to_regex_str(text: str) -> str:
    """
    Convierte un fragmento de texto (token o alternativa multi-palabra)
    que puede contener placeholders de Drain3 embebidos, a su patrón
    regex equivalente (sin anclar, sin compilar).

    Los tramos que son puro whitespace se generalizan como '\\s+' (para
    tolerar diferencias de nº de espacios entre miembros), en vez de
    escaparse literalmente.

    Args:
        text (str): Fragmento de texto a convertir.

    Returns:
        str: Patrón regex equivalente al fragmento dado.
    """
    if _is_whitespace_token(text):
        return r'\s+'

    working = text
    placeholder_map = {}
    for idx, ph in enumerate(_PLACEHOLDER_ORDER):
        token = _TOKEN_TEMPLATE.format(idx)
        if ph in working:
            placeholder_map[token] = ph
            working = working.replace(ph, token)

    escaped = re.escape(working)
    for token, ph in placeholder_map.items():
        escaped_token = re.escape(token)
        escaped = escaped.replace(escaped_token, _PLACEHOLDER_PATTERNS[ph])
    return escaped


class _VariantSlot:
    """
    Posición variable dentro de una plantilla fusionada. Acumula el
    conjunto de fragmentos literales distintos observados en esa
    posición a lo largo de todos los miembros del grupo, para poder
    generar después una alternancia regex explícita en vez de un
    comodín genérico.
    """
    __slots__ = ('alternatives',)

    def __init__(self, alternatives):
        self.alternatives = set(a for a in alternatives if a)

    def merge(self, other_alternatives):
        self.alternatives.update(a for a in other_alternatives if a)


def _chunk_alternatives(chunk: list) -> set:
    """
    Dado un tramo de tokens no coincidente (que puede mezclar strings
    literales y _VariantSlot de una fusión previa), lo reduce a un
    conjunto de alternativas:

    - Si el tramo completo es un único _VariantSlot, se reutilizan
      directamente sus alternativas acumuladas.
    - En cualquier otro caso (tramo de solo strings, o mezcla de
      strings y _VariantSlot), se renderiza cada elemento a texto
      (un _VariantSlot se representa como '<*>') y se unen con
      espacios como una única alternativa de "frase completa".
      Como '<*>' es un placeholder conocido, esta alternativa hará
      que _contains_known_placeholder() detecte la mezcla y el
      resultado caiga a '.*?' en build_group_regex(), evitando
      construir una alternancia inválida o con ambigüedad de tipos.

    Args:
        chunk (list): Lista de tokens (str o _VariantSlot) que difieren
            entre dos plantillas.

    Returns:
        set: Conjunto de alternativas literales (str) para ese tramo.
    """
    if len(chunk) == 1 and isinstance(chunk[0], _VariantSlot):
        return set(chunk[0].alternatives)

    rendered = [
        '<*>' if isinstance(item, _VariantSlot) else item
        for item in chunk
    ]
    joined = ''.join(rendered) 
    return {joined} if joined else set()


def _merge_two_token_lists(tokens_a: list, tokens_b: list) -> list:
    """
    Fusiona dos listas de tokens: los tramos idénticos se conservan
    literales; los tramos donde difieren se convierten en un
    _VariantSlot que acumula TODAS las alternativas vistas (en vez de
    colapsar directamente a un comodín '<*>').

    Args:
        tokens_a (list): Lista de tokens de la primera plantilla.
        tokens_b (list): Lista de tokens de la segunda plantilla.

    Returns:
        list: Lista de tokens fusionada (str y _VariantSlot).
    """
    sm = difflib.SequenceMatcher(a=tokens_a, b=tokens_b, autojunk=False)
    merged = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == 'equal':
            merged.extend(tokens_a[i1:i2])
        else:
            alts = _chunk_alternatives(tokens_a[i1:i2]) | _chunk_alternatives(tokens_b[j1:j2])
            if merged and isinstance(merged[-1], _VariantSlot):
                merged[-1].merge(alts)
            else:
                merged.append(_VariantSlot(alts))
    return merged


def build_merged_tokens(templates: list) -> list:
    """
    Fusiona progresivamente todas las plantillas de un grupo en una
    única lista de tokens (mezcla de str literales y _VariantSlot).

    Args:
        templates (list): Lista de plantillas a fusionar.

    Returns:
        list: Lista de tokens fusionada (str y _VariantSlot).
    """
    unique_templates = list(dict.fromkeys(templates))
    if not unique_templates:
        return []
    merged = _tokenize(unique_templates[0])
    for template in unique_templates[1:]:
        merged = _merge_two_token_lists(merged, _tokenize(template))
    return merged


def merge_member_templates(templates: list) -> str:
    """
    Versión "legible" de la fusión (para mostrar en 'merged_template'):
    cada _VariantSlot se representa como '<*>', igual que antes.

    Args:
        templates (list): Lista de plantillas a fusionar.

    Returns:
        str: Plantilla fusionada, con '<*>' en posiciones variables.
    """
    tokens = build_merged_tokens(templates)
    return ' '.join('<*>' if isinstance(t, _VariantSlot) else t for t in tokens)


def build_group_regex(templates: list, anchor: bool = True,
                       alt_threshold: int = _ALTERNATION_THRESHOLD) -> re.Pattern:
    """
    Genera el regex final de un grupo a partir de TODAS sus plantillas
    miembro.

    - Si las plantillas son suficientemente similares entre sí
      (ver _templates_are_mergeable), se fusionan token a token,
      generalizando con alternancias explícitas o '.*?' las posiciones
      variables (comportamiento habitual, óptimo para variaciones
      puntuales dentro de una misma estructura de frase).

    - Si las plantillas son estructuralmente muy distintas (frases
      distintas, longitudes muy dispares), la fusión token a token NO
      es fiable y puede perder cobertura de miembros. En ese caso, se
      genera en su lugar una ALTERNANCIA de los patrones individuales
      completos de cada miembro: '(?:pat_1|pat_2|...|pat_n)', lo que
      garantiza cobertura del 100% de los miembros sin forzar una
      generalización que no tiene sentido semántico.

    Args:
        templates (list): Plantillas de todos los miembros del grupo.
        anchor (bool): Si True, ancla el regex (fullmatch).
        alt_threshold (int): Nº máx. de alternativas antes de usar '.*?'.

    Returns:
        re.Pattern: Regex compilado.
    """
    unique_templates = list(dict.fromkeys(templates))

    if not _templates_are_mergeable(unique_templates):
        # Plantillas demasiado distintas: alternancia de patrones completos,
        # cada uno generado sin anclar (el ancla se aplica una sola vez al final).
        sub_patterns = [
            build_group_regex([t], anchor=False, alt_threshold=alt_threshold).pattern
            for t in unique_templates
        ]
        unique_sub_patterns = list(dict.fromkeys(sub_patterns))
        pattern_str = (
            unique_sub_patterns[0] if len(unique_sub_patterns) == 1
            else '(?:' + '|'.join(unique_sub_patterns) + ')'
        )
        if anchor:
            pattern_str = f'^{pattern_str}$'
        return re.compile(pattern_str, re.DOTALL)

    tokens = build_merged_tokens(unique_templates)
    if not tokens:
        pattern_str = '.*?'
    else:
        parts = []
        for tok in tokens:
            if isinstance(tok, _VariantSlot):
                alts = sorted(tok.alternatives)
                if not alts or len(alts) > alt_threshold or any(
                    _contains_known_placeholder(a) for a in alts
                ):
                    parts.append(r'.*?')
                else:
                    escaped_alts = sorted({_fragment_to_regex_str(a) for a in alts})
                    parts.append(
                        escaped_alts[0] if len(escaped_alts) == 1
                        else '(?:' + '|'.join(escaped_alts) + ')'
                    )
            else:
                parts.append(_fragment_to_regex_str(tok))
        pattern_str = ''.join(parts)

    if anchor:
        pattern_str = f'^{pattern_str}$'
    return re.compile(pattern_str, re.DOTALL)

def find_matching_existing_group(template: str, existing_groups: list) -> dict:
    """
    Comprueba si 'template' ya está cubierto semánticamente por alguna de
    las regex ya existentes en 'existing_groups' (fullmatch, ya que las
    regex se generan con anchor=True en generate_regex_groups()).

    Devuelve el primer grupo existente cuya regex matchea, o None si
    ninguna lo cubre.

    Args:
        template (str): El representative_template del grupo nuevo.
        existing_groups (list): Lista de grupos existentes, cada uno con
            'pattern' y 'flags'.

    Returns:
        dict or None: El grupo existente que cubre el template, o None si no hay match.
    """
    for group in existing_groups:
        pattern = group.get("pattern")
        flags = group.get("flags", 0)
        if not pattern:
            continue
        try:
            compiled = re.compile(pattern, flags)
        except re.error:
            continue
        if compiled.fullmatch(template):
            return group
    return None


def _group_key(group: dict) -> tuple:
    """
    Clave de identidad de un grupo, usada para detectar si ya existe en
    el fichero de salida. Se basa en group_id + representative_cluster_id
    + representative_template porque:
    - group_id puede coincidir por casualidad entre ejecuciones distintas
      de semantic_grouping.py (labels reasignados).
    - representative_cluster_id + representative_template juntos
      identifican de forma mucho más fiable si es "el mismo grupo"
      semántico, incluso si el group_id numérico cambia.
    """
    return (
        group.get("representative_template"),
    )


def load_existing_regex_groups(output_path: str) -> list:
    """
    Carga los grupos ya existentes en x_template_regex.json, si el
    fichero existe. Devuelve lista vacía si no existe o si está corrupto
    (en cuyo caso avisa, pero no borra nada del fichero original).
    """
    if not os.path.exists(output_path):
        return []

    try:
        with open(output_path, encoding='utf-8') as f:
            data = json.load(f)
        return data.get('groups', [])
    except (json.JSONDecodeError, KeyError) as e:
        print(f"  ⚠️  No se pudo leer {output_path} ({e}), se tratará como vacío "
              f"(el fichero original NO se toca hasta el guardado final)")
        return []


def derive_original_template_path(groups_input_path: str) -> str:
    """
    Deriva la ruta del fichero 'x_template.json' original (el que produjo
    extract_templates.py, con TODOS los clusters individuales) a partir
    de la ruta de 'x_template_semantic_groups.json'.

    Ej: 'templates/ais_template_semantic_groups.json' ->
        'templates/ais_template.json'

    Args:
        groups_input_path (str): Ruta al fichero de grupos semánticos.

    Returns:
        str: Ruta al fichero de templates original (por cluster_id).
    """
    suffix = '_semantic_groups.json'
    if groups_input_path.endswith(suffix):
        base = groups_input_path[:-len(suffix)]
        return f"{base}.json"
    return groups_input_path.replace('_semantic_groups.json', '.json')


def load_cluster_templates(template_file_path: str) -> dict:
    """
    Carga el mapa {cluster_id: template} a partir del fichero
    'x_template.json' original (salida de extract_templates.py), que
    contiene el detalle de TODOS los clusters individuales antes de la
    agrupación semántica.

    Args:
        template_file_path (str): Ruta al fichero 'x_template.json'.

    Returns:
        dict: Mapa cluster_id (int) -> template (str). Vacío si el
            fichero no existe o no se puede leer.
    """
    if not os.path.exists(template_file_path):
        print(f"  ⚠️  No se encontró el fichero de templates original "
              f"'{template_file_path}'; se usará solo representative_template "
              f"para todos los grupos (regex potencialmente demasiado específica)")
        return {}

    try:
        with open(template_file_path, encoding='utf-8') as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"  ⚠️  Error leyendo '{template_file_path}': {e}")
        return {}

    clusters = data.get('clusters', [])
    return {c['cluster_id']: c['template'] for c in clusters if 'template' in c}


def _tokenize(template: str) -> list:
    """
    Tokeniza un template preservando los tramos de espacio en blanco
    como tokens propios (en vez de asumir un único espacio simple entre
    palabras). Esto evita desajustes cuando el template original tiene
    espacios múltiples, tabulaciones, etc.

    Ej: "a   b" -> ['a', '   ', 'b']   (en vez de ['a', '', '', 'b'])

    Args:
        template (str): Plantilla a tokenizar.

    Returns:
        list: Lista de tokens (str), incluyendo tramos de whitespace.
    """
    return [t for t in _WHITESPACE_SPLIT_RE.split(template) if t != '']

def _is_whitespace_token(token) -> bool:
    return isinstance(token, str) and token != '' and token.strip() == ''

def _extract_cluster_id(member) -> int:
    """
    Normaliza un elemento de 'member_cluster_ids', que puede venir como
    int/str directamente, o como dict (ej. {'cluster_id': 5, ...}),
    según la versión de semantic_grouping.py que lo generó.

    Args:
        member: elemento de member_cluster_ids (int, str o dict).

    Returns:
        El cluster_id normalizado (mismo tipo que las keys de
        cluster_templates, típicamente int).
    """
    if isinstance(member, dict):
        return member.get('cluster_id')
    return member

def _extract_member_template(member, cluster_templates: dict, fallback: str) -> str:
    """
    Obtiene la plantilla real de un miembro de 'member_cluster_ids'.

    Prioridad:
    1. Si el miembro es un dict con campo 'template', se usa directamente
       (fuente más fiable, ya viene del propio JSON de grupos semánticos).
    2. Si no, se busca por cluster_id en cluster_templates (fichero
       x_template.json original), probando tanto la clave tal cual como
       su versión str/int para evitar desajustes de tipo.
    3. Si nada de lo anterior funciona, se usa 'fallback'
       (representative_template).

    Args:
        member: elemento de member_cluster_ids (int, str o dict).
        cluster_templates (dict): Mapa cluster_id -> template.
        fallback (str): Template a usar si no se encuentra nada mejor.

    Returns:
        str: Template del miembro.
    """
    if isinstance(member, dict) and member.get('template'):
        return member['template']

    cid = _extract_cluster_id(member)
    if cid in cluster_templates:
        return cluster_templates[cid]
    # Probar conversión de tipo (int <-> str) por si las keys no coinciden
    try:
        cid_int = int(cid)
        if cid_int in cluster_templates:
            return cluster_templates[cid_int]
    except (TypeError, ValueError):
        pass
    try:
        cid_str = str(cid)
        if cid_str in cluster_templates:
            return cluster_templates[cid_str]
    except TypeError:
        pass

    return fallback


def generate_regex_groups(groups: list, cluster_templates: dict, anchor: bool = True) -> list:
    """
    Compila el regex para cada grupo de la lista dada (ya filtrada, solo
    los nuevos), fusionando las plantillas de TODOS sus
    member_cluster_ids (no solo la representativa) para generalizar
    correctamente el patrón.

    Args:
        groups (list): Lista de grupos a procesar, cada uno con
            'representative_template', 'member_cluster_ids' y demás
            metadatos.
        cluster_templates (dict): Mapa cluster_id -> template, cargado
            desde el fichero 'x_template.json' original (usado como
            fallback si el miembro no trae su propio 'template').
        anchor (bool): Si True, el regex generado se ancla al inicio y fin
            de la cadena (equivalente a fullmatch). Si False, se permite
            match parcial (search).

    Returns:
        list: Lista de grupos con el regex compilado, lista para guardar en
            x_template_regex.json.
    """
    result_groups = []
    skipped_groups = 0

    for group in groups:
        representative_template = group['representative_template']
        member_cluster_ids = group.get('member_cluster_ids', [])
        event_type = group.get('event_type')
        severity = group.get('severity')

        member_templates = [
            _extract_member_template(m, cluster_templates, representative_template)
            for m in member_cluster_ids
        ] or [representative_template]

        merged_template = merge_member_templates(member_templates)

        try:
            compiled = build_group_regex(member_templates, anchor=anchor)
        except Exception as e:
            print(f"  ⚠️  Error compilando grupo {group['group_id']} "
                  f"(merged: {merged_template[:60]}...): {e}")
            skipped_groups += 1
            continue

        result_groups.append({
            "group_id": group["group_id"],
            "representative_cluster_id": group["representative_cluster_id"],
            "representative_template": representative_template,
            "merged_template": merged_template,
            "pattern": compiled.pattern,
            "flags": compiled.flags,
            "event_type": event_type,
            "severity": severity,
            "member_cluster_ids": member_cluster_ids,
        })

    if skipped_groups > 0:
        print(f"  ⚠️  {skipped_groups} grupo(s) omitidos por error de compilación")

    return result_groups


def save_regex_groups(groups: list, output_path: str) -> None:
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump({'groups': groups}, f, ensure_ascii=False, indent=2)

    print(f"💾 Guardado: {output_path} ({len(groups)} grupos)")


def derive_output_path(input_path: str) -> str:
    """
    'templates/alert_jde_template_semantic_groups.json' ->
    'templates/alert_jde_template_regex.json'
    """
    suffix = '_semantic_groups.json'
    if input_path.endswith(suffix):
        base = input_path[:-len(suffix)]
        return f"{base}_regex.json"
    return input_path.replace('.json', '_regex.json')


def process_groups_file(input_path: str) -> None:
    """
    Procesa un fichero x_template_semantic_groups.json, genera/actualiza
    x_template_regex.json de forma incremental (sin sobrescribir grupos
    ya existentes). El regex de cada grupo se genera fusionando las
    plantillas de todos sus member_cluster_ids.

    Args:
        input_path (str): Ruta al fichero x_template_semantic_groups.json.

    Returns:
        None
    """
    with open(input_path, encoding='utf-8') as f:
        groups_data = json.load(f)

    all_groups = groups_data.get('groups', [])
    total_groups = len(all_groups)
    total_members = sum(g['num_members'] for g in all_groups)

    print(f"📊 {total_groups} grupo(s) semántico(s), {total_members} cluster(s) individuales")

    # Cargamos el mapa cluster_id -> template original, necesario para
    # fusionar TODAS las plantillas de cada grupo (no solo la representativa)
    original_template_path = derive_original_template_path(input_path)
    cluster_templates = load_cluster_templates(original_template_path)
    if cluster_templates:
        print(f"  📎 {len(cluster_templates)} template(s) individuales cargados desde "
              f"{os.path.basename(original_template_path)}")

    output_path = derive_output_path(input_path)

    # Cargar grupos ya existentes para no sobreescribirlos
    existing_groups = load_existing_regex_groups(output_path)
    existing_keys = {_group_key(g) for g in existing_groups}

    if existing_groups:
        print(f"  📎 {len(existing_groups)} grupo(s) ya existentes en "
              f"{os.path.basename(output_path)} (se conservan sin tocar)")

    # Filtrar primero por clave exacta (mismo representative_template)
    candidate_groups = [g for g in all_groups if _group_key(g) not in existing_keys]
    skipped_by_key = total_groups - len(candidate_groups)

    if skipped_by_key > 0:
        print(f"  ⏭️  {skipped_by_key} grupo(s) omitidos (clave ya existente)")

    # De los candidatos, comprobar si ya están
    # cubiertos por el REGEX de algún grupo existente (aunque su
    # representative_template no coincida literalmente con ninguno ya
    # guardado). Esto evita crear un grupo redundante cuando un nuevo
    # template, aunque distinto textualmente, cae dentro del patrón ya
    # generalizado de un grupo previo.
    new_groups = []
    covered_by_regex = 0
    for group in candidate_groups:
        template = group.get("representative_template")
        matched = find_matching_existing_group(template, existing_groups)
        if matched is not None:
            covered_by_regex += 1
            print(f"  🔎 Grupo '{template[:60]}...' ya cubierto por regex "
                  f"del grupo existente '{matched.get('representative_template', '')[:60]}...' "
                  f"(event_type={matched.get('event_type')}), se omite")
        else:
            new_groups.append(group)

    if covered_by_regex > 0:
        print(f"  ⏭️  {covered_by_regex} grupo(s) adicionales omitidos "
              f"(ya cubiertos por una regex existente)")

    missing_metadata = sum(
        1 for g in new_groups
        if g.get('event_type') is None or g.get('severity') is None
    )
    if missing_metadata > 0:
        print(f"  ⚠️  {missing_metadata} grupo(s) nuevo(s) sin 'event_type'/'severity' asignado (quedarán como null)")

    if new_groups:
        compiled_new_groups = generate_regex_groups(new_groups, cluster_templates)
        print(f"  ✓ {len(compiled_new_groups)} grupo(s) nuevo(s) convertido(s) a regex")
    else:
        compiled_new_groups = []
        print(f"  ✓ Nada nuevo que convertir")

    if not new_groups and existing_groups:
        print(f"  ℹ️  Sin cambios, se mantiene el fichero existente")
        return

    # Merge: existentes (sin tocar, tal cual estaban) + nuevos compilados
    merged_groups = existing_groups + compiled_new_groups

    save_regex_groups(merged_groups, output_path)


def main():
    parser = argparse.ArgumentParser(
        description="Genera/actualiza regex por grupo a partir de "
                     "x_template_semantic_groups.json, de forma INCREMENTAL: "
                     "los grupos ya presentes en x_template_regex.json nunca "
                     "se sobrescriben. El regex se genera fusionando las "
                     "plantillas de TODOS los member_cluster_ids del grupo."
    )
    parser.add_argument('input', type=str, help="Ruta a x_template_semantic_groups.json")
    args = parser.parse_args()

    process_groups_file(args.input)


if __name__ == '__main__':
    main()