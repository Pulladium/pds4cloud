from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from server import app
from routers.models import router as models_router
app.include_router(models_router)


@patch("routers.models.OpenAI")
def test_list_models_filters_and_sorts_gpt_models(mock_cls):
    mock_client = MagicMock()
    mock_cls.return_value = mock_client
    mock_client.models.list.return_value = MagicMock(data=[
        MagicMock(id="gpt-4o"),
        MagicMock(id="gpt-4-turbo"),
        MagicMock(id="text-davinci-003"),
        MagicMock(id="gpt-4o-mini"),
        MagicMock(id="dall-e-3"),
    ])

    with TestClient(app) as client:
        r = client.get("/api/models")

    assert r.status_code == 200
    data = r.json()
    assert data == ["gpt-4-turbo", "gpt-4o", "gpt-4o-mini"]
    assert "text-davinci-003" not in data
    assert "dall-e-3" not in data


@patch("routers.models.OpenAI")
def test_list_models_returns_503_on_openai_failure(mock_cls):
    mock_cls.side_effect = Exception("network error")

    with TestClient(app) as client:
        r = client.get("/api/models")

    assert r.status_code == 503
    assert "OpenAI unavailable" in r.json()["detail"]
