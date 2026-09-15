"""
ingest.py 

Módulo para ingestar logs parseados en OpenSearch. 
Permite tanto ingesta completa (recreando el índice) 
como ingesta incremental (solo los parquet generados en la ejecución actual de parsing).
"""
import hashlib
import os
import sys
from datetime import datetime

from opensearchpy import OpenSearch, helpers
from opensearchpy.exceptions import RequestError

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from storage.factory import get_storage_backend
from parsing.parquet_io import parquet_bytes_to_records

# CONFIGURACIÓN DE OPENSEARCH
OPENSEARCH_HOST = 'localhost'
OPENSEARCH_PORT = 9200
OPENSEARCH_USER = 'admin'
OPENSEARCH_PASSWORD = 'admin'
INDEX_NAME = 'jde-logs'

# CARPETA DE LOGS PARSEADOS
PARSED_LOGS_FOLDER = 'parsed_logs'

# Mapping usado tanto para creación completa como incremental
INDEX_MAPPING = {
    "settings": {
        "number_of_shards": 1,
        "number_of_replicas": 0,
        "index": {
            "refresh_interval": "5s"
        }
    },
    "mappings": {
        "properties": {
            "@timestamp": {"type": "date"},
            "timestamp": {"type": "keyword"},
            "log_type": {"type": "keyword"},
            "file": {"type": "keyword"},
            "source_file": {"type": "keyword"},
            "pattern": {"type": "keyword"},
            "level": {"type": "keyword"},
            "user": {"type": "keyword"},
            "component": {"type": "keyword"},
            "message": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
            "pid": {"type": "keyword"},
            "event_type": {"type": "keyword"},
            "severity": {"type": "keyword"},
            "extracted": {"type": "object"},
            "raw_line": {"type": "text"}
        }
    }
}


# CONECTAR A OPENSEARCH
def connect_opensearch():
    """Conecta a OpenSearch con autenticación básica."""
    client = OpenSearch(
        hosts=[{'host': OPENSEARCH_HOST, 'port': OPENSEARCH_PORT}],
        http_auth=(OPENSEARCH_USER, OPENSEARCH_PASSWORD),
        use_ssl=False,
        verify_certs=False,
        ssl_show_warn=False,
        timeout=60,                  # ✅ Aumentar timeout por request (antes 10s por defecto)
        max_retries=3,                # ✅ Reintentar automáticamente
        retry_on_timeout=True,        # ✅ Reintentar específicamente en timeouts
        retry_on_status={502, 503, 504}
    )

    print(f"✓ Conectado a OpenSearch en {OPENSEARCH_HOST}:{OPENSEARCH_PORT}")
    return client


# CREAR ÍNDICE (recreándolo si ya existe)
def create_index(client, index_name):
    """
    Crea el índice con un mapping optimizado, BORRÁNDOLO PRIMERO si ya
    existe. Pensado para reingesta manual completa (main()). No usar
    en el flujo automático tras cada ejecución de parsing, porque
    perderías el histórico ya indexado (usar ensure_index() en su lugar).

    Args:
        client: instancia de OpenSearch.
        index_name (str): nombre del índice a crear.

    Returns:
        None
    """
    try:
        if client.indices.exists(index=index_name):
            print(f"⚠️  El índice '{index_name}' ya existe. Se eliminará.")
            client.indices.delete(index=index_name)

        client.indices.create(index=index_name, body=INDEX_MAPPING)
        print(f"✓ Índice '{index_name}' creado con éxito")

    except RequestError as e:
        print(f"❌ Error creando índice: {e}")
        raise


# CREAR ÍNDICE SOLO SI NO EXISTE — usado en el flujo automático/incremental
def ensure_index(client, index_name):
    """
    Crea el índice SOLO si no existe. A diferencia de create_index(),
    no borra el índice si ya existe, para no perder histórico al
    llamarse automáticamente tras cada ejecución de parsing.

    Args:
        client: instancia de OpenSearch.
        index_name (str): nombre del índice a crear.

    Returns:
        None
    """
    if client.indices.exists(index=index_name):
        print(f"✓ Índice '{index_name}' ya existe, se reutiliza")
        return

    try:
        client.indices.create(index=index_name, body=INDEX_MAPPING)
        print(f"✓ Índice '{index_name}' creado con éxito")
    except RequestError as e:
        print(f"❌ Error creando índice: {e}")
        raise


# NORMALIZAR TIMESTAMP A ISO 8601
def normalize_timestamp(timestamp_str):
    """
    Convierte timestamp a formato ISO 8601 para OpenSearch.
    
    Args:
        timestamp_str (str): Timestamp en formato "dd/mm/yy hh:mm:ss.ms".

    Returns:
        str: Timestamp en formato ISO 8601, o el timestamp actual si
             no se puede parsear.
    """
    if not timestamp_str:
        return datetime.now().isoformat()

    try:
        # Formato: "dd/mm/yy hh:mm:ss.ms"
        # Ejemplo: "23/12/24 11:44:26.000"
        dt = datetime.strptime(timestamp_str, "%d/%m/%y %H:%M:%S.%f")
        return dt.isoformat()
    except Exception as e:
        print(f"⚠️  Error parseando timestamp '{timestamp_str}': {e}")
        return datetime.now().isoformat()


# PREPARAR DOCUMENTO PARA OPENSEARCH
def prepare_document(record):
    """Prepara un registro para ser indexado en OpenSearch."""
    doc = {
        "@timestamp": normalize_timestamp(record.get("timestamp")),
        "timestamp": record.get("timestamp"),
        "log_type": record.get("log_type"),
        "file": record.get("file"),
        "source_file": record.get("source_file"),
        "pattern": record.get("pattern"),
        "level": record.get("level"),
        "user": record.get("user"),
        "component": record.get("component"),
        "message": record.get("message"),
        "pid": record.get("pid"),
        "event_type": record.get("event_type"),
        "severity": record.get("severity"),
        "extracted": record.get("extracted", {}),
        "raw_line": record.get("raw_line")
    }

    # Limpiar valores None
    return {k: v for k, v in doc.items() if v is not None}


def _make_doc_id(record):
    """
    Genera un _id determinista a partir de campos estables del registro,
    para que reingestar el mismo dato sea idempotente (upsert) en vez
    de crear duplicados en el índice.
    """
    key = "|".join(str(record.get(k, "")) for k in (
        "source_file", "timestamp", "raw_line"
    ))
    return hashlib.sha256(key.encode("utf-8", errors="replace")).hexdigest()


# LEER TODOS LOS ARCHIVOS PARQUET DE UNA CARPETA
def read_parsed_logs(storage, folder):
    """
    Lee todos los ficheros .parquet de la carpeta (vía storage backend),
    excluyendo los ficheros sidecar '_sources.json' asociados a cada
    parquet (ver derive_parquet_path() en parquet_io.py).

    Args:
        storage: backend de almacenamiento (local o S3).
        folder (str): carpeta donde buscar ficheros .parquet.
    
    Returns:
        List[dict]: lista de registros leídos de todos los parquet.
    """
    all_records = []

    parquet_files = storage.list_files(prefix=folder, extension=".parquet")

    if not parquet_files:
        print(f"❌ No se encontraron ficheros .parquet en '{folder}/'")
        return all_records

    for file_path, rel_path in sorted(parquet_files):
        try:
            raw_bytes = storage.read_all_bytes(file_path)
            records = parquet_bytes_to_records(raw_bytes)

            if records:
                print(f"✓ Cargando {len(records)} registros desde {rel_path}")
                all_records.extend(records)

        except Exception as e:
            print(f"❌ Error leyendo {rel_path}: {e}")

    return all_records


# LEER SOLO LOS PARQUET INDICADOS (ingesta incremental)
def read_parsed_logs_by_paths(storage, folder, rel_paths):
    """
    Igual que read_parsed_logs(), pero solo lee los parquet cuyos
    rel_path (relativos a 'folder') estén en la lista indicada. Útil
    para ingestar solo lo generado en la ejecución actual de parsing,
    sin reingestar todo el histórico de 'parsed_logs/'.

    Args:
        storage: backend de almacenamiento (local o S3).
        folder (str): carpeta donde buscar ficheros .parquet.
        rel_paths (List[str]): rutas relativas de los parquet a leer.

    Returns:
        List[dict]: lista de registros leídos de los parquet indicados.
    """
    all_records = []

    if not rel_paths:
        print("⚠️  No se indicaron rel_paths, no se ingestará nada")
        return all_records

    parquet_files = storage.list_files(prefix=folder, extension=".parquet")
    rel_paths_set = set(rel_paths)
    matched = [(fp, rp) for fp, rp in parquet_files if rp in rel_paths_set]

    if not matched:
        print(f"⚠️  Ninguno de los {len(rel_paths)} rel_paths indicados "
              f"coincide con parquets existentes en '{folder}/'")
        return all_records

    for file_path, rel_path in sorted(matched):
        try:
            raw_bytes = storage.read_all_bytes(file_path)
            records = parquet_bytes_to_records(raw_bytes)
            if records:
                print(f"✓ Cargando {len(records)} registros desde {rel_path}")
                all_records.extend(records)
        except Exception as e:
            print(f"❌ Error leyendo {rel_path}: {e}")

    return all_records


# INGESTAR EN BULK (con _id determinista => idempotente)
def bulk_ingest(client, index_name, records, batch_size=500):
    """
    Ingesta registros en lotes usando bulk API. Cada documento usa
    un _id determinista (ver _make_doc_id) para que reingestar el
    mismo dato sea un upsert en vez de crear duplicados.

    Args:
        client: instancia de OpenSearch.
        index_name (str): nombre del índice donde ingestar.
        records (List[dict]): lista de registros a ingestar.
        batch_size (int): tamaño de lote para bulk API.

    Returns:
        int: número total de documentos ingestados correctamente.
    """
    total_ingested = 0

    def generate_actions():
        for record in records:
            doc = prepare_document(record)
            yield {
                "_index": index_name,
                "_id": _make_doc_id(record),
                "_source": doc
            }

    try:
        success, failed = helpers.bulk(
            client,
            generate_actions(),
            chunk_size=batch_size,
            request_timeout=30,
            raise_on_error=False
        )

        total_ingested = success

        if failed:
            print(f"⚠️  {len(failed)} documentos fallaron")

        print(f"✓ {total_ingested} documentos ingestados correctamente")

    except Exception as e:
        print(f"❌ Error en bulk ingest: {e}")
        raise

    return total_ingested


# FUNCIÓN DE ENTRADA PARA EL FLUJO AUTOMÁTICO (llamada desde parsing/init.py)
def ingest_execution_to_opensearch(storage, output_folder, rel_paths, index_name=None):
    """
    Ingesta SOLO los parquet correspondientes a 'rel_paths' (los
    procesados con éxito en la ejecución actual de parsing), evitando
    reingestar todo el histórico. No borra el índice si ya existe.

    Args:
        storage: backend de storage (local o S3).
        output_folder (str): carpeta donde están los parquet ('parsed_logs' por defecto).
        rel_paths (List[str]): rutas relativas de los parquet a ingestar.
        index_name (str, opcional): nombre del índice. Si es None, usa INDEX_NAME.

    Returns:
        dict con estadísticas: {"records_found", "ingested", "index", "total_in_index"}
    """
    index_name = index_name or INDEX_NAME

    client = connect_opensearch()
    ensure_index(client, index_name)

    records = read_parsed_logs_by_paths(storage, output_folder, rel_paths)
    if not records:
        return {"records_found": 0, "ingested": 0, "index": index_name}

    total = bulk_ingest(client, index_name, records)

    client.indices.refresh(index=index_name)
    count = client.count(index=index_name)['count']

    return {
        "records_found": len(records),
        "ingested": total,
        "index": index_name,
        "total_in_index": count,
    }


def main():
    """
    Ejecución manual/standalone: reingesta TODO el histórico de
    PARSED_LOGS_FOLDER, recreando el índice desde cero. Para la
    ingesta incremental automática usar ingest_execution_to_opensearch().
    """
    print(f"\n{'='*60}")
    print(f"📊 INGESTA DE LOGS A OPENSEARCH (manual, histórico completo)")
    print(f"{'='*60}\n")

    storage, mode = get_storage_backend()
    print(f"🌐 Modo de storage: {mode}")

    client = connect_opensearch()
    create_index(client, INDEX_NAME)

    print(f"\n📂 Leyendo logs desde: {PARSED_LOGS_FOLDER}")
    records = read_parsed_logs(storage, PARSED_LOGS_FOLDER)

    if not records:
        print("❌ No se encontraron registros para ingestar")
        return

    print(f"✓ Total de registros encontrados: {len(records)}")

    print(f"\n📤 Ingesta en progreso...")
    total = bulk_ingest(client, INDEX_NAME, records)

    client.indices.refresh(index=INDEX_NAME)
    count = client.count(index=INDEX_NAME)['count']

    print(f"\n{'='*60}")
    print(f"✅ INGESTA COMPLETADA")
    print(f"{'='*60}")
    print(f"  Total procesado: {len(records)}")
    print(f"  Total ingestado: {total}")
    print(f"  En índice '{INDEX_NAME}': {count} documentos")
    print(f"{'='*60}\n")

    print("🔍 Ejemplo de consulta:")
    result = client.search(
        index=INDEX_NAME,
        body={
            "query": {"match_all": {}},
            "size": 5,
            "sort": [{"@timestamp": {"order": "desc"}}]
        }
    )

    print(f"\n📋 Últimos 5 logs:")
    for hit in result['hits']['hits']:
        source = hit['_source']
        print(f"  - [{source.get('log_type')}] {source.get('timestamp')} | {source.get('message', '')[:80]}")


if __name__ == "__main__":
    main()