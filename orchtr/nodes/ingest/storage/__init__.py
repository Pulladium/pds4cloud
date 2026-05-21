"""
nodes/ingest/storage — Storage adapter factory.

Select backend via env var:
  STORAGE_BACKEND=gcs    (default)
  STORAGE_BACKEND=minio
"""

import os


def get_storage_adapter():
    """
    Return an initialised storage adapter, or raise if the backend is
    unavailable (caller should catch and fall back to demo mode).
    """
    backend = os.environ.get("STORAGE_BACKEND", "minio").lower()

    if backend == "minio":
        from .minio_adapter import MinIOAdapter
        return MinIOAdapter.from_env()

    # default: gcs
    from .gcs_adapter import GCSAdapter
    return GCSAdapter.from_env()
