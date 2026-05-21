from database import SessionLocal
from models import ProjectImage
from nodes.ingest.storage import get_storage_adapter
from nodes.qdrant.graph import index_product_bytes


def _storage_marker(path: str) -> str:
    return f"storage:{path}"


def _select_preview_path(result: dict, storage) -> str | None:
    for path in (result.get("rgb_path"), result.get("gray_path")):
        if path and storage.exists(path):
            return path
    return None


def backfill_generated_preview(project_id: str | None, lid: str, result: dict) -> dict:
    if not project_id:
        return {"status": "skipped_no_project"}

    db = SessionLocal()
    try:
        img = (
            db.query(ProjectImage)
            .filter(ProjectImage.project_id == project_id, ProjectImage.lid == lid)
            .first()
        )
        if not img:
            return {"status": "skipped_missing_project_image"}
        if img.thumb_url:
            return {"status": "skipped_has_preview"}

        photo_id = result.get("photo_id")
        sol = str(result.get("sol") or "").zfill(5)
        if not photo_id or not sol:
            return {"status": "skipped_missing_metadata"}

        storage = get_storage_adapter()
        preview_path = _select_preview_path(result, storage)
        if not preview_path:
            return {"status": "skipped_missing_preview"}

        img_bytes = storage.download_bytes(preview_path)
        thumb_url = _storage_marker(preview_path)
        index_result = index_product_bytes(
            lid,
            img_bytes,
            photo_id=photo_id,
            sol=sol,
            thumb_url=thumb_url,
        )

        img.thumb_url = thumb_url
        img.sol = sol
        db.commit()

        return {
            "status": index_result.get("status", "ok"),
            "thumb_url": thumb_url,
            "preview_path": preview_path,
            "point_id": index_result.get("point_id"),
            "error": index_result.get("error"),
        }
    finally:
        db.close()
