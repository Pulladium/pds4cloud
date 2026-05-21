import base64
import importlib
import pytest
from unittest.mock import patch, MagicMock
import requests as _real_requests


def test_embed_text_returns_vector(monkeypatch):
    monkeypatch.setenv("CLIP_SERVICE_URL", "http://localhost:8001")

    mock_resp = MagicMock()
    mock_resp.json.return_value = {"vector": [0.1] * 512}
    mock_resp.raise_for_status = lambda: None

    with patch("nodes.qdrant.clip_client.requests.post", return_value=mock_resp) as mock_post:
        import nodes.qdrant.clip_client as cc
        result = cc.embed_text("rocky terrain")

    mock_post.assert_called_once_with(
        "http://localhost:8001/embed/text",
        json={"text": "rocky terrain"},
        timeout=30,
    )
    assert result == [0.1] * 512


def test_embed_image_encodes_bytes(monkeypatch):
    monkeypatch.setenv("CLIP_SERVICE_URL", "http://localhost:8001")

    img_bytes = b"\x89PNG fake"
    expected_b64 = base64.b64encode(img_bytes).decode()

    mock_resp = MagicMock()
    mock_resp.json.return_value = {"vector": [0.2] * 512}
    mock_resp.raise_for_status = lambda: None

    with patch("nodes.qdrant.clip_client.requests.post", return_value=mock_resp) as mock_post:
        import nodes.qdrant.clip_client as cc
        result = cc.embed_image(img_bytes)

    mock_post.assert_called_once_with(
        "http://localhost:8001/embed/image",
        json={"image_b64": expected_b64},
        timeout=30,
    )
    assert result == [0.2] * 512


def test_embed_text_raises_on_connection_error(monkeypatch):
    monkeypatch.setenv("CLIP_SERVICE_URL", "http://localhost:8001")

    with patch("nodes.qdrant.clip_client.requests.post",
               side_effect=_real_requests.ConnectionError("refused")):
        import nodes.qdrant.clip_client as cc
        with pytest.raises(RuntimeError, match="CLIP service unavailable"):
            cc.embed_text("test")
