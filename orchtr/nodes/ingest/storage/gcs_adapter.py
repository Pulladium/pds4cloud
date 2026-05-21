"""
nodes/ingest/storage/gcs_adapter.py — Google Cloud Storage adapter.

Required env vars:
  GOOGLE_APPLICATION_CREDENTIALS  path to service-account JSON
  GCS_PROJECT_ID                  GCP project (default: proven-splicer-483117-h9)
  GCS_BUCKET                      bucket name  (default: mars2020)
"""

import os


class GCSAdapter:
    def __init__(self, bucket):
        self._bucket = bucket

    @classmethod
    def from_env(cls) -> "GCSAdapter":
        from google.cloud import storage

        project     = os.environ.get("GCS_PROJECT_ID", "proven-splicer-483117-h9")
        bucket_name = os.environ.get("GCS_BUCKET", "mars2020")
        client      = storage.Client(project=project)
        bucket      = client.bucket(bucket_name)
        return cls(bucket)

    def exists(self, path: str) -> bool:
        return self._bucket.blob(path).exists()

    def upload_bytes(self, path: str, data: bytes, content_type: str) -> bool:
        from google.api_core.exceptions import PreconditionFailed

        blob = self._bucket.blob(path)
        try:
            blob.upload_from_string(data, content_type=content_type, if_generation_match=0)
            return True   # uploaded
        except PreconditionFailed:
            return False  # already existed (concurrent upload race)

    def download_bytes(self, path: str) -> bytes:
        return self._bucket.blob(path).download_as_bytes()

    def list_objects(self, prefix: str):
        for blob in self._bucket.list_blobs(prefix=prefix):
            yield blob.name

    def delete_object(self, path: str) -> None:
        try:
            self._bucket.blob(path).delete()
        except Exception:
            pass

    def presigned_url(self, path: str, expires: int = 3600) -> str:
        from datetime import timedelta
        return self._bucket.blob(path).generate_signed_url(
            expiration=timedelta(seconds=expires), method="GET"
        )
