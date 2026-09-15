#!/usr/bin/env python3
"""
generate_regex_from_groups.py

Toma el resultado de semantic_grouping.py (x_template_semantic_groups.json)
y genera/actualiza un 'x_template_regex.json' donde CADA GRUPO conserva su
propia estructura (group_id, representative_cluster_id,
representative_template, regex, event_type, severity, member_cluster_ids).

Uso:
    python drain/generate_regex_from_groups.py templates/alert_jde_template_semantic_groups.json
"""
import json
import os
import re
import argparse
import sys 

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from template_generator.template_to_regex import template_to_regex

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


def generate_regex_groups(groups: list, anchor: bool = True) -> list:
    """
    Compila el regex para cada grupo de la lista dada (ya filtrada, solo
    los nuevos), a partir de 'representative_template'.

    Args:
        groups (list): Lista de grupos a procesar, cada uno con 
            'representative_template' y demás metadatos.
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
        event_type = group.get('event_type')
        severity = group.get('severity')

        try:
            compiled = template_to_regex(representative_template, anchor=anchor)
        except Exception as e:
            print(f"  ⚠️  Error compilando grupo {group['group_id']} "
                  f"(representative: {representative_template[:60]}...): {e}")
            skipped_groups += 1
            continue

        result_groups.append({
            "group_id": group["group_id"],
            "representative_cluster_id": group["representative_cluster_id"],
            "representative_template": representative_template,
            "pattern": compiled.pattern,
            "flags": compiled.flags,
            "event_type": event_type,
            "severity": severity,
            "member_cluster_ids": group["member_cluster_ids"],
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
    ya existentes).

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

    output_path = derive_output_path(input_path)

    # ✅ Cargar grupos ya existentes para no sobreescribirlos
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

    # ✅ NUEVO: de los candidatos restantes, comprobar si ya están
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
        compiled_new_groups = generate_regex_groups(new_groups)
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
                     "se sobrescriben."
    )
    parser.add_argument('input', type=str, help="Ruta a x_template_semantic_groups.json")
    args = parser.parse_args()

    process_groups_file(args.input)


if __name__ == '__main__':
    main()