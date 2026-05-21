"""
nodes/ingest/storage/base.py — Minimal storage adapter interface.
"""

from typing import Protocol


class StorageAdapter(Protocol):
    def exists(self, path: str) -> bool:
        """Return True if the object at *path* exists in the bucket."""
        ...

    def upload_bytes(self, path: str, data: bytes, content_type: str) -> bool:
        """
        Upload *data* to *path*.

        Returns True if uploaded, False if the object already existed (skip).
        Implementations should handle concurrent-upload races gracefully.
        """
        ...

    def download_bytes(self, path: str) -> bytes:
        """Return the full content of the object at *path*."""
        ...

    def list_objects(self, prefix: str):
        """Yield object paths (str) that start with *prefix*."""
        ...

    def delete_object(self, path: str) -> None:
        """Delete the object at *path*. Silent no-op if it does not exist."""
        ...

    def presigned_url(self, path: str, expires: int = 3600) -> str:
        """Return a time-limited URL to GET the object (for frontend display)."""
        ...
