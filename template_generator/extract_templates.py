"""
extract_templates.py

Módulo para extraer templates (clusters) desde los resultados completos de Drain3 ('*_drain3_parsed_full.json') y generar ficheros
"""
import json
import os
import re
import glob

# Patrón para detectar ficheros "x_drain3_parsed_full.json" y extraer el
# nombre de origen "x" a partir del nombre del fichero.
_FULL_RESULT_RE = re.compile(r'^(?P<origin>.+)_drain3_parsed_full\.json$')


def find_full_result_files(input_folder: str) -> list:
    """
    Busca recursivamente dentro de input_folder (una subcarpeta por
    origen, ej: drain3_parsed_results/ais/ais_drain3_parsed_full.json)
    todos los ficheros que sigan el patrón 'x_drain3_parsed_full.json'
    y devuelve una lista de tuplas (origin, full_path).

    Args:
        input_folder (str): Carpeta raíz donde buscar los ficheros.
    
    Returns:
        list: Lista de tuplas (origin, full_path) para cada fichero encontrado.
    """
    pattern = os.path.join(input_folder, '**', '*_drain3_parsed_full.json')
    matches = []
    for path in glob.glob(pattern, recursive=True):
        filename = os.path.basename(path)
        m = _FULL_RESULT_RE.match(filename)
        if m:
            matches.append((m.group('origin'), path))
        else:
            print(f"  ⚠️  Nombre inesperado, se ignora: {filename}")
    return matches


def extract_clusters_from_full_result(full_result_path: str) -> list:
    """
    Lee un fichero 'x_drain3_parsed_full.json'.

    Args:
        full_result_path (str): Ruta al fichero 'x_drain3_parsed_full.json'.

    Returns:
        list: Lista de clusters filtrados con 'percentage' > 0.
    """
    with open(full_result_path, encoding='utf-8') as f:
        data = json.load(f)

    clusters = data.get('clusters')
    if clusters is None:
        raise KeyError(f"No se encontró la clave 'clusters' en {full_result_path}")
    
    return clusters


def save_template_file(clusters: list, output_path: str) -> None:
    """
    Guarda el array de clusters en un fichero 'x_template.json', con la
    misma estructura que ya usan ais_template.json / jde_template.json
    (clave raíz 'clusters').

    Args:
        clusters (list): Lista de clusters a guardar.
        output_path (str): Ruta de salida para el fichero 'x_template.json'.

    Returns:
        None
    """
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump({'clusters': clusters}, f, ensure_ascii=False, indent=2)

    print(f"  💾 Guardado: {output_path} ({len(clusters)} clusters)")


def process_all_origins(
    input_folder: str = 'drain3_parsed_results',
    output_folder: str = 'templates'
) -> None:
    """
    Procesa todos los orígenes detectados en input_folder:
    1) Localiza cada 'x_drain3_parsed_full.json'.
    2) Extrae el array 'clusters'.
    3) Guarda 'templates/x_template.json'.

    Args:
        input_folder: carpeta raíz donde buscar los
            'x_drain3_parsed_full.json' (recursivo).
        output_folder: carpeta de salida para 'x_template.json'.

    Returns:
        None
    """
    os.makedirs(output_folder, exist_ok=True)

    origins = find_full_result_files(input_folder)
    if not origins:
        print(f"❌ No se encontraron ficheros '*_drain3_parsed_full.json' en {input_folder}")
        return

    print(f"🔍 {len(origins)} origen(es) detectado(s): {[o for o, _ in origins]}")

    for origin, full_path in origins:
        print(f"\n📂 Procesando origen: {origin}")
        try:
            clusters = extract_clusters_from_full_result(full_path)
            output_path = os.path.join(output_folder, f"{origin}_template.json")
            save_template_file(clusters, output_path)
        except (json.JSONDecodeError, KeyError, OSError) as e:
            print(f"  ❌ Error procesando {origin}: {e}")
            
def process_single_origin(
    origin: str,
    input_folder: str = 'drain3_parsed_results',
    output_folder: str = 'templates'
) -> str:
    """
    Igual que process_all_origins() pero restringido a un único
    origen, evitando reprocesar (y sobrescribir) los '*_template.json'
    de otros orígenes que puedan existir bajo input_folder de
    ejecuciones anteriores.

    Args:
        origin: nombre del origen a procesar (ej: 'jde', 'ais').
        input_folder: carpeta raíz donde buscar
            '<origin>_drain3_parsed_full.json' (recursivo).
        output_folder: carpeta de salida para '<origin>_template.json'.

    Returns:
        Ruta al fichero '<origin>_template.json' generado.

    Raises:
        FileNotFoundError: si no se encuentra el fichero
            '<origin>_drain3_parsed_full.json' esperado.
    """
    os.makedirs(output_folder, exist_ok=True)

    all_origins = find_full_result_files(input_folder)
    matches = [(o, path) for o, path in all_origins if o == origin]

    if not matches:
        raise FileNotFoundError(
            f"No se encontró '{origin}_drain3_parsed_full.json' bajo "
            f"'{input_folder}/'. Verifica que 'drain_unified.py parsed3' "
            f"se ejecutó correctamente para este origen."
        )

    if len(matches) > 1:
        print(f"  ⚠️  Se encontraron {len(matches)} coincidencias para "
              f"'{origin}', se usará la primera: {matches[0][1]}")

    _, full_path = matches[0]

    print(f"\n📂 Procesando origen: {origin}")
    clusters = extract_clusters_from_full_result(full_path)
    output_path = os.path.join(output_folder, f"{origin}_template.json")
    save_template_file(clusters, output_path)

    return output_path

if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(
        description="Extrae templates ('clusters') desde los resultados "
                     "de Drain3 ('*_drain3_parsed_full.json')."
    )
    parser.add_argument('--input-folder', type=str, default='drain3_parsed_results',
                         help="Carpeta raíz donde buscar los "
                              "'*_drain3_parsed_full.json' (default: drain3_parsed_results)")
    parser.add_argument('--output-folder', type=str, default='templates',
                         help="Carpeta de salida para '<origin>_template.json' (default: templates)")

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--origin', type=str,
                        help="Procesa únicamente este origen (ej: 'jde', 'ais')")
    group.add_argument('--all', action='store_true',
                        help="Procesa todos los orígenes detectados en --input-folder")

    args = parser.parse_args()

    if args.all:
        process_all_origins(args.input_folder, args.output_folder)
    else:
        process_single_origin(args.origin, args.input_folder, args.output_folder)