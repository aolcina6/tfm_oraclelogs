import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, render_template, jsonify, request
from storage.factory import get_storage_backend
from parsing.parquet_io import parquet_bytes_to_records
import json
import yaml

app = Flask(__name__)

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.yaml")

with open(CONFIG_PATH, "r", encoding="utf-8") as archivo:
    config = yaml.safe_load(archivo)


# ==================== HELPERS DE LECTURA (parquet + json) ====================

def _rel_path_of(file_info):
    """Normaliza la tupla devuelta por storage.list_files (2 o 3 elementos)."""
    if isinstance(file_info, tuple) and len(file_info) == 3:
        full_key, rel_path, _ = file_info
    else:
        full_key, rel_path = file_info
    return full_key, rel_path


def list_result_files(storage, prefix=""):
    """
    Lista todos los ficheros de resultados parseados (.parquet y .json)
    bajo 'prefix', devolviendo tuplas (full_key, rel_path, format).
    """
    files = []
    for ext, fmt in ((".parquet", "parquet"), (".json", "json")):
        for file_info in storage.list_files(prefix, ext):
            full_key, rel_path = _rel_path_of(file_info)
            files.append((full_key, rel_path, fmt))
    return files


def read_records_file(storage, full_key, fmt):
    """
    Lee un fichero de resultados (parquet o json) y devuelve
    (records, log_type, date). Unifica la forma de acceder a los
    datos independientemente del formato de origen.
    """
    if fmt == "json":
        data = storage.read_json(full_key)
        records = data.get("records", [])
        log_type = data.get("log_type", "unknown")
        date_val = data.get("date")
    else:
        raw_bytes = storage.read_all_bytes(full_key)
        records = parquet_bytes_to_records(raw_bytes)
        log_type = None
        date_val = None
    return records, log_type, date_val


def parse_result_filename(rel_path):
    """
    Extrae (date_str, log_type) del nombre de fichero de resultados
    con nomenclatura '{year}_{month}_{day}_{log_type}.<ext>' o
    'sin_fecha_{log_type}.<ext>'.

    Returns:
        (date_str, log_type): date_str en formato 'YYYY-MM-DD' o
        'sin_fecha'; log_type puede tener guiones bajos.
    """
    file_name = os.path.basename(rel_path)
    name_without_ext = os.path.splitext(file_name)[0]

    if name_without_ext.startswith("sin_fecha_"):
        return "sin_fecha", name_without_ext[len("sin_fecha_"):]

    parts = name_without_ext.split("_")
    if len(parts) < 4:
        return None, None

    year, month, day = parts[0], parts[1], parts[2]
    log_type = "_".join(parts[3:])
    if not (year.isdigit() and month.isdigit() and day.isdigit()):
        return None, None

    return f"{year}-{month}-{day}", log_type


def list_available_dates(storage):
    """
    Escanea el output_folder buscando ficheros de resultados (parquet/json)
    y devuelve las fechas disponibles en formato YYYY-MM-DD (o 'sin_fecha').
    """
    dates = set()
    all_files = list_result_files(storage, config['output_folder'])

    for full_key, rel_path, fmt in all_files:
        if os.path.basename(rel_path).startswith('_'):
            continue
        date_str, log_type = parse_result_filename(rel_path)
        if date_str:
            dates.add(date_str)

    return sorted(dates, reverse=True)


def list_log_types_for_date(storage, date_str):
    """
    Devuelve los tipos de log disponibles para una fecha dada,
    escaneando todos los ficheros de resultados (parquet/json) cuyo
    nombre corresponda a esa fecha.
    """
    result = set()
    all_files = list_result_files(storage, config['output_folder'])

    for full_key, rel_path, fmt in all_files:
        if os.path.basename(rel_path).startswith('_'):
            continue
        file_date, log_type = parse_result_filename(rel_path)
        if file_date == date_str and log_type:
            result.add(log_type)

    return sorted(result)


# def list_available_dates(storage):
#     """
#     Recorre parsed_logs/ buscando carpetas con estructura año/mes/día y devuelve una lista de fechas disponibles en formato YYYY-MM-DD.

#     Args: 
#         storage: instancia de almacenamiento (local o S3)

#     Returns:
#         List[str]: Lista de fechas disponibles en formato YYYY-MM-DD, incluyendo "sin_fecha" si existe.
#     """
#     dates = set()
#     all_json_files = storage.list_files(config['output_folder'], ".json")

#     for file_info in all_json_files:
#         if isinstance(file_info, tuple) and len(file_info) == 3:
#             _, rel_path, _ = file_info
#         else:
#             _, rel_path = file_info
            
#         parts = rel_path.replace("\\", "/").split("/")
#         if len(parts) == 4 and parts[0].isdigit():
#             year, month, day = parts[0], parts[1], parts[2]
#             dates.add(f"{year}-{month}-{day}")
#         elif len(parts) == 2 and parts[0] == "sin_fecha":
#             dates.add("sin_fecha")

#     return sorted(dates, reverse=True)


# def list_log_types_for_date(storage, date_str):
#     """
#     Devuelve los tipos de log disponibles para una fecha dada.

#     Args:
#         storage: instancia de almacenamiento (local o S3)
#         date_str: fecha en formato YYYY-MM-DD o "sin_fecha"

#     Returns:
#         List[str]: Lista de tipos de log disponibles para la fecha especificada.
#     """
#     if date_str == "sin_fecha":
#         prefix = f"{config['output_folder']}sin_fecha/"
#     else:
#         year, month, day = date_str.split("-")
#         prefix = f"{config['output_folder']}{year}/{month}/{day}/"

#     files = storage.list_files(prefix, ".json")
#     result = set()
    
#     for file_info in files:
#         if isinstance(file_info, tuple) and len(file_info) == 3:
#             _, rel_path, _ = file_info
#         else:
#             _, rel_path = file_info
            
#         result.add(os.path.splitext(os.path.basename(rel_path))[0])
    
#     return sorted(result)


def list_drain_origins(storage):
    """
    Devuelve lista de orígenes (jde, oracle, weblogic, etc.) en drain_results/.

    Args:
        storage: instancia de almacenamiento (local o S3)

    Returns:
        List[str]: Lista de orígenes disponibles en drain_results/.
    """
    try:
        # Buscar archivos *_drain_analysis.json
        analysis_files = storage.list_files(config['drain_folder'], "_drain_analysis.json")
        
        origins = set()
        for file_info in analysis_files:
            if isinstance(file_info, tuple) and len(file_info) == 3:
                _, rel_path, _ = file_info
            else:
                _, rel_path = file_info
                
            parts = rel_path.replace("\\", "/").split("/")
            if len(parts) >= 2:
                origin = parts[0]
                if not origin.startswith('_'):
                    origins.add(origin)
        
        return sorted(origins)
    except:
        return []


def get_drain_summary(storage):
    """
    Devuelve el summary de Drain.

    Args:
        storage: instancia de almacenamiento (local o S3)

    Returns:
        Dict: Contenido del archivo _summary.json de Drain, o un diccionario vacío si no existe.
    """
    try:
        summary_path = f"{config['drain_folder']}_summary.json"
        return storage.read_json(summary_path)
    except:
        return {}


def get_origin_analysis(storage, origin):
    """Devuelve análisis completo de un origen."""
    try:
        analysis_file = f"{config['drain_folder']}{origin}/{origin}_drain_analysis.json"
        
        if not storage.exists(analysis_file):
            print(f"⚠️  Archivo no encontrado: {analysis_file}")
            return None
        
        data = storage.read_json(analysis_file)
        
        if not data:
            print(f"⚠️  Archivo vacío: {analysis_file}")
            return None
        
        clusters_count = len(data.get('clusters', []))
        print(f"✓ Análisis cargado para {origin}: {clusters_count} clusters")
        return data
        
    except Exception as e:
        print(f"❌ Error cargando análisis para {origin}: {e}")
        import traceback
        traceback.print_exc()
        return None


def get_origin_patterns(storage, origin):
    """Devuelve patrones de un origen."""
    try:
        patterns_file = f"{config['drain_folder']}{origin}/{origin}_patterns.json"
        
        # ✅ Verificar si el archivo existe antes de leerlo
        if not storage.exists(patterns_file):
            print(f"⚠️  Archivo no encontrado: {patterns_file}")
            
            # ✅ DEBUG: Listar qué archivos existen en esa carpeta
            try:
                origin_folder = f"{config['drain_folder']}{origin}/"
                files_in_folder = storage.list_files(origin_folder, "")
                print(f"   Contenido de {origin_folder}:")
                for file_info in files_in_folder:
                    if isinstance(file_info, tuple) and len(file_info) == 3:
                        _, rel_path, _ = file_info
                    else:
                        _, rel_path = file_info
                    print(f"     - {rel_path}")
            except Exception as e:
                print(f"   Error listando carpeta: {e}")
            
            return {}
        
        data = storage.read_json(patterns_file)
        
        if not data:
            print(f"⚠️  Archivo vacío: {patterns_file}")
            return {}
        
        patterns_count = len(data.get('patterns', []))
        print(f"✓ Patrones cargados para {origin}: {patterns_count} patrones")
        return data
        
    except Exception as e:
        print(f"❌ Error cargando patrones para {origin}: {e}")
        import traceback
        traceback.print_exc()
        return {}

def get_origin_contexts(storage, origin):
    """Devuelve contextos de un origen."""
    try:
        contexts_file = f"{config['drain_folder']}{origin}/{origin}_contexts.json"
        
        if not storage.exists(contexts_file):
            print(f"⚠️  Archivo no encontrado: {contexts_file}")
            return {}
        
        data = storage.read_json(contexts_file)
        
        if not data:
            print(f"⚠️  Archivo vacío: {contexts_file}")
            return {}
        
        contexts_count = len(data.get('aggregated_contexts', []))
        print(f"✓ Contextos cargados para {origin}: {contexts_count} contextos")
        return data
        
    except Exception as e:
        print(f"❌ Error cargando contextos para {origin}: {e}")
        import traceback
        traceback.print_exc()
        return {}


# ==================== ROUTES ====================

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/drain")
def drain_viewer():
    """Página principal del visor Drain."""
    return render_template("drain.html")


# ==================== API: Parsed Logs ====================

@app.route("/api/dates")
def api_dates():
    storage, mode = get_storage_backend()
    dates = list_available_dates(storage)
    return jsonify({"dates": dates, "mode": mode})


@app.route("/api/log_types")
def api_log_types():
    storage, _ = get_storage_backend()
    date_str = request.args.get("date")
    if not date_str:
        return jsonify({"log_types": []})
    log_types = list_log_types_for_date(storage, date_str)
    return jsonify({"log_types": log_types})


@app.route("/api/records")
def api_records():
    """Devuelve registros con filtros opcionales e independientes."""
    storage, _ = get_storage_backend()

    date_str = request.args.get("date", "").strip()
    log_type = request.args.get("log_type", "").strip()
    search = request.args.get("search", "").strip().lower()
    page = int(request.args.get("page", 1))
    page_size = int(request.args.get("page_size", 50))

    print(f"\n{'='*60}")
    print(f"🔍 API REQUEST: /api/records")
    print(f"   date_str: '{date_str}'")
    print(f"   log_type: '{log_type}'")
    print(f"   search: '{search}'")
    print(f"{'='*60}\n")

    records = []
    source_files = []

    try:
        all_files = list_result_files(storage, config['output_folder'])

        # Filtramos según los criterios pedidos, usando el nombre del fichero
        candidates = []
        for full_key, rel_path, fmt in all_files:
            if os.path.basename(rel_path).startswith('_'):
                continue

            file_date, file_log_type = parse_result_filename(rel_path)
            if file_log_type is None:
                continue

            if date_str and file_date != date_str:
                continue
            if log_type and file_log_type != log_type:
                continue

            candidates.append((full_key, rel_path, fmt, file_date, file_log_type))

        print(f"📊 Ficheros candidatos tras filtrar: {len(candidates)}")

        for full_key, rel_path, fmt, file_date, file_log_type in candidates:
            try:
                file_records, embedded_log_type, embedded_date = read_records_file(storage, full_key, fmt)
                effective_log_type = embedded_log_type or file_log_type

                for rec in file_records:
                    rec['_source_file'] = effective_log_type

                records.extend(file_records)
                source_files.append(full_key)
                print(f"  ✓ {full_key} ({fmt}): {len(file_records)} registros")
            except Exception as e:
                print(f"  ⚠️  Error leyendo {full_key}: {e}")
                continue

        print(f"\n📊 RESUMEN PRE-FILTROS:")
        print(f"   Total registros cargados: {len(records)}")

        # ✅ Aplicar búsqueda si existe
        if search:
            original_count = len(records)
            records = [
                r for r in records
                if search in str(r.get("message", "")).lower() or
                   search in str(r.get("_source_file", "")).lower() or
                   search in str(r.get("component", "")).lower()
            ]
            print(f"   Filtrados por búsqueda: {original_count} → {len(records)}")

        # ✅ ORDENAR por timestamp normalizado (si existe)
        def get_sort_key(rec):
            ts = rec.get('timestamp_normalized') or rec.get('timestamp') or ""
            return ts if ts else ""

        records.sort(key=get_sort_key)

        print(f"\n✓ FINAL: {len(records)} registros listos para paginar\n")

    except Exception as e:
        print(f"❌ ERROR GENERAL: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

    # ✅ Paginación
    total = len(records)
    start = (page - 1) * page_size
    end = start + page_size
    page_records = records[start:end]

    return jsonify({
        "records": page_records,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": max(1, (total + page_size - 1) // page_size),
        "source_files": source_files,
        "log_type": log_type or "todos",
        "filters": {
            "date": date_str or None,
            "log_type": log_type or None,
            "search": search or None
        }
    })

@app.route("/api/summary")
def api_summary():
    """Devuelve el resumen de parsed_logs."""
    storage, _ = get_storage_backend()
    summary_path = f"{config['output_folder']}_summary.json"
    if not storage.exists(summary_path):
        return jsonify({"error": "No hay summary disponible"}), 404
    return jsonify(storage.read_json(summary_path))


# ==================== API: Drain ====================

@app.route("/api/drain/summary")
def api_drain_summary():
    """Devuelve el summary de Drain."""
    storage, _ = get_storage_backend()
    summary = get_drain_summary(storage)
    
    if not summary:
        return jsonify({"error": "No hay análisis de Drain disponible"}), 404
    
    return jsonify(summary)


@app.route("/api/drain/origins")
def api_drain_origins():
    """Devuelve lista de orígenes disponibles."""
    storage, _ = get_storage_backend()
    origins = list_drain_origins(storage)
    return jsonify({"origins": origins})


@app.route("/api/drain/origin/<origin>")
def api_drain_origin(origin):
    """Devuelve análisis completo de un origen."""
    storage, _ = get_storage_backend()
    
    print(f"\n{'='*60}")
    print(f"🔍 Solicitando análisis para origen: {origin}")
    print(f"{'='*60}")
    
    # Obtener datos
    analysis = get_origin_analysis(storage, origin)
    patterns = get_origin_patterns(storage, origin)
    contexts = get_origin_contexts(storage, origin)
    
    # ✅ DEBUG: Mostrar estado
    analysis_status = '✓' if analysis else '❌'
    patterns_status = '✓' if patterns and patterns.get('patterns') else '❌'
    contexts_status = '✓' if contexts and contexts.get('aggregated_contexts') else '❌'
    
    analysis_clusters = len(analysis.get('clusters', [])) if analysis else 0
    patterns_count = len(patterns.get('patterns', [])) if patterns else 0
    contexts_count = len(contexts.get('aggregated_contexts', [])) if contexts else 0
    
    print(f"   Analysis:  {analysis_status} ({analysis_clusters} clusters)")
    print(f"   Patterns:  {patterns_status} ({patterns_count} patrones)")
    print(f"   Contexts:  {contexts_status} ({contexts_count} contextos)")
    print(f"{'='*60}\n")
    
    # ✅ Si no hay análisis, error
    if not analysis:
        print(f"❌ No hay análisis para origen: {origin}")
        return jsonify({
            "error": f"No hay análisis para origen: {origin}",
            "origin": origin,
            "analysis_found": False,
            "patterns_found": patterns_count > 0,
            "contexts_found": contexts_count > 0
        }), 404
    
    # ✅ Si hay análisis pero sin patrones/contextos, devolver lo que hay
    return jsonify({
        "analysis": analysis,
        "patterns": patterns or {},
        "contexts": contexts or {},
        "status": {
            "has_analysis": True,
            "has_patterns": patterns_count > 0,
            "has_contexts": contexts_count > 0,
            "patterns_count": patterns_count,
            "contexts_count": contexts_count,
            "clusters_count": analysis_clusters
        }
    })

@app.route("/api/drain/origin/<origin>/patterns")
def api_drain_origin_patterns(origin):
    """Devuelve TODOS los patrones de un origen con ejemplos REALES de logs."""
    storage, _ = get_storage_backend()
    
    limit = int(request.args.get("limit", 999999))
    search = request.args.get("search", "").strip().lower()
    
    patterns = get_origin_patterns(storage, origin)
    
    # ✅ CORREGIDO: Ahora patterns siempre es un dict, validar si tiene contenido
    if not patterns or not patterns.get('patterns'):  # ✅ Cambiar de "is None" a "not patterns"
        # ✅ Debug: Listar qué archivos existen en esa carpeta
        try:
            origin_folder = f"{config['drain_folder']}{origin}/"
            origin_files = storage.list_files(origin_folder, "")
            
            available_files = []
            for file_info in origin_files:
                if isinstance(file_info, tuple) and len(file_info) == 3:
                    _, rel_path, _ = file_info
                else:
                    _, rel_path = file_info
                available_files.append(rel_path)
            
            print(f"⚠️  No hay patrones para {origin}")
            print(f"   Carpeta: {origin_folder}")
            print(f"   Archivos disponibles: {available_files}")
            
            return jsonify({
                "error": f"No hay patrones para origen: {origin}",
                "origin_folder": origin_folder,
                "available_files": available_files,
                "expected_file": f"{origin}_patterns.json"
            }), 404
        except Exception as e:
            print(f"❌ Error listando archivos: {e}")
            return jsonify({
                "error": f"No hay patrones para origen: {origin}",
                "origin_folder": f"{config['drain_folder']}{origin}/"
            }), 404
    
    pattern_list = patterns.get('patterns', [])
    
    # ✅ Filtrar por búsqueda si se proporciona
    if search:
        pattern_list = [
            p for p in pattern_list
            if search in str(p.get('template', '')).lower()
        ]
    
    # ✅ Limitado a 5 examples por patrón
    for pattern in pattern_list:
        if 'examples' in pattern:
            pattern['examples'] = pattern['examples'][:5]
    
    # Aplicar límite
    pattern_list = pattern_list[:limit]
    
    print(f"✓ Devolviendo {len(pattern_list)} patrones para {origin}")
    
    return jsonify({
        "origin": origin,
        "total_patterns": len(patterns.get('patterns', [])),
        "filtered_patterns": len(pattern_list),
        "patterns": pattern_list,
        "summary": patterns.get('summary', {})
    })

@app.route("/api/drain/origin/<origin>/contexts")
def api_drain_origin_contexts(origin):
    """Devuelve los contextos de un origen (top N)."""
    storage, _ = get_storage_backend()
    
    limit = int(request.args.get("limit", 20))
    contexts = get_origin_contexts(storage, origin)
    
    if not contexts:
        return jsonify({"error": f"No hay contextos para origen: {origin}"}), 404
    
    ctx_list = contexts.get('aggregated_contexts', [])[:limit]
    
    return jsonify({
        "origin": origin,
        "total_contexts": len(contexts.get('aggregated_contexts', [])),
        "contexts": ctx_list,
        "summary": contexts.get('summary', {})
    })


@app.route("/api/drain/origin/<origin>/cluster/<int:cluster_id>")
def api_drain_cluster(origin, cluster_id):
    """Devuelve detalle de un cluster específico."""
    storage, _ = get_storage_backend()
    
    analysis = get_origin_analysis(storage, origin)
    if not analysis:
        return jsonify({"error": f"No hay análisis para origen: {origin}"}), 404
    
    clusters = analysis.get('clusters', [])
    cluster = next((c for c in clusters if c['cluster_id'] == cluster_id), None)
    
    if not cluster:
        return jsonify({"error": f"Cluster {cluster_id} no encontrado"}), 404
    
    return jsonify({
        "origin": origin,
        "cluster": cluster
    })

@app.route("/api/variable-patterns/origin/<origin>")
def api_variable_patterns_origin(origin):
    """Devuelve patrones de variables para un origen."""
    storage, _ = get_storage_backend()
    
    limit = int(request.args.get("limit", 20))
    
    try:
        var_patterns_file = f"variable_patterns/{origin}_variable_patterns.json"
        var_patterns = storage.read_json(var_patterns_file)
    except:
        return jsonify({"error": f"No hay patrones de variables para origen: {origin}"}), 404
    
    templates = var_patterns.get('variable_templates', [])[:limit]
    
    return jsonify({
        "origin": origin,
        "total_templates": len(var_patterns.get('variable_templates', [])),
        "templates": templates,
        "statistics": var_patterns.get('statistics', {})
    })

@app.route("/api/extractor-analysis")
def api_extractor_analysis():
    """Devuelve el análisis de extractores duplicados."""
    storage, _ = get_storage_backend()
    
    try:
        analysis_file = "drain_results/_extractor_analysis.json"
        analysis = storage.read_json(analysis_file)
        return jsonify(analysis)
    except:
        return jsonify({"error": "No extractor analysis available"}), 404


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5002)