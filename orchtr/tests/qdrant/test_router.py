import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient


@pytest.fixture()
def client():
    with patch("nodes.qdrant.qdrant_client.QdrantClient"), \
         patch("nodes.qdrant.clip_client.requests"):
        from server import app
        return TestClient(app)


def test_add_indexes_new_product(client):
    mock_qdrant = MagicMock()
    mock_qdrant.retrieve.return_value = []

    with patch("routers.qdrant.get_qdrant_client", return_value=mock_qdrant), \
         patch("routers.qdrant.ensure_collection"), \
         patch("routers.qdrant.index_product", return_value={
             "status": "ok", "point_id": "abc-123"
         }):
        resp = client.post("/api/qdrant/add", json={
            "lid": "urn:nasa:pds:test",
            "thumb_url": "https://example.com/t.jpg",
        })

    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "point_id": "abc-123"}


def test_add_returns_already_indexed_without_force(client):
    mock_qdrant = MagicMock()
    mock_qdrant.retrieve.return_value = [MagicMock()]

    with patch("routers.qdrant.get_qdrant_client", return_value=mock_qdrant), \
         patch("routers.qdrant.ensure_collection"):
        resp = client.post("/api/qdrant/add", json={
            "lid": "urn:nasa:pds:test",
            "thumb_url": "https://example.com/t.jpg",
            "force": False,
        })

    assert resp.status_code == 200
    assert resp.json()["status"] == "already_indexed"


def test_add_with_force_overwrites(client):
    mock_qdrant = MagicMock()

    with patch("routers.qdrant.get_qdrant_client", return_value=mock_qdrant), \
         patch("routers.qdrant.ensure_collection"), \
         patch("routers.qdrant.index_product", return_value={
             "status": "ok", "point_id": "abc-123"
         }):
        resp = client.post("/api/qdrant/add", json={
            "lid": "urn:nasa:pds:test",
            "thumb_url": "https://example.com/t.jpg",
            "force": True,
        })

    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
    mock_qdrant.retrieve.assert_not_called()


def test_search_by_text_returns_results(client):
    mock_hit = MagicMock()
    mock_hit.score = 0.95
    mock_hit.payload = {
        "lid": "urn:nasa:pds:test", "photo_id": "ZRF_0045",
        "sol": "00045", "thumb_url": "https://example.com/t.jpg",
    }

    mock_qdrant = MagicMock()
    mock_qdrant.search.return_value = [mock_hit]

    with patch("routers.qdrant.ensure_collection"), \
         patch("routers.qdrant.get_qdrant_client", return_value=mock_qdrant), \
         patch("routers.qdrant.embed_text", return_value=[0.1] * 512):
        resp = client.post("/api/qdrant/search", json={"query_text": "rocky terrain"})

    assert resp.status_code == 200
    results = resp.json()
    assert len(results) == 1
    assert results[0]["score"] == 0.95
    assert results[0]["lid"] == "urn:nasa:pds:test"


def test_search_resolves_generated_preview_storage_marker():
    from routers.qdrant import SearchRequest, search_qdrant

    mock_hit = MagicMock()
    mock_hit.score = 0.9
    mock_hit.payload = {
        "lid": "urn:test:generated",
        "photo_id": "PHOTO",
        "sol": "00001",
        "thumb_url": "storage:transformed/mastcamz/sol=00001/PHOTO/rgb.jpg",
    }

    mock_qdrant = MagicMock()
    mock_qdrant.query_points.return_value = MagicMock(points=[mock_hit])
    storage = MagicMock()
    storage.presigned_url.return_value = "http://minio/generated-preview"

    with patch("routers.qdrant.ensure_collection"), \
         patch("routers.qdrant.get_qdrant_client", return_value=mock_qdrant), \
         patch("routers.qdrant.embed_text", return_value=[0.1] * 512), \
         patch("routers.qdrant.get_storage_adapter", return_value=storage):
        result = search_qdrant(SearchRequest(query_text="rock", limit=1))

    assert result[0]["thumb_url"] == "http://minio/generated-preview"
    assert result[0]["preview_source"] == "generated_transform"
    storage.presigned_url.assert_called_once_with("transformed/mastcamz/sol=00001/PHOTO/rgb.jpg")


def test_search_requires_exactly_one_mode(client):
    with patch("routers.qdrant.ensure_collection"):
        resp = client.post("/api/qdrant/search", json={
            "query_text": "terrain",
            "ref_lid": "urn:nasa:pds:test",
        })
    assert resp.status_code == 400


def test_search_ref_lid_not_indexed_returns_404(client):
    mock_qdrant = MagicMock()
    mock_qdrant.retrieve.return_value = []

    with patch("routers.qdrant.ensure_collection"), \
         patch("routers.qdrant.get_qdrant_client", return_value=mock_qdrant):
        resp = client.post("/api/qdrant/search", json={"ref_lid": "urn:nasa:pds:missing"})

    assert resp.status_code == 404


def test_clip_unavailable_returns_503(client):
    with patch("routers.qdrant.ensure_collection"), \
         patch("routers.qdrant.embed_text", side_effect=RuntimeError("CLIP service unavailable")):
        resp = client.post("/api/qdrant/search", json={"query_text": "test"})

    assert resp.status_code == 503
