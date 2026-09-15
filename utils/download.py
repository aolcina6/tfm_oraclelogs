import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from storage.s3_storage import S3Storage
from botocore.exceptions import ClientError

# ✅ Configuración
S3_BUCKET_NAME = "beholder-logs-testing-area-505515191272-eu-south-2-an"
S3_REGION = "eu-south-2"
S3_PREFIX = "enterprise"  # Carpeta en S3 a descargar (vacío "" para todo el bucket)
LOCAL_DESTINATION = "./downloaded_logs"  # Carpeta local de destino

def download_s3_folder(bucket: str, region: str, s3_prefix: str, local_dest: str):
    """
    Descarga recursivamente una carpeta completa de S3 a disco local.
    
    Args:
        bucket: Nombre del bucket S3
        region: Región de AWS
        s3_prefix: Prefijo/carpeta en S3 (ej: "logs", "" para todo)
        local_dest: Carpeta local de destino
    """
    print(f"🌐 Conectando a S3...")
    print(f"   Bucket: {bucket}")
    print(f"   Region: {region}")
    print(f"   Prefix: {s3_prefix or '(raíz del bucket)'}")
    print(f"   Destino: {local_dest}\n")
    
    # Crear carpeta de destino
    Path(local_dest).mkdir(parents=True, exist_ok=True)
    
    # Inicializar cliente S3
    storage = S3Storage(bucket_name=bucket, region_name=region)
    
    try:
        # Listar todos los archivos
        print(f"📋 Listando archivos en S3...\n")
        
        paginator = storage.client.get_paginator('list_objects_v2')
        
        if s3_prefix:
            pages = paginator.paginate(Bucket=bucket, Prefix=s3_prefix)
        else:
            pages = paginator.paginate(Bucket=bucket)
        
        total_files = 0
        total_size = 0
        downloaded_files = 0
        skipped_files = 0
        
        for page in pages:
            if 'Contents' not in page:
                continue
            
            for obj in page['Contents']:
                key = obj['Key']
                size = obj['Size']
                
                total_files += 1
                total_size += size
                
                # Ignorar carpetas (objetos que terminan en /)
                if key.endswith('/'):
                    continue
                
                # Calcular ruta local
                if s3_prefix:
                    relative_path = key[len(s3_prefix):].lstrip('/')
                else:
                    relative_path = key
                
                local_file = os.path.join(local_dest, relative_path)
                
                # Crear directorio si no existe
                os.makedirs(os.path.dirname(local_file), exist_ok=True)
                
                # Verificar si ya existe
                if os.path.exists(local_file):
                    local_size = os.path.getsize(local_file)
                    if local_size == size:
                        print(f"⏭️  Ya existe: {relative_path} ({format_size(size)})")
                        skipped_files += 1
                        continue
                
                # Descargar archivo
                print(f"⬇️  Descargando: {relative_path} ({format_size(size)})")
                
                try:
                    storage.client.download_file(bucket, key, local_file)
                    downloaded_files += 1
                except Exception as e:
                    print(f"   ❌ Error: {e}")
        
        # Resumen
        print(f"\n{'='*60}")
        print(f"✅ Descarga completada")
        print(f"{'='*60}")
        print(f"   Total de archivos en S3: {total_files}")
        print(f"   Archivos descargados: {downloaded_files}")
        print(f"   Archivos omitidos (ya existían): {skipped_files}")
        print(f"   Tamaño total: {format_size(total_size)}")
        print(f"   Ubicación: {os.path.abspath(local_dest)}")
        
    except ClientError as e:
        error_code = e.response['Error']['Code']
        print(f"\n❌ Error de S3: {error_code}")
        
        if error_code == 'NoSuchBucket':
            print(f"   El bucket '{bucket}' no existe")
        elif error_code == 'AccessDenied':
            print(f"   No tienes permisos para acceder al bucket '{bucket}'")
        elif error_code == 'InvalidToken':
            print(f"   Token inválido, verifica tus credenciales AWS")
        
        sys.exit(1)
    
    except Exception as e:
        print(f"\n❌ Error inesperado: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

def format_size(bytes_size: int) -> str:
    """Formatea bytes a formato legible."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_size < 1024.0:
            return f"{bytes_size:.2f} {unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.2f} PB"

if __name__ == "__main__":
    # ✅ Permitir argumentos de línea de comandos
    if len(sys.argv) > 1:
        S3_PREFIX = sys.argv[1]
    
    if len(sys.argv) > 2:
        LOCAL_DESTINATION = sys.argv[2]
    
    print(f"🚀 Descargador de S3 → Local")
    print(f"{'='*60}\n")
    
    download_s3_folder(
        bucket=S3_BUCKET_NAME,
        region=S3_REGION,
        s3_prefix=S3_PREFIX,
        local_dest=LOCAL_DESTINATION
    )