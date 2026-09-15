"""
orchestrator.py

Punto de entrada principal del template_generator. Ejecuta de forma
secuencial:

    drain3 parsed3  ->  extract_templates.process_all_origins  ->  semantic_grouping.semantic_group_templates  ->  generate_regex_from_groups

FLUJO DE USO (log completamente nuevo):
    1. El desarrollador crea manualmente config/<origen>_config.py con
       una config mínima y ejecuta el parsing normal (parsing/init.py)
       generando parsed_logs/<origen>/*.parquet.
    2. Se ejecuta 'drain_unified.py parsed3' sobre ese origen, que
       genera drain3_output_folder/<origen>/<origen>_drain3_parsed_full.json.
    3. extract_templates.process_all_origins() localiza TODOS los
       ficheros '*_drain3_parsed_full.json' bajo drain3_output_folder
       (no solo el del origen que nos interesa) y los normaliza a
       templates/<origen>_template.json.
    4. semantic_grouping.semantic_group_templates() lee ÚNICAMENTE
       templates/<origen>_template.json y agrupa templates similares
       en templates/<origen>_template_semantic_groups.json.
    5. generate_regex_from_groups genera propuestas de regex a partir
       de esos grupos, para revisión manual del desarrollador.
"""

import os
import sys
import json
import subprocess
from datetime import datetime
from typing import List, Dict, Any, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from storage.factory import get_storage_backend

from extract_templates import process_single_origin
from semantic_grouping import semantic_group_templates
from generate_regex_from_groups import process_groups_file, derive_output_path



DRAIN_UNIFIED_SCRIPT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "drain", "drain_unified.py"
)


def _run_drain3_parsed(origin: str, parsed_folder: str = "parsed_logs",
                        output_folder: str = "drain3_parsed_results",
                        depth: Optional[int] = None, st: Optional[float] = None,
                        max_children: Optional[int] = None) -> None:
    """
    Ejecuta 'drain_unified.py parsed3' para un único origen, invocando
    el script como subproceso.

    Args:
        origin: nombre del origen a procesar (ej: 'jde', 'ais').
        parsed_folder: carpeta con los parquet parseados (entrada de drain3).
        output_folder: carpeta de salida de 'drain_unified.py parsed3'.
        depth, st, max_children: hiperparámetros de Drain3.

    Raises:
        RuntimeError: si el subproceso devuelve un código de salida distinto de 0.

    Returns:
        None
    """
    cmd = [
        sys.executable, DRAIN_UNIFIED_SCRIPT, "parsed3",
        "--origin", origin,
        "--parsed-folder", parsed_folder,
        "--output", output_folder,
    ]
    if depth is not None:
        cmd += ["--depth", str(depth)]
    if st is not None:
        cmd += ["--st", str(st)]
    if max_children is not None:
        cmd += ["--max-children", str(max_children)]

    print(f"\n{'='*70}")
    print(f"▶️  [1/4] Ejecutando: {' '.join(cmd)}")
    print(f"{'='*70}")

    result = subprocess.run(cmd, capture_output=False)
    if result.returncode != 0:
        raise RuntimeError(
            f"drain_unified.py parsed3 falló para origen '{origin}' "
            f"(exit code {result.returncode})"
        )


def generate_templates_for_origin(
    origin: str,
    parsed_folder: str = "parsed_logs",
    drain3_output_folder: str = "drain3_parsed_results",
    templates_folder: str = "templates",
    depth: Optional[int] = None,
    st: Optional[float] = None,
    max_children: Optional[int] = None,
    similarity_threshold: float = 0.6,
    skip_drain: bool = False,
) -> Dict[str, Any]:
    """
    Orquesta el flujo completo de generación de templates para un
    origen ya configurado (config/<origin>_config.py existente y con
    al menos una ejecución previa de parsing).

    Args:
        origin: nombre del origen a procesar (ej: 'jde', 'ais').
        parsed_folder: carpeta con los parquet parseados (entrada de drain3).
        drain3_output_folder: carpeta de salida de 'drain_unified.py parsed3'.
        templates_folder: carpeta de salida de extract_templates
            (equivalente a 'templates/' en el proyecto).
        depth, st, max_children: hiperparámetros de Drain3.
        similarity_threshold: distance_threshold pasado a
            semantic_group_templates (cosine distance, no similitud;
            más bajo = grupos más estrictos).
        skip_drain: si True, no re-ejecuta drain3 (reutiliza el
            '*_drain3_parsed_full.json' ya existente).

    Returns:
        dict con: {"templates_path", "semantic_groups_path",
                   "num_templates", "num_groups", "regex_proposals"}
    """
    storage, execution_mode = get_storage_backend()
    print(f"🌐 Modo de ejecución: {execution_mode}")
    print(f"🎯 Origen a analizar: {origin}")

    all_parquets = storage.list_files(prefix=parsed_folder, extension=".parquet")

    existing_parquets = [
        full_path for full_path, filename in all_parquets
        if filename == f"{origin}.parquet"
        or filename.endswith(f"_{origin}.parquet")
    ]
    if not existing_parquets:
        raise FileNotFoundError(
            f"No se encontraron ficheros '*_{origin}.parquet' en "
            f"'{parsed_folder}/'. Antes de usar template_generator debes "
            f"crear config/{origin}_config.py y ejecutar el parsing normal "
            f"(parsing/init.py) para ese origen."
        )
    print(f"✓ {len(existing_parquets)} ficheros parquet encontrados para origen '{origin}' en '{parsed_folder}/'")

    os.makedirs(templates_folder, exist_ok=True)

    # --- 1. Drain3 sobre parsed_logs del origen ---
    if not skip_drain:
        _run_drain3_parsed(
            origin=origin,
            parsed_folder=parsed_folder,
            output_folder=drain3_output_folder,
            depth=depth, st=st, max_children=max_children,
        )
    else:
        print(f"\n⏭️  [1/4] Saltando ejecución de Drain3 (skip_drain=True)")

    # --- 2. extract_templates: procesa TODOS los orígenes detectados ---
    # bajo drain3_output_folder y guarda templates/<origen>_template.json
    # para cada uno (no solo para 'origin', ver nota en el docstring).
    print(f"\n{'='*70}")
    print(f"▶️  [2/4] extract_templates.process_single_origin('{origin}')")
    print(f"{'='*70}")
    templates_path = process_single_origin(
        origin=origin,
        input_folder=drain3_output_folder,
        output_folder=templates_folder,
    )

    with open(templates_path, encoding="utf-8") as f:
        num_templates = len(json.load(f).get("clusters", []))
    print(f"✓ {num_templates} templates disponibles en {templates_path}")

    with open(templates_path, encoding="utf-8") as f:
        num_templates = len(json.load(f).get("clusters", []))
    print(f"✓ {num_templates} templates disponibles en {templates_path}")

    # --- 3. Agrupamiento semántico ---
    print(f"\n{'='*70}")
    print(f"▶️  [3/4] semantic_grouping.semantic_group_templates(threshold={similarity_threshold})")
    print(f"{'='*70}")
    semantic_result = semantic_group_templates(templates_path, similarity_threshold)

    semantic_groups_path = os.path.join(
        templates_folder, f"{origin}_template_semantic_groups.json"
    )
    with open(semantic_groups_path, "w", encoding="utf-8") as f:
        json.dump(semantic_result, f, ensure_ascii=False, indent=2)

    num_groups = len(semantic_result.get("groups", []))
    print(f"✓ {num_templates} templates agrupados en {num_groups} grupos semánticos")
    print(f"💾 Guardado en: {semantic_groups_path}")

    # --- 4. Generación de propuestas de regex por grupo ---
    print(f"\n{'='*70}")
    print(f"▶️  [4/4] generate_regex_from_groups.process_groups_file()")
    print(f"{'='*70}")
    process_groups_file(semantic_groups_path)

    regex_path = derive_output_path(semantic_groups_path)
    regex_proposals = None
    num_regex_groups = None
    if os.path.exists(regex_path):
        with open(regex_path, encoding="utf-8") as f:
            regex_data = json.load(f)
        regex_proposals = regex_data.get("groups", [])
        num_regex_groups = len(regex_proposals)
        print(f"✓ {num_regex_groups} grupo(s) con regex disponibles en {regex_path}")
    else:
        print(f"  ⚠️  No se generó '{regex_path}' (revisa logs de process_groups_file)")

    print(f"\n{'='*70}")
    print(f"✅ TEMPLATE GENERATOR COMPLETADO para origen '{origin}'")
    print(f"{'='*70}")
    print(f"  Templates:        {num_templates}")
    print(f"  Grupos semánticos:{num_groups}")
    if num_regex_groups is not None:
        print(f"  Grupos con regex: {num_regex_groups}")
    print(f"{'='*70}\n")

    return {
        "templates_path": templates_path,
        "semantic_groups_path": semantic_groups_path,
        "regex_path": regex_path,
        "num_templates": num_templates,
        "num_groups": num_groups,
        "regex_proposals": regex_proposals,
    }

if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(
        description="Orquesta el flujo completo de template_generator para un origen"
    )
    parser.add_argument('origin', type=str, help="Nombre del origen (ej: 'jde', 'ais')")
    parser.add_argument('--parsed-folder', type=str, default='parsed_logs')
    parser.add_argument('--drain3-output-folder', type=str, default='drain3_parsed_results')
    parser.add_argument('--templates-folder', type=str, default='templates')
    parser.add_argument('--depth', type=int, default=None)
    parser.add_argument('--st', type=float, default=None)
    parser.add_argument('--max-children', type=int, default=None)
    parser.add_argument('--similarity-threshold', type=float, default=0.6)
    parser.add_argument('--skip-drain', action='store_true',
                         help="No re-ejecutar Drain3, reutilizar el "
                              "'*_drain3_parsed_full.json' ya existente")
    args = parser.parse_args()

    generate_templates_for_origin(
        origin=args.origin,
        parsed_folder=args.parsed_folder,
        drain3_output_folder=args.drain3_output_folder,
        templates_folder=args.templates_folder,
        depth=args.depth,
        st=args.st,
        max_children=args.max_children,
        similarity_threshold=args.similarity_threshold,
        skip_drain=args.skip_drain,
    )