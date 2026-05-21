import pytest
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from database import Base, get_db
from models import Project, ProjectImage, ConversationMessage


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


def test_create_project(db):
    p = Project(user_id="u1", name="My Project")
    db.add(p)
    db.commit()
    db.refresh(p)
    assert p.id is not None
    assert p.name == "My Project"
    assert p.created_at is not None


def test_project_image_cascade_delete(db):
    p = Project(user_id="u1", name="Test")
    db.add(p)
    db.commit()
    img = ProjectImage(project_id=p.id, lid="urn:nasa:pds:mars2020_mast_z:browse::1.0", thumb_url="http://example.com/t.jpg")
    db.add(img)
    db.commit()
    db.delete(p)
    db.commit()
    assert db.query(ProjectImage).count() == 0


def test_conversation_message(db):
    p = Project(user_id="u1", name="Test")
    db.add(p)
    db.commit()
    msg = ConversationMessage(project_id=p.id, role="user", content="Hello")
    db.add(msg)
    db.commit()
    fetched = db.query(ConversationMessage).filter_by(project_id=p.id).all()
    assert len(fetched) == 1
    assert fetched[0].role == "user"


from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch


@pytest.fixture
def client(db):
    from server import app
    from database import get_db

    def override():
        yield db

    app.dependency_overrides[get_db] = override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_create_project_api(client):
    r = client.post("/api/projects", json={"name": "Apollo"}, headers={"X-User-Id": "u1"})
    assert r.status_code == 201
    data = r.json()
    assert data["name"] == "Apollo"
    assert data["status"] == "not_started"
    assert "id" in data


def test_list_projects_api(client):
    client.post("/api/projects", json={"name": "P1"}, headers={"X-User-Id": "u1"})
    client.post("/api/projects", json={"name": "P2"}, headers={"X-User-Id": "u1"})
    r = client.get("/api/projects", headers={"X-User-Id": "u1"})
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 2
    assert {p["status"] for p in data} == {"not_started"}


def test_max_3_projects(client):
    for i in range(3):
        client.post("/api/projects", json={"name": f"P{i}"}, headers={"X-User-Id": "u1"})
    r = client.post("/api/projects", json={"name": "P4"}, headers={"X-User-Id": "u1"})
    assert r.status_code == 400
    assert r.json()["detail"] == "You can't create more than 3 not published projects. Publish or delete one first."


def test_published_projects_do_not_count_against_draft_limit(db):
    from routers.projects import CreateProjectRequest, create_project

    for i in range(3):
        create_project(CreateProjectRequest(name=f"P{i}"), db, "u1")
    db.query(Project).first().published_at = datetime(2026, 5, 4)
    db.commit()

    created = create_project(CreateProjectRequest(name="P4"), db, "u1")
    assert created["name"] == "P4"


def test_published_project_status_is_reported(db):
    from routers.projects import get_project, list_projects

    p = Project(user_id="u1", name="Published", published_at=datetime(2026, 5, 4))
    db.add(p)
    db.commit()
    db.refresh(p)

    listed = list_projects(db, "u1")
    detail = get_project(p.id, db, "u1")

    assert listed[0]["status"] == "published"
    assert detail["status"] == "published"


def test_delete_project_api(client):
    r = client.post("/api/projects", json={"name": "ToDelete"}, headers={"X-User-Id": "u1"})
    pid = r.json()["id"]
    r2 = client.delete(f"/api/projects/{pid}", headers={"X-User-Id": "u1"})
    assert r2.status_code == 204
    r3 = client.get("/api/projects", headers={"X-User-Id": "u1"})
    assert r3.json() == []


def test_add_image_to_project(client):
    r = client.post("/api/projects", json={"name": "ImgTest"}, headers={"X-User-Id": "u1"})
    pid = r.json()["id"]
    with patch("routers.projects.index_product", return_value={"status": "ok", "point_id": "abc"}):
        r2 = client.post(
            f"/api/projects/{pid}/images",
            json={"lid": "urn:test:1", "thumb_url": "http://ex.com/t.jpg"},
            headers={"X-User-Id": "u1"},
        )
    assert r2.status_code == 201
    assert r2.json()["lid"] == "urn:test:1"


def test_add_image_without_preview_url_still_adds_project_image(db):
    from routers.projects import AddImageRequest, add_image

    p = Project(user_id="u1", name="NoPreview")
    db.add(p)
    db.commit()
    db.refresh(p)

    with patch("routers.projects.index_product") as index_product_mock:
        body = add_image(p.id, AddImageRequest(lid="urn:test:no-preview", thumb_url=""), db, "u1")

    assert body["lid"] == "urn:test:no-preview"
    assert body["thumb_url"] == ""
    assert body["index_warning"] == "Could not add image to vector search: no preview URL is available."
    index_product_mock.assert_not_called()


def test_add_image_accepts_missing_preview_url(db):
    from routers.projects import AddImageRequest, add_image

    p = Project(user_id="u1", name="MissingPreview")
    db.add(p)
    db.commit()
    db.refresh(p)

    with patch("routers.projects.index_product") as index_product_mock:
        body = add_image(p.id, AddImageRequest(lid="urn:test:missing-preview"), db, "u1")

    assert body["lid"] == "urn:test:missing-preview"
    assert body["thumb_url"] == ""
    assert body["index_warning"] == "Could not add image to vector search: no preview URL is available."
    index_product_mock.assert_not_called()


def test_add_image_index_failure_returns_warning_but_still_adds(db):
    from routers.projects import AddImageRequest, add_image

    p = Project(user_id="u1", name="IndexWarning")
    db.add(p)
    db.commit()
    db.refresh(p)

    with patch("routers.projects.index_product", return_value={"status": "error_thumb", "error": "bad thumbnail"}):
        body = add_image(
            p.id,
            AddImageRequest(lid="urn:test:index-warning", thumb_url="http://ex.com/t.jpg"),
            db,
            "u1",
        )

    assert body["lid"] == "urn:test:index-warning"
    assert body["index_warning"] == "Could not add image to vector search: bad thumbnail"


def test_get_project_includes_cached_analysis_metadata(db):
    from routers.projects import get_project
    from services.analysis_artifacts import reserve_analysis, mark_ready

    p = Project(user_id="u1", name="Cached")
    db.add(p)
    db.commit()
    db.refresh(p)
    lid = "urn:nasa:pds:mars2020_mastcamz_ops_calibrated:data:zrf_0045_0670943307_535ras_n0031416zcam05003_1100luj"
    img = ProjectImage(project_id=p.id, lid=lid, thumb_url="http://ex.com/t.jpg", sol="00045")
    db.add(img)
    db.commit()

    artifact = reserve_analysis(
        db,
        lid,
        "ZRF_0045_0670943307_535RAS_N0031416ZCAM05003_1100LUJ01",
        "00045",
        p.id,
        "job-1",
        "u1",
        "gpt-5.1-chat-latest",
    )
    mark_ready(db, artifact.id, analyzed_at=datetime(2026, 5, 4, 10, 55, 53))

    storage = MagicMock()

    with patch("routers.projects.get_storage_adapter", return_value=storage, create=True):
        response = get_project(p.id, db, "u1")

    image = response["images"][0]
    assert image["analysis_cache"] == {
        "status": "cached",
        "analysis_id": artifact.id,
        "analyzed_at": "2026-05-04T10:55:53",
        "result_path": artifact.result_path,
    }
    storage.list_objects.assert_not_called()


def test_project_analysis_cache_uses_analysis_artifact_metadata(db):
    from routers.projects import _analysis_cache_for_lid
    from services.analysis_artifacts import reserve_analysis, mark_ready

    artifact = reserve_analysis(db, "urn:test:lid1", "lid1", "00001", "project-1", "job-1", "user-1", "gpt-4o")
    mark_ready(db, artifact.id)

    cache = _analysis_cache_for_lid(db, "urn:test:lid1")

    assert cache["status"] == "cached"
    assert cache["analysis_id"] == artifact.id
    assert cache["result_path"] == artifact.result_path
    with patch("routers.projects.latest_cache_for_product", side_effect=AssertionError("should not query blank lid")):
        assert _analysis_cache_for_lid(db, "   ") == {
            "status": "none",
            "analysis_id": None,
            "analyzed_at": None,
            "result_path": None,
        }


def test_get_project_reports_no_analysis_cache_when_result_missing(db):
    from routers.projects import get_project

    p = Project(user_id="u1", name="Uncached")
    db.add(p)
    db.commit()
    db.refresh(p)
    img = ProjectImage(
        project_id=p.id,
        lid="urn:test:no_cache",
        thumb_url="http://ex.com/t.jpg",
        sol="00045",
    )
    db.add(img)
    db.commit()

    storage = MagicMock()
    storage.list_objects.return_value = []

    with patch("routers.projects.get_storage_adapter", return_value=storage, create=True):
        response = get_project(p.id, db, "u1")

    image = response["images"][0]
    assert response["status"] == "not_started"
    assert image["analysis_cache"] == {
        "status": "none",
        "analysis_id": None,
        "analyzed_at": None,
        "result_path": None,
    }
    storage.list_objects.assert_not_called()


def test_get_project_finds_cached_analysis_when_previewless_image_has_no_sol(db):
    from routers.projects import get_project
    from services.analysis_artifacts import reserve_analysis, mark_ready

    p = Project(user_id="u1", name="Previewless")
    db.add(p)
    db.commit()
    db.refresh(p)
    lid = "zlf_0001_0667035653_000fdr_n0010052aut_04096_0260lmj"
    img = ProjectImage(project_id=p.id, lid=lid, thumb_url="", sol="")
    db.add(img)
    db.commit()

    artifact = reserve_analysis(
        db,
        lid,
        "ZLF_0001_0667035653_000FDR_N0010052AUT_04096_0260LMJ01",
        "00001",
        p.id,
        "job-1",
        "u1",
        "gpt-4o",
    )
    mark_ready(db, artifact.id, analyzed_at=datetime(2026, 5, 5, 12, 0, 0))

    storage = MagicMock()

    with patch("routers.projects.get_storage_adapter", return_value=storage, create=True):
        response = get_project(p.id, db, "u1")

    image = response["images"][0]
    assert image["analysis_cache"] == {
        "status": "cached",
        "analysis_id": artifact.id,
        "analyzed_at": "2026-05-05T12:00:00",
        "result_path": artifact.result_path,
    }
    storage.list_objects.assert_not_called()


def test_get_project_returns_presigned_url_for_generated_preview_marker(db):
    from routers.projects import get_project

    p = Project(user_id="u1", name="GeneratedPreview")
    db.add(p)
    db.commit()
    db.refresh(p)
    img = ProjectImage(
        project_id=p.id,
        lid="urn:test:generated-preview",
        thumb_url="storage:transformed/mastcamz/sol=00001/PHOTO/rgb.jpg",
        sol="00001",
    )
    db.add(img)
    db.commit()

    storage = MagicMock()
    storage.list_objects.return_value = []
    storage.presigned_url.return_value = "http://minio/presigned-rgb"

    with patch("routers.projects.get_storage_adapter", return_value=storage, create=True):
        response = get_project(p.id, db, "u1")

    assert response["images"][0]["thumb_url"] == "http://minio/presigned-rgb"
    assert response["images"][0]["preview_source"] == "generated_transform"
    storage.presigned_url.assert_called_once_with("transformed/mastcamz/sol=00001/PHOTO/rgb.jpg")


def test_generated_previews_returns_storage_wide_transformed_preview_map(db):
    from routers.projects import generated_previews

    storage = MagicMock()
    storage.list_objects.return_value = [
        "transformed/mastcamz/sol=00001/ZLF_0001_0667035653_000FDR_N0010052AUT_04096_0260LMJ01/rgb.jpg",
        "transformed/mastcamz/sol=00001/ZLF_0001_0667035653_000FDR_N0010052AUT_04096_0260LMJ01/gray.jpg",
        "transformed/mastcamz/sol=00001/OTHER/rgb.jpg",
    ]
    storage.presigned_url.side_effect = lambda path: f"http://minio/{path}"

    with patch("routers.projects.get_storage_adapter", return_value=storage, create=True):
        response = generated_previews(
            "urn:nasa:pds:test:zlf_0001_0667035653_000fdr_n0010052aut_04096_0260lmj,urn:test:missing",
        )

    assert response == {
        "urn:nasa:pds:test:zlf_0001_0667035653_000fdr_n0010052aut_04096_0260lmj": {
            "thumb_url": (
                "http://minio/"
                "transformed/mastcamz/sol=00001/"
                "ZLF_0001_0667035653_000FDR_N0010052AUT_04096_0260LMJ01/rgb.jpg"
            ),
            "preview_source": "generated_transform",
        },
    }


def test_generated_previews_matches_photo_id_embedded_in_versioned_lid(db):
    from routers.projects import generated_previews

    photo_id = "ZLF_0004_0667301183_000RAF_N0010052AUT_04096_110085J03"
    versioned_lid = f"urn:nasa:pds:test:data:{photo_id.lower()}::1.0"

    storage = MagicMock()
    storage.list_objects.return_value = [
        f"transformed/mastcamz/sol=00004/{photo_id}/rgb.jpg",
    ]
    storage.presigned_url.side_effect = lambda path: f"http://minio/{path}"

    with patch("routers.projects.get_storage_adapter", return_value=storage, create=True):
        response = generated_previews(versioned_lid)

    assert response == {
        versioned_lid: {
            "thumb_url": f"http://minio/transformed/mastcamz/sol=00004/{photo_id}/rgb.jpg",
            "preview_source": "generated_transform",
        },
    }


def test_publish_project_rejects_large_or_too_many_images():
    from routers.projects import _validate_publish_images

    class Upload:
        def __init__(self, filename, content_type, data):
            self.filename = filename
            self.content_type = content_type
            self.file = __import__("io").BytesIO(data)

    assert _validate_publish_images([
        Upload("a.jpg", "image/jpeg", b"x"),
        Upload("b.png", "image/png", b"x"),
    ]) == [
        ("a.jpg", "image/jpeg", b"x"),
        ("b.png", "image/png", b"x"),
    ]

    with pytest.raises(Exception) as too_many:
        _validate_publish_images([
            Upload("a.jpg", "image/jpeg", b"x"),
            Upload("b.png", "image/png", b"x"),
            Upload("c.jpg", "image/jpeg", b"x"),
        ])
    assert "at most 2" in too_many.value.detail

    with pytest.raises(Exception) as too_large:
        _validate_publish_images([Upload("a.jpg", "image/jpeg", b"x" * (2 * 1024 * 1024 + 1))])
    assert "2 MB" in too_large.value.detail


def test_download_pdf_reads_public_object_url_from_storage(monkeypatch):
    from routers.projects import _download_pdf

    storage = MagicMock()
    storage._bucket = "mars2020"
    storage.download_bytes.return_value = b"%PDF-local"
    monkeypatch.setenv("PUBLIC_OBJECT_BASE_URL", "http://localhost:8088")

    data = _download_pdf(
        "http://localhost:8088/mars2020/reports/job-1/report.pdf"
        "?X-Amz-Algorithm=AWS4-HMAC-SHA256",
        storage,
    )

    assert data == b"%PDF-local"
    storage.download_bytes.assert_called_once_with("reports/job-1/report.pdf")


def test_public_project_response_includes_researched_project_images(db):
    from routers.projects import _public_project_response

    p = Project(user_id="u1", name="Published", published_at=datetime(2026, 5, 5))
    db.add(p)
    db.commit()
    db.refresh(p)
    db.add(ProjectImage(
        project_id=p.id,
        lid="urn:test:researched",
        thumb_url="storage:transformed/mastcamz/sol=00015/PHOTO/rgb.jpg",
        sol="00015",
    ))
    db.commit()
    db.refresh(p)

    storage = MagicMock()
    storage.presigned_url.side_effect = lambda path, *args, **kwargs: f"http://minio/{path}"

    response = _public_project_response(p, storage)

    assert response["research_image_urls"] == ["http://minio/transformed/mastcamz/sol=00015/PHOTO/rgb.jpg"]
    assert response["image_urls"] == ["http://minio/transformed/mastcamz/sol=00015/PHOTO/rgb.jpg"]
    assert response["research_images"][0]["lid"] == "urn:test:researched"
    assert response["research_images"][0]["sol"] == "00015"
    assert response["research_images"][0]["thumb_url"] == "http://minio/transformed/mastcamz/sol=00015/PHOTO/rgb.jpg"
    assert response["research_images"][0]["preview_source"] == "generated_transform"


def test_max_5_images(client):
    r = client.post("/api/projects", json={"name": "MaxImg"}, headers={"X-User-Id": "u1"})
    pid = r.json()["id"]
    with patch("routers.projects.index_product", return_value={"status": "ok", "point_id": "x"}):
        for i in range(5):
            client.post(
                f"/api/projects/{pid}/images",
                json={"lid": f"urn:test:{i}", "thumb_url": "http://ex.com/t.jpg"},
                headers={"X-User-Id": "u1"},
            )
        r2 = client.post(
            f"/api/projects/{pid}/images",
            json={"lid": "urn:test:99", "thumb_url": "http://ex.com/t.jpg"},
            headers={"X-User-Id": "u1"},
        )
    assert r2.status_code == 400
    assert "Maximum 5" in r2.json()["detail"]
