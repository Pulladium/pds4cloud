"""
nodes/ingest/storage/minio_adapter.py — MinIO adapter.

Required env vars:
  MINIO_ENDPOINT    host:port  (e.g. localhost:9000)
  MINIO_ACCESS_KEY
  MINIO_SECRET_KEY

Optional env vars:
  MINIO_BUCKET      bucket name (default: mars2020)
  MINIO_SECURE      use TLS     (default: false)
"""

import io
import os
from urllib.parse import urlsplit, urlunsplit


class MinIOAdapter:
    def __init__(self, client, bucket_name: str):
        self._client = client
        self._bucket = bucket_name

    @classmethod
    def from_env(cls) -> "MinIOAdapter":
        from minio import Minio

        endpoint    = os.environ["MINIO_ENDPOINT"]
        access_key  = os.environ["MINIO_ACCESS_KEY"]
        secret_key  = os.environ["MINIO_SECRET_KEY"]
        bucket_name = os.environ.get("MINIO_BUCKET", "mars2020")
        secure      = os.environ.get("MINIO_SECURE", "false").lower() == "true"

        client = Minio(endpoint, access_key=access_key, secret_key=secret_key, secure=secure)

        if not client.bucket_exists(bucket_name):
            client.make_bucket(bucket_name)

        return cls(client, bucket_name)

    def exists(self, path: str) -> bool:
        from minio.error import S3Error

        try:
            self._client.stat_object(self._bucket, path)
            return True
        except S3Error:
            return False

    def upload_bytes(self, path: str, data: bytes, content_type: str) -> bool:
        if self.exists(path):
            return False  # already exists, skip

        self._client.put_object(
            self._bucket, path,
            io.BytesIO(data), len(data),
            content_type=content_type,
        )
        return True

    def download_bytes(self, path: str) -> bytes:
        response = self._client.get_object(self._bucket, path)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()

    def list_objects(self, prefix: str):
        for obj in self._client.list_objects(self._bucket, prefix=prefix, recursive=True):
            yield obj.object_name

    def delete_object(self, path: str) -> None:
        from minio.error import S3Error
        try:
            self._client.remove_object(self._bucket, path)
        except S3Error:
            pass

    def presigned_url(self, path: str, expires: int = 3600) -> str:
        from datetime import timedelta
        signed_url = self._client.presigned_get_object(
            self._bucket, path, expires=timedelta(seconds=expires)
        )
        return self._public_url(signed_url)

    def _public_url(self, signed_url: str) -> str:
        public_base_url = os.environ.get("PUBLIC_OBJECT_BASE_URL", "").rstrip("/")
        if not public_base_url:
            return signed_url

        signed = urlsplit(signed_url)
        public = urlsplit(public_base_url)
        return urlunsplit((
            public.scheme,
            public.netloc,
            signed.path,
            signed.query,
            signed.fragment,
        ))
