import pytest
from unittest.mock import patch, MagicMock


BASE_STATE = {
    "lid":       "urn:nasa:pds:mars2020_mastcamz:data:ZRF_0045_abc",
    "thumb_url": "https://example.com/thumb.jpg",
    "photo_id":  "",
    "sol":       "",
    "pds_meta":  {},
    "img_bytes": b"",
    "vector":    [],
    "status":    "",
    "error":     None,
    "point_id":  None,
    "messages":  [],
}


class TestFetchImage:

    def test_success(self):
        fake_img = b"\xff\xd8fake-jpeg"
        fake_meta = {
            "mars2020:Observation_Information.mars2020:sol_number": ["45"],
            "pds:File.pds:file_name": ["ZRF_0045_abc.IMG"],
        }

        thumb_resp = MagicMock(content=fake_img)
        thumb_resp.raise_for_status = lambda: None

        pds_resp = MagicMock()
        pds_resp.ok = True
        pds_resp.json.return_value = {"properties": fake_meta}

        with patch("nodes.qdrant.nodes.requests.get", side_effect=[thumb_resp, pds_resp]):
            from nodes.qdrant.nodes import fetch_image
            result = fetch_image(dict(BASE_STATE))

        assert result["status"] == "fetched"
        assert result["img_bytes"] == fake_img
        assert result["sol"] == "00045"
        assert result["photo_id"] == "ZRF_0045_abc"
        assert result["pds_meta"] == fake_meta

    def test_thumb_download_fails(self):
        import requests as _req
        with patch("nodes.qdrant.nodes.requests.get", side_effect=_req.HTTPError("404")):
            from nodes.qdrant.nodes import fetch_image
            result = fetch_image(dict(BASE_STATE))

        assert result["status"].startswith("error_thumb")
        assert result["error"] is not None

    def test_pds_failure_is_non_blocking(self):
        fake_img = b"\xff\xd8fake-jpeg"
        thumb_resp = MagicMock(content=fake_img)
        thumb_resp.raise_for_status = lambda: None

        import requests as _req
        with patch("nodes.qdrant.nodes.requests.get",
                   side_effect=[thumb_resp, _req.ConnectionError("no network")]):
            from nodes.qdrant.nodes import fetch_image
            result = fetch_image(dict(BASE_STATE))

        assert result["status"] == "fetched"
        assert result["pds_meta"] == {}


class TestEmbedClip:

    def test_success(self):
        state = {**BASE_STATE, "img_bytes": b"fake", "status": "fetched"}

        with patch("nodes.qdrant.nodes.embed_image", return_value=[0.1] * 512):
            from nodes.qdrant.nodes import embed_clip
            result = embed_clip(state)

        assert result["status"] == "embedded"
        assert len(result["vector"]) == 512

    def test_passes_through_error_state(self):
        state = {**BASE_STATE, "status": "error_thumb: something"}
        from nodes.qdrant.nodes import embed_clip
        result = embed_clip(state)
        assert result["status"] == "error_thumb: something"

    def test_clip_unavailable(self):
        state = {**BASE_STATE, "img_bytes": b"fake", "status": "fetched"}

        with patch("nodes.qdrant.nodes.embed_image", side_effect=RuntimeError("CLIP service unavailable")):
            from nodes.qdrant.nodes import embed_clip
            result = embed_clip(state)

        assert result["status"].startswith("error_clip")


class TestUpsertQdrant:

    def test_success(self):
        state = {
            **BASE_STATE,
            "img_bytes": b"",
            "photo_id": "ZRF_0045_abc",
            "sol": "00045",
            "vector": [0.1] * 512,
            "pds_meta": {"some_key": "some_val"},
            "status": "embedded",
        }

        mock_client = MagicMock()

        with patch("nodes.qdrant.nodes.get_qdrant_client", return_value=mock_client), \
             patch("nodes.qdrant.nodes.COLLECTION_NAME", "mars_images"):
            from nodes.qdrant.nodes import upsert_qdrant
            result = upsert_qdrant(state)

        assert result["status"] == "ok"
        assert "point_id" in result
        mock_client.upsert.assert_called_once()

    def test_passes_through_error_state(self):
        state = {**BASE_STATE, "status": "error_clip: no service", "vector": []}
        from nodes.qdrant.nodes import upsert_qdrant
        result = upsert_qdrant(state)
        assert result["status"].startswith("error")


def test_lid_to_point_id_is_deterministic():
    from nodes.qdrant.nodes import lid_to_point_id
    lid = "urn:nasa:pds:mars2020:ZRF_0045_abc"
    assert lid_to_point_id(lid) == lid_to_point_id(lid)
    assert lid_to_point_id(lid) != lid_to_point_id("different:lid")


class TestIndexProduct:

    def test_full_graph_ok(self):
        from unittest.mock import patch, MagicMock

        fake_img = b"\xff\xd8fake"
        thumb_resp = MagicMock(content=fake_img)
        thumb_resp.raise_for_status = lambda: None

        pds_resp = MagicMock()
        pds_resp.ok = True
        pds_resp.json.return_value = {
            "properties": {
                "mars2020:Observation_Information.mars2020:sol_number": ["45"],
                "pds:File.pds:file_name": ["ZRF_0045_abc.IMG"],
            }
        }

        mock_qdrant = MagicMock()

        with patch("nodes.qdrant.nodes.requests.get", side_effect=[thumb_resp, pds_resp]), \
             patch("nodes.qdrant.nodes.embed_image", return_value=[0.1] * 512), \
             patch("nodes.qdrant.nodes.get_qdrant_client", return_value=mock_qdrant):
            from nodes.qdrant.graph import index_product
            result = index_product(
                lid="urn:nasa:pds:mars2020:ZRF_0045_abc",
                thumb_url="https://example.com/thumb.jpg",
            )

        assert result["status"] == "ok"
        assert result["point_id"] is not None
        mock_qdrant.upsert.assert_called_once()


def test_index_product_bytes_uses_generated_preview_without_downloading_url():
    mock_qdrant = MagicMock()

    with patch("nodes.qdrant.nodes.embed_image", return_value=[0.2] * 512), \
         patch("nodes.qdrant.nodes.get_qdrant_client", return_value=mock_qdrant), \
         patch("nodes.qdrant.nodes.requests.get") as requests_get:
        from nodes.qdrant.graph import index_product_bytes
        result = index_product_bytes(
            lid="urn:test:generated",
            img_bytes=b"\xff\xd8generated",
            photo_id="ZLF_0001_ABC01",
            sol="00001",
            thumb_url="storage:transformed/mastcamz/sol=00001/ZLF_0001_ABC01/rgb.jpg",
        )

    assert result["status"] == "ok"
    assert result["point_id"] is not None
    requests_get.assert_not_called()
    mock_qdrant.upsert.assert_called_once()
