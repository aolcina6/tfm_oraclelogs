"""
delete.py 

Módulo para eliminar datos de OpenSearch de manera interactiva.
"""
import json
from datetime import datetime
from opensearchpy import OpenSearch
from opensearchpy.exceptions import NotFoundError, RequestError

# ✅ CONFIGURACIÓN DE OPENSEARCH
OPENSEARCH_HOST = 'localhost'
OPENSEARCH_PORT = 9200
OPENSEARCH_USER = 'admin'
OPENSEARCH_PASSWORD = 'admin'
INDEX_NAME = 'jde-logs'

# CONECTAR A OPENSEARCH
def connect_opensearch():
    """Conecta a OpenSearch con autenticación básica."""
    client = OpenSearch(
        hosts=[{'host': OPENSEARCH_HOST, 'port': OPENSEARCH_PORT}],
        http_auth=(OPENSEARCH_USER, OPENSEARCH_PASSWORD),
        use_ssl=False,
        verify_certs=False,
        ssl_show_warn=False
    )
    
    print(f"✓ Conectado a OpenSearch en {OPENSEARCH_HOST}:{OPENSEARCH_PORT}")
    return client


def delete_index(client, index_name):
    """
    Elimina un índice completo.
    
    Args:
        client: Cliente de OpenSearch.
        index_name: Nombre del índice a eliminar.

    Returns:
        bool: True si se eliminó correctamente, False en caso de error o cancelación.
    """
    try:
        if not client.indices.exists(index=index_name):
            print(f"⚠️  El índice '{index_name}' no existe")
            return False
        
        # Obtener estadísticas antes de eliminar
        stats = client.indices.stats(index=index_name)
        doc_count = stats['_all']['primaries']['docs']['count']
        size_bytes = stats['_all']['primaries']['store']['size_in_bytes']
        size_mb = size_bytes / (1024 * 1024)
        
        print(f"\n📊 Estadísticas del índice '{index_name}':")
        print(f"  Documentos: {doc_count:,}")
        print(f"  Tamaño: {size_mb:.2f} MB")
        
        # Confirmar eliminación
        confirm = input(f"\n⚠️  ¿Confirmar eliminación del índice '{index_name}'? (yes/no): ").strip().lower()
        
        if confirm != 'yes':
            print("❌ Operación cancelada")
            return False
        
        # Eliminar índice
        client.indices.delete(index=index_name)
        print(f"\n✅ Índice '{index_name}' eliminado correctamente")
        return True
        
    except NotFoundError:
        print(f"⚠️  El índice '{index_name}' no existe")
        return False
    except Exception as e:
        print(f"❌ Error eliminando índice: {e}")
        return False


def delete_by_query(client, index_name, query):
    """
    Elimina documentos que coincidan con una consulta.

    Args:
        client: Cliente de OpenSearch.
        index_name: Nombre del índice.
        query: Consulta en formato dict (OpenSearch DSL).

    Returns:
        bool: True si se eliminaron documentos, False en caso de error o cancelación.
    """
    try:
        if not client.indices.exists(index=index_name):
            print(f"⚠️  El índice '{index_name}' no existe")
            return False
        
        # Contar documentos que se eliminarán
        count_result = client.count(index=index_name, body={"query": query})
        doc_count = count_result['count']
        
        if doc_count == 0:
            print(f"⚠️  No se encontraron documentos que coincidan con la consulta")
            return False
        
        print(f"\n📊 Documentos a eliminar: {doc_count:,}")
        print(f"📋 Consulta: {json.dumps(query, indent=2)}")
        
        # Confirmar eliminación
        confirm = input(f"\n⚠️  ¿Confirmar eliminación de {doc_count:,} documentos? (yes/no): ").strip().lower()
        
        if confirm != 'yes':
            print("❌ Operación cancelada")
            return False
        
        # Eliminar por consulta
        result = client.delete_by_query(
            index=index_name,
            body={"query": query},
            conflicts='proceed',
            refresh=True
        )
        
        deleted = result.get('deleted', 0)
        print(f"\n✅ {deleted:,} documentos eliminados correctamente")
        
        # Mostrar estadísticas restantes
        remaining = client.count(index=index_name)['count']
        print(f"📊 Documentos restantes en '{index_name}': {remaining:,}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error eliminando documentos: {e}")
        return False


def delete_all_documents(client, index_name):
    """Elimina todos los documentos de un índice sin eliminar el índice."""
    query = {"match_all": {}}
    return delete_by_query(client, index_name, query)


def delete_by_log_type(client, index_name, log_type):
    """
    Elimina documentos de un tipo de log específico.

    Args:
        log_type: Tipo de log a eliminar (ej: 'jde', 'listener', 'bssv').

    Returns:
        bool: True si se eliminaron documentos, False en caso de error o cancelación.
    """
    query = {
        "term": {
            "log_type": log_type
        }
    }
    return delete_by_query(client, index_name, query)


def delete_by_date_range(client, index_name, start_date, end_date):
    """
    Elimina documentos en un rango de fechas.
    
    Args:
        start_date: Fecha inicial (formato: YYYY-MM-DD o ISO 8601)
        end_date: Fecha final (formato: YYYY-MM-DD o ISO 8601)

    Returns:
        bool: True si se eliminaron documentos, False en caso de error o cancelación.
    """
    query = {
        "range": {
            "@timestamp": {
                "gte": start_date,
                "lte": end_date
            }
        }
    }
    return delete_by_query(client, index_name, query)


def delete_by_source_file(client, index_name, source_file):
    """
    Elimina documentos de un archivo fuente específico.

    Args:
        source_file: Nombre del archivo fuente a eliminar (ej: 'jde.log').

    Returns:
        bool: True si se eliminaron documentos, False en caso de error o cancelación.
    """
    query = {
        "term": {
            "source_file.keyword": source_file
        }
    }
    return delete_by_query(client, index_name, query)


def list_indices(client):
    """
    Lista todos los índices existentes.
    
    Args:
        client: Cliente de OpenSearch.

    Returns:
        None
    """
    try:
        indices = client.cat.indices(format='json')
        
        if not indices:
            print("⚠️  No hay índices")
            return
        
        print(f"\n📋 Índices existentes:")
        print(f"{'='*80}")
        print(f"{'Índice':<30} {'Documentos':>15} {'Tamaño':>15} {'Estado':>10}")
        print(f"{'='*80}")
        
        for idx in indices:
            name = idx.get('index', 'N/A')
            docs = idx.get('docs.count', '0')
            size = idx.get('store.size', 'N/A')
            health = idx.get('health', 'N/A')
            
            print(f"{name:<30} {docs:>15} {size:>15} {health:>10}")
        
        print(f"{'='*80}\n")
        
    except Exception as e:
        print(f"❌ Error listando índices: {e}")


def show_index_stats(client, index_name):
    """
    Muestra estadísticas detalladas de un índice.
    
    Args:
        client: Cliente de OpenSearch.
        index_name: Nombre del índice.

    Returns:
        None
    """
    try:
        if not client.indices.exists(index=index_name):
            print(f"⚠️  El índice '{index_name}' no existe")
            return
        
        stats = client.indices.stats(index=index_name)
        doc_count = stats['_all']['primaries']['docs']['count']
        size_bytes = stats['_all']['primaries']['store']['size_in_bytes']
        size_mb = size_bytes / (1024 * 1024)
        
        # Contar por log_type
        agg_result = client.search(
            index=index_name,
            body={
                "size": 0,
                "aggs": {
                    "by_log_type": {
                        "terms": {
                            "field": "log_type",
                            "size": 100
                        }
                    }
                }
            }
        )
        
        print(f"\n📊 Estadísticas del índice '{index_name}':")
        print(f"{'='*60}")
        print(f"Total documentos: {doc_count:,}")
        print(f"Tamaño total: {size_mb:.2f} MB")
        print(f"\nDistribución por tipo de log:")
        
        for bucket in agg_result['aggregations']['by_log_type']['buckets']:
            log_type = bucket['key']
            count = bucket['doc_count']
            percentage = (count / doc_count * 100) if doc_count > 0 else 0
            print(f"  {log_type:<20} {count:>10,} ({percentage:>5.1f}%)")
        
        print(f"{'='*60}\n")
        
    except Exception as e:
        print(f"❌ Error obteniendo estadísticas: {e}")


def interactive_menu(client, index_name):
    """Menú interactivo para elegir operación de eliminación."""
    while True:
        print(f"\n{'='*60}")
        print(f"🗑️  MENÚ DE ELIMINACIÓN - Índice: {index_name}")
        print(f"{'='*60}")
        print("1. Eliminar ÍNDICE COMPLETO (destruye todo)")
        print("2. Eliminar TODOS los documentos (mantiene índice vacío)")
        print("3. Eliminar por TIPO DE LOG")
        print("4. Eliminar por RANGO DE FECHAS")
        print("5. Eliminar por ARCHIVO FUENTE")
        print("6. Ver ESTADÍSTICAS del índice")
        print("7. Listar TODOS los índices")
        print("0. Salir")
        print(f"{'='*60}")
        
        choice = input("\nSelecciona una opción: ").strip()
        
        if choice == '0':
            print("👋 Saliendo...")
            break
        
        elif choice == '1':
            delete_index(client, index_name)
            break  # Salir si se elimina el índice
        
        elif choice == '2':
            delete_all_documents(client, index_name)
        
        elif choice == '3':
            log_type = input("Ingresa el tipo de log (ej: jde, listener, bssv): ").strip()
            if log_type:
                delete_by_log_type(client, index_name, log_type)
        
        elif choice == '4':
            start = input("Fecha inicial (YYYY-MM-DD): ").strip()
            end = input("Fecha final (YYYY-MM-DD): ").strip()
            if start and end:
                delete_by_date_range(client, index_name, start, end)
        
        elif choice == '5':
            source = input("Ingresa el nombre del archivo fuente: ").strip()
            if source:
                delete_by_source_file(client, index_name, source)
        
        elif choice == '6':
            show_index_stats(client, index_name)
        
        elif choice == '7':
            list_indices(client)
        
        else:
            print("❌ Opción inválida")


def main():
    """Función principal."""
    print(f"\n{'='*60}")
    print(f"🗑️  ELIMINACIÓN DE DATOS EN OPENSEARCH")
    print(f"{'='*60}\n")
    
    # Conectar a OpenSearch
    client = connect_opensearch()
    
    # Listar índices disponibles
    list_indices(client)
    
    # ✅ Obtener lista de índices existentes
    indices_list = client.cat.indices(format='json')
    available_indices = [idx.get('index') for idx in indices_list]
    
    if not available_indices:
        print("❌ No hay índices disponibles en OpenSearch")
        print("💡 Ejecuta el script de ingesta primero para crear datos\n")
        return
    
    # Preguntar por el índice a eliminar
    print(f"📋 Índices disponibles: {', '.join(available_indices)}")
    index_to_delete = input(f"\nIngresa el nombre del índice: ").strip()
    
    if not index_to_delete:
        print("❌ Debes especificar un índice")
        return
    
    # Verificar si el índice existe
    if index_to_delete not in available_indices:
        print(f"\n❌ El índice '{index_to_delete}' no existe")
        print(f"💡 Índices disponibles: {', '.join(available_indices)}\n")
        return
    
    # Mostrar estadísticas
    show_index_stats(client, index_to_delete)
    
    # Mostrar menú interactivo
    interactive_menu(client, index_to_delete)
    
    print(f"\n✅ Operación completada\n")


if __name__ == "__main__":
    main()