import os
import pytest
from unittest.mock import patch, MagicMock


def test_get_qdrant_client_uses_env(monkeypatch):
    monkeypatch.setenv("QDRANT_URL", "http://fake:6333")
    monkeypatch.setenv("QDRANT_API_KEY", "fake-key")

    import nodes.qdrant.qdrant_client as qc
    qc._client = None  # reset singleton

    with patch("nodes.qdrant.qdrant_client.QdrantClient") as MockClient:
        MockClient.return_value = MagicMock()
        client = qc.get_qdrant_client()
        MockClient.assert_called_once_with(url="http://fake:6333", api_key="fake-key")
        assert client is MockClient.return_value


def test_ensure_collection_creates_if_missing(monkeypatch):
    monkeypatch.setenv("QDRANT_URL", "http://fake:6333")
    monkeypatch.setenv("QDRANT_API_KEY", "fake-key")

    import nodes.qdrant.qdrant_client as qc
    qc._client = None

    mock_client = MagicMock()
    mock_client.get_collections.return_value.collections = []

    with patch("nodes.qdrant.qdrant_client.QdrantClient", return_value=mock_client):
        qc.ensure_collection()

    mock_client.create_collection.assert_called_once()
    assert mock_client.create_payload_index.call_count == 2


def test_ensure_collection_skips_if_exists(monkeypatch):
    monkeypatch.setenv("QDRANT_URL", "http://fake:6333")
    monkeypatch.setenv("QDRANT_API_KEY", "fake-key")

    import nodes.qdrant.qdrant_client as qc
    qc._client = None

    existing = MagicMock()
    existing.name = "mars_images"
    mock_client = MagicMock()
    mock_client.get_collections.return_value.collections = [existing]

    with patch("nodes.qdrant.qdrant_client.QdrantClient", return_value=mock_client):
        qc.ensure_collection()

    mock_client.create_collection.assert_not_called()
