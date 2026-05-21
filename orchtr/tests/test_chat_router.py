import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from unittest.mock import patch
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from database import Base, get_db
from models import Project


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def client_with_project(db):
    from server import app

    def override():
        yield db

    app.dependency_overrides[get_db] = override
    # Create a project directly in DB
    p = Project(user_id="u1", name="ChatTest")
    db.add(p)
    db.commit()
    db.refresh(p)
    with TestClient(app) as c:
        yield c, p.id
    app.dependency_overrides.clear()


def test_get_empty_history(client_with_project):
    client, pid = client_with_project
    r = client.get(f"/api/projects/{pid}/chat/history", headers={"X-User-Id": "u1"})
    assert r.status_code == 200
    assert r.json() == []


def test_send_message_and_get_history(client_with_project):
    client, pid = client_with_project
    with patch("routers.chat.run_chat", return_value=("Hello from AI", [])):
        r = client.post(
            f"/api/projects/{pid}/chat/message",
            json={"content": "What do you see?"},
            headers={"X-User-Id": "u1"},
        )
    assert r.status_code == 200
    assert r.json()["content"] == "Hello from AI"
    assert r.json()["role"] == "assistant"
    assert "image_results" in r.json()

    history = client.get(f"/api/projects/{pid}/chat/history", headers={"X-User-Id": "u1"}).json()
    assert len(history) == 2
    assert history[0]["role"] == "user"
    assert history[0]["content"] == "What do you see?"
    assert "image_results" in history[0]
    assert history[1]["role"] == "assistant"
    assert history[1]["content"] == "Hello from AI"
    assert "image_results" in history[1]


def test_clear_history(client_with_project):
    client, pid = client_with_project
    with patch("routers.chat.run_chat", return_value=("AI reply", [])):
        client.post(
            f"/api/projects/{pid}/chat/message",
            json={"content": "Hi"},
            headers={"X-User-Id": "u1"},
        )
    r = client.delete(f"/api/projects/{pid}/chat/history", headers={"X-User-Id": "u1"})
    assert r.status_code == 204
    history = client.get(f"/api/projects/{pid}/chat/history", headers={"X-User-Id": "u1"}).json()
    assert history == []


def test_chat_404_for_unknown_project(client_with_project):
    client, _ = client_with_project
    r = client.get("/api/projects/nonexistent/chat/history", headers={"X-User-Id": "u1"})
    assert r.status_code == 404


def test_send_message_with_image_results(client_with_project):
    client, pid = client_with_project
    mock_images = [{"lid": "urn:test:1", "photo_id": "zl0_001", "sol": "045", "thumb_url": "http://ex.com/t.jpg", "score": 0.92}]
    with patch("routers.chat.run_chat", return_value=("Here are similar images.", mock_images)):
        r = client.post(f"/api/projects/{pid}/chat/message", json={"content": "find rocky terrain"}, headers={"X-User-Id": "u1"})
    assert r.status_code == 200
    assert r.json()["image_results"] == mock_images

    history = client.get(f"/api/projects/{pid}/chat/history", headers={"X-User-Id": "u1"}).json()
    assistant_msg = next(m for m in history if m["role"] == "assistant")
    assert assistant_msg["image_results"] == mock_images
