"""
template_to_regex.py

Modulo para convertir templates de Drain3 (con placeholders como <*>, <NUM>, <ALPHANUM>, <UUID>, <PATH>...) en expresiones regulares compiladas de Python, y viceversa.
"""

import re
import json 
import os 

# Orden de especificidad: de más concreto a más genérico. Esto importa
# porque <*> podría "comerse" el texto de otro placeholder si no
# procesamos primero los más específicos.
_PLACEHOLDER_PATTERNS = {
    '<NUM>':       r'\d+',
    '<UUID>':      r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}',
    '<PATH>':      r'[\w/.\-]+',
    '<ALPHANUM>':  r'[A-Za-z0-9_]+',
    '<HEX>':       r'0x[0-9a-fA-F]+',
    '<IP>':        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}',
    '<ORCH_JSON>':       r'\[.*\]',
    '<SQL_QUERY_UPPER>': r'(?:SELECT|INSERT\s+INTO|UPDATE|DELETE\s+FROM|SELECT\s+DISTINCT).*?(?=;|$)',
    '<SQL_QUERY_LOWER>': r'(?:select|insert\s+into|update|delete\s+from|select\s+distinct).*?(?=;|$)',
    '<SQL_QUERY_CAP>':   r'(?:Select|Insert\s+into|Update|Delete\s+from|Select\s+distinct).*?(?=;|$)',
    '<LIBCODE>':         r'LIB\d{7}',
    '<JDECODE>':         r'[A-Z]\d{6}',
    '<CONTEXT_ID>':      r'Context ID:\s*[\d.:]+',
    '<TIMESTAMP>':       r'Time:\s*\d{2}-[A-Z]{3}-\d{4}\s+\d{2}:\d{2}:\d{2}',
    '<SOAP_ENVELOPE>':   r'<[a-zA-Z0-9]+:Envelope\b.*?</[a-zA-Z0-9]+:Envelope>',
    '<MIME_PART>':       r'------=_Part_\d+_\d+\.\d+.*?(?=------=_Part_|\Z)',
    '<BASE64_BLOB>':     r'[A-Za-z0-9+/]{40,}={0,2}',
    '<JSON_BLOB>':       r'\{.*?\}',
    '<XML_BLOCK>':       r'<[a-zA-Z][\w:-]*\b[^>]*>.*?</[a-zA-Z][\w:-]*>',
    '<PEM_BLOCK>':       r'-----BEGIN [A-Z ]+-----.*?-----END [A-Z ]+-----',
    '<JWT>':             r'eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+',
    '<STACKTRACE>':      r'(?:\s*at\s+[\w.$]+\([^)]*\)\s*\n?){2,}|(?:\s*File\s+"[^"]+",\s+line\s+\d+.*\n?){2,}',
    '<LONG_LIST>':       r'\((?:\s*\d+\s*,){5,}\s*\d+\s*\)',
    '<URL_WITH_QUERY>':  r'https?://[^\s"\'<>]+\?[^\s"\'<>]+',
    '<PID>':             r'\d+',
    '<*>':         r'.*?',   # comodín genérico de Drain, lazy para evitar backtracking excesivo
}

_TOKEN_TEMPLATE = "\x00PH{}\x00"
_SPACE_TOKEN = "\x00SPACE\x00"

# Se ordenan las claves por longitud descendente para que, por ejemplo,
# '<ALPHANUM>' se procese antes que un eventual '<A>' más corto (no aplica
# aquí, pero es una guarda barata y correcta en general).
_SORTED_PLACEHOLDERS = sorted(_PLACEHOLDER_PATTERNS.keys(), key=len, reverse=True)

# Token único e improbable de colisionar con el texto real del template,
# usado como marcador temporal mientras escapamos el resto del texto.
_TOKEN_TEMPLATE = "\x00PH{}\x00"


def template_to_regex(template: str, anchor: bool = True) -> re.Pattern:
    """
    Convierte un template de Drain3 (con placeholders <*>, <NUM>,
    <ALPHANUM>, <UUID>, <PATH>...) en un regex compilado que matchea
    líneas de log reales generadas a partir de ese template.

    Estrategia (para no romper el escaping):
    1) Sustituir cada placeholder por un token temporal único.
    2) Sustituir cada espacio literal por un token temporal único
       (¡ANTES de escapar!, para que re.escape() no vuelva a escapar
       el backslash que insertaremos después).
    3) Escapar todo el texto restante con re.escape().
    4) Reemplazar los tokens temporales (placeholders y espacios) por
       sus patrones regex reales.
    """
    tokens = []

    def _replace_placeholder(match):
        ph = match.group(0)
        idx = len(tokens)
        tokens.append(ph)
        return _TOKEN_TEMPLATE.format(idx)

    # Paso 1: sustituir placeholders conocidos por tokens temporales
    placeholder_re = re.compile('|'.join(re.escape(p) for p in _SORTED_PLACEHOLDERS))
    tokenized = placeholder_re.sub(_replace_placeholder, template)

    # Paso 2: sustituir espacios por un token temporal ANTES de escapar
    tokenized = re.sub(r' +', lambda m: _SPACE_TOKEN, tokenized)

    # Paso 3: escapar el resto del texto (literal)
    escaped = re.escape(tokenized)

    # Deshacer el escaping de los \x00 de nuestros tokens
    escaped = escaped.replace(re.escape("\x00"), "\x00")

    # Paso 4a: sustituir el token de espacio por \s+ usando .replace()
    # (NO re.sub con string repl, para no interpretar '\' como backreference)
    escaped = escaped.replace(_SPACE_TOKEN, r'\s+')

    # Paso 4b: sustituir cada token temporal de placeholder por su patrón regex real
    for idx, ph in enumerate(tokens):
        token = _TOKEN_TEMPLATE.format(idx)
        pattern = _PLACEHOLDER_PATTERNS[ph]
        escaped = escaped.replace(token, pattern)

    if anchor:
        escaped = f'^{escaped}$'

    return re.compile(escaped, re.DOTALL)


def templates_to_regex_map(clusters: list, anchor: bool = True) -> dict:
    """
    Dado el JSON de clusters de Drain (como ais_template.json), devuelve
    un dict {cluster_id: (compiled_regex, metadata)} para poder clasificar
    nuevas líneas de log contra los templates ya minados.

    Args:
        clusters (list): Lista de clusters extraídos de Drain.
        anchor (bool): Si True, el regex generado se ancla al inicio y fin
            de la cadena (equivalente a fullmatch). Si False, se permite
            match parcial (search).
    
    Returns:
        dict: Mapa de cluster_id a regex compilado y metadatos
    """
    result = {}
    for cluster in clusters:
        cluster_id = cluster['cluster_id']
        template = cluster['template']
        try:
            compiled = template_to_regex(template, anchor=anchor)
            result[cluster_id] = {
                'regex': compiled,
                'template': template,
                'event_type': cluster.get('event_type'),
                'severity': cluster.get('severiy'),  # ojo: typo original "severiy"
            }
        except re.error as e:
            print(f"⚠️  Error compilando cluster {cluster_id}: {e}")
    return result


def classify_message(message: str, regex_map: dict):
    """
    Intenta matchear un mensaje nuevo contra los templates ya minados.
    Devuelve el cluster_id del primer match, o None si no matchea ninguno.
    """
    for cluster_id, info in regex_map.items():
        if info['regex'].match(message):
            return cluster_id
    return None


def save_regex_map(regex_map: dict, output_path: str) -> None:
    """
    Guarda el mapa de regex generado a partir de los templates de Drain
    en un JSON serializable (el objeto re.Pattern no es serializable
    directamente, así que se guarda el patrón como string junto con sus
    flags, para poder recompilarlo después con load_regex_map()).

    Args:
        regex_map (dict): Mapa de cluster_id a regex compilado y metadatos.
        output_path (str): Ruta de salida para el fichero JSON.

    Returns:
        None
    """
    serializable = {}
    for cluster_id, info in regex_map.items():
        serializable[str(cluster_id)] = {
            'pattern': info['regex'].pattern,
            'flags': info['regex'].flags,
            'template': info['template'],
            'event_type': info.get('event_type'),
            'severity': info.get('severity'),
        }

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump({'clusters': serializable}, f, ensure_ascii=False, indent=2)

    print(f"💾 Guardado: {output_path} ({len(serializable)} clusters)")


def load_regex_map(input_path: str) -> dict:
    """
    Recarga un mapa de regex previamente guardado con save_regex_map(),
    recompilando los patrones (el flag guardado incluye re.DOTALL si se
    usó al generar el regex original).

    Args:
        input_path (str): Ruta del fichero JSON previamente guardado.
    
    Returns:
        dict: Mapa de cluster_id a regex compilado y metadatos.
    """
    with open(input_path, encoding='utf-8') as f:
        data = json.load(f)

    regex_map = {}
    for cluster_id_str, info in data['clusters'].items():
        regex_map[int(cluster_id_str)] = {
            'regex': re.compile(info['pattern'], info['flags']),
            'template': info['template'],
            'event_type': info.get('event_type'),
            'severity': info.get('severity'),
        }
    return regex_map


def derive_output_path(input_path: str) -> str:
    """
    Deriva el nombre del fichero de salida a partir del de entrada,
    insertando '_regex' antes de la extensión.
    Ej: 'templates/ais_template.json' -> 'templates/ais_template_regex.json'

    Args:
        input_path (str): Ruta del fichero de entrada.

    Returns:
        str: Ruta del fichero de salida derivada.
    """
    base, ext = os.path.splitext(input_path)
    return f"{base}_regex{ext}"

def find_template_files(templates_folder: str) -> list:
    """
    Busca en templates_folder todos los ficheros 'x_template.json',
    excluyendo los que ya sean resultado de una conversión previa
    ('x_template_regex.json'), para no reprocesarlos por error.

    Args:
        templates_folder (str): Carpeta donde buscar los ficheros de templates.
    
    Returns:
        list: Lista de rutas a los ficheros 'x_template.json' encontrados.
    """
    import glob

    pattern = os.path.join(templates_folder, '*_template.json')
    all_matches = glob.glob(pattern)

    # Excluir explícitamente los que terminen en '_regex.json'
    return [p for p in all_matches if not p.endswith('_regex.json')]


def process_template_file(input_path: str) -> None:
    """
    Convierte un fichero de templates a su versión con regex compilados.

    INCREMENTAL: si ya existe un 'x_template_regex.json' previo, los
    cluster_id que ya tengan regex generada NO se recompilan ni se
    sobreescriben (se conservan tal cual, por si se ajustaron a mano o
    para no perder tiempo recompilando lo que no ha cambiado). Solo se
    generan regex para los cluster_id nuevos que no estuvieran ya.

    Args:
        input_path (str): Ruta del fichero 'x_template.json' de entrada.
    
    Returns:
        None
    """
    output_path = derive_output_path(input_path)

    with open(input_path, encoding='utf-8') as f:
        data = json.load(f)

    clusters = data.get('clusters')
    if clusters is None:
        print(f"  ❌ No se encontró la clave 'clusters' en {input_path}")
        return

    # Cargar regex_map existente (si lo hay) para no sobreescribir lo ya generado
    existing_regex_map = {}
    if os.path.exists(output_path):
        try:
            existing_regex_map = load_regex_map(output_path)
            print(f"  📎 {len(existing_regex_map)} cluster(s) ya existentes en {os.path.basename(output_path)}")
        except (json.JSONDecodeError, KeyError, re.error) as e:
            print(f"  ⚠️  No se pudo leer el regex existente ({e}), se regenerará todo")
            existing_regex_map = {}

    # Filtrar solo los clusters cuyo cluster_id todavía no tiene regex generada
    new_clusters = [c for c in clusters if c['cluster_id'] not in existing_regex_map]
    skipped = len(clusters) - len(new_clusters)

    if skipped > 0:
        print(f"  ⏭️  {skipped} cluster(s) omitidos (ya tenían regex generada)")

    if new_clusters:
        new_regex_map = templates_to_regex_map(new_clusters)
        print(f"  ✓ {len(new_regex_map)} cluster(s) nuevo(s) convertidos a regex")
    else:
        new_regex_map = {}
        print(f"  ✓ Nada nuevo que convertir")

    # Merge: existentes (sin tocar) + nuevos
    merged_regex_map = {**existing_regex_map, **new_regex_map}

    if not new_clusters and existing_regex_map:
        print(f"  ℹ️  Sin cambios, se mantiene el fichero existente")
        return

    save_regex_map(merged_regex_map, output_path)


def process_all_templates(templates_folder: str = 'templates') -> None:
    """
    Procesa todos los ficheros 'x_template.json' encontrados en
    templates_folder, generando su correspondiente
    'x_template_regex.json'.

    Args:
        templates_folder (str): Carpeta donde buscar los ficheros de templates.
    
    Returns:
        None
    """
    template_files = find_template_files(templates_folder)

    if not template_files:
        print(f"❌ No se encontraron ficheros '*_template.json' en {templates_folder}")
        return

    print(f"🔍 {len(template_files)} fichero(s) de templates detectado(s)")

    for input_path in template_files:
        print(f"\n📂 Procesando: {input_path}")
        try:
            process_template_file(input_path)
        except (json.JSONDecodeError, KeyError, OSError) as e:
            print(f"  ❌ Error procesando {input_path}: {e}")


if __name__ == '__main__':
    import sys

    templates_folder = sys.argv[1] if len(sys.argv) > 1 else 'templates'
    process_all_templates(templates_folder)