"""
s3_storage.py 

Implementación de StorageBackend para almacenamiento en S3.
"""
import json
import boto3
from botocore.exceptions import ClientError
from storage.base import StorageBackend


class S3Storage(StorageBackend):
    def __init__(self, bucket_name: str, region_name: str = "eu-south-2"):
        self.bucket = bucket_name
        self.client = boto3.client("s3", region_name=region_name)

    def list_files(self, prefix: str, extension: str = ".log", exclude_prefix: str = None) -> list:
        log_files = []
        paginator = self.client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                if not key.endswith(extension):
                    continue
                rel_path = key[len(prefix):].lstrip("/")
                if exclude_prefix and rel_path.startswith(exclude_prefix):
                    continue
                log_files.append((key, rel_path))
        return log_files

    def read_all_bytes(self, path: str) -> bytes:
        response = self.client.get_object(Bucket=self.bucket, Key=path)
        return response["Body"].read()

    def read_bytes_from_offset(self, path: str, start: int) -> bytes:
        """
        Lee desde 'start' hasta el final usando HTTP Range request.
        Si start=0, lee el archivo completo (evita error de range inválido).
        """
        if start == 0:
            return self.read_all_bytes(path)

        try:
            response = self.client.get_object(
                Bucket=self.bucket,
                Key=path,
                Range=f"bytes={start}-"
            )
            return response["Body"].read()
        except ClientError as e:
            # Si el rango pedido es igual o mayor al tamaño real, no hay nada nuevo
            if e.response["Error"]["Code"] in ("InvalidRange", "416"):
                return b""
            raise

    def get_file_size(self, path: str) -> int:
        response = self.client.head_object(Bucket=self.bucket, Key=path)
        return response["ContentLength"]

    def write_json(self, path: str, data: dict):
        body = json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")
        self.client.put_object(
            Bucket=self.bucket,
            Key=path,
            Body=body,
            ContentType="application/json"
        )

    def read_json(self, path: str) -> dict:
        response = self.client.get_object(Bucket=self.bucket, Key=path)
        return json.loads(response["Body"].read())

    def exists(self, path: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=path)
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] in ("404", "NoSuchKey"):
                return False
            raise

    def write_bytes(self, path: str, data: bytes):
        self.client.put_object(Bucket=self.bucket, Key=path, Body=data)

    def delete_file(self, path: str):
        self.client.delete_object(Bucket=self.bucket, Key=path)

    def get_file_size(self, key: str) -> int:
        """Obtiene el tamaño de un archivo en S3."""
        try:
            response = self.client.head_object(Bucket=self.bucket, Key=key)
            return response['ContentLength']
        except ClientError as e:
            print(f"Error obteniendo tamaño de {key}: {e}")
            return 0