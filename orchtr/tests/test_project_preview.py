from unittest.mock import MagicMock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base
from models import Project, ProjectImage


def _db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    return Session()


def test_backfill_generated_preview_indexes_preview_and_updates_previewless_project_image():
    db = _db()
    p = Project(user_id="u1", name="NoPreview")
    db.add(p)
    db.commit()
    project_id = p.id
    img = ProjectImage(project_id=p.id, lid="urn:test:no-preview", thumb_url="", sol="")
    db.add(img)
    db.commit()

    storage = MagicMock()
    storage.exists.side_effect = lambda path: path.endswith("/rgb.jpg")
    storage.download_bytes.return_value = b"generated-jpeg"

    result = {
        "status": "analyze_ok",
        "photo_id": "ZLF_0001_ABC01",
        "sol": "00001",
        "rgb_path": "transformed/mastcamz/sol=00001/ZLF_0001_ABC01/rgb.jpg",
        "gray_path": "transformed/mastcamz/sol=00001/ZLF_0001_ABC01/gray.jpg",
    }

    with (
        patch("services.project_preview.SessionLocal", return_value=db),
        patch("services.project_preview.get_storage_adapter", return_value=storage),
        patch("services.project_preview.index_product_bytes", return_value={"status": "ok", "point_id": "p1"}) as index,
    ):
        from services.project_preview import backfill_generated_preview
        response = backfill_generated_preview(project_id, "urn:test:no-preview", result)

    img = db.query(ProjectImage).filter_by(project_id=project_id, lid="urn:test:no-preview").first()
    assert response["status"] == "ok"
    assert response["thumb_url"] == "storage:transformed/mastcamz/sol=00001/ZLF_0001_ABC01/rgb.jpg"
    assert img.thumb_url == "storage:transformed/mastcamz/sol=00001/ZLF_0001_ABC01/rgb.jpg"
    assert img.sol == "00001"
    index.assert_called_once_with(
        "urn:test:no-preview",
        b"generated-jpeg",
        photo_id="ZLF_0001_ABC01",
        sol="00001",
        thumb_url="storage:transformed/mastcamz/sol=00001/ZLF_0001_ABC01/rgb.jpg",
    )


def test_backfill_generated_preview_skips_images_that_already_have_preview_url():
    db = _db()
    p = Project(user_id="u1", name="HasPreview")
    db.add(p)
    db.commit()
    img = ProjectImage(project_id=p.id, lid="urn:test:has-preview", thumb_url="https://example.com/t.jpg", sol="00001")
    db.add(img)
    db.commit()

    with (
        patch("services.project_preview.SessionLocal", return_value=db),
        patch("services.project_preview.get_storage_adapter") as get_storage,
        patch("services.project_preview.index_product_bytes") as index,
    ):
        from services.project_preview import backfill_generated_preview
        response = backfill_generated_preview(p.id, "urn:test:has-preview", {"photo_id": "P", "sol": "00001"})

    assert response["status"] == "skipped_has_preview"
    get_storage.assert_not_called()
    index.assert_not_called()
