import json
import os
from datetime import datetime
from urllib.parse import unquote, urlparse

import requests
from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models import Project, ProjectImage
from nodes.ingest.storage import get_storage_adapter
from nodes.qdrant.graph import index_product
from services.analysis_artifacts import latest_cache_for_product

router = APIRouter(prefix="/api/projects", tags=["projects"])

_MAX_PROJECTS = 3
_MAX_IMAGES = 5
_DEFAULT_PROJECT_STATUS = "not_started"
_PUBLISHED_PROJECT_STATUS = "published"
_MAX_PUBLISH_IMAGES = 2
_MAX_PUBLISH_IMAGE_BYTES = 2 * 1024 * 1024
_PUBLISH_IMAGE_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
}


class CreateProjectRequest(BaseModel):
    name: str


class AddImageRequest(BaseModel):
    lid: str
    thumb_url: str = ""


def _user_id(x_user_id: str = Header(default="anonymous")) -> str:
    return x_user_id


def _get_project_or_404(project_id: str, user_id: str, db: Session) -> Project:
    p = db.query(Project).filter(Project.id == project_id, Project.user_id == user_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    return p


def _project_status(project: Project) -> str:
    if project.published_at is not None:
        return _PUBLISHED_PROJECT_STATUS
    return _DEFAULT_PROJECT_STATUS


def _empty_analysis_cache() -> dict:
    return {
        "status": "none",
        "analysis_id": None,
        "analyzed_at": None,
        "result_path": None,
    }


def _display_thumb_url(raw_url: str, storage) -> str:
    marker = "storage:"
    if raw_url.startswith(marker):
        return storage.presigned_url(raw_url[len(marker):])
    return raw_url


def _preview_source(raw_url: str) -> str:
    return "generated_transform" if raw_url.startswith("storage:") else "external"


def _lid_tail(lid: str) -> str:
    return (lid.rsplit(":", 1)[-1] or "").lower()


def _photo_id_from_preview_path(path: str) -> str:
    parts = path.split("/")
    return parts[-2].lower() if len(parts) >= 2 else ""


def _preview_path_matches_request(path: str, requested: str) -> bool:
    photo_id = _photo_id_from_preview_path(path)
    requested_key = requested.lower()
    requested_tail = _lid_tail(requested)
    return (
        bool(photo_id)
        and (
            photo_id.startswith(requested_tail)
            or photo_id in requested_key
        )
    )


def _analysis_cache_for_lid(db: Session, lid: str) -> dict:
    if not lid or not lid.strip():
        return _empty_analysis_cache()
    return latest_cache_for_product(db, product_lid=lid)


def _public_project_response(project: Project, storage) -> dict:
    image_paths = json.loads(project.published_image_paths or "[]")
    research_images = [
        {
            "id": img.id,
            "lid": img.lid,
            "thumb_url": _display_thumb_url(img.thumb_url, storage),
            "preview_source": _preview_source(img.thumb_url),
            "sol": img.sol or "",
            "added_at": img.added_at.isoformat(),
        }
        for img in project.images
        if img.thumb_url
    ]
    research_image_urls = [img["thumb_url"] for img in research_images]
    published_image_urls = [storage.presigned_url(path) for path in image_paths]
    return {
        "id": project.id,
        "name": project.name,
        "researcher_comment": project.researcher_comment or "",
        "published_at": project.published_at.isoformat() if project.published_at else None,
        "pdf_url": storage.presigned_url(project.published_pdf_path) if project.published_pdf_path else "",
        "image_urls": published_image_urls or research_image_urls,
        "published_image_urls": published_image_urls,
        "research_image_urls": research_image_urls,
        "research_images": research_images,
    }


def _validate_publish_images(images: list[UploadFile]) -> list[tuple[str, str, bytes]]:
    if len(images) > _MAX_PUBLISH_IMAGES:
        raise HTTPException(status_code=400, detail="You can publish at most 2 JPG or PNG images.")

    validated = []
    for image in images:
        content_type = image.content_type or ""
        if content_type not in _PUBLISH_IMAGE_TYPES:
            raise HTTPException(status_code=400, detail="Published images must be JPG or PNG files.")

        data = image.file.read()
        image.file.seek(0)
        if len(data) > _MAX_PUBLISH_IMAGE_BYTES:
            raise HTTPException(status_code=400, detail="Each published image must be 2 MB or smaller.")

        validated.append((image.filename or "image", content_type, data))

    return validated


def _storage_path_from_public_url(pdf_url: str, storage) -> str | None:
    public_base_url = os.environ.get("PUBLIC_OBJECT_BASE_URL", "").rstrip("/")
    bucket = getattr(storage, "_bucket", os.environ.get("MINIO_BUCKET", "mars2020"))
    parsed = urlparse(pdf_url)

    if public_base_url:
        public = urlparse(public_base_url)
        if parsed.scheme == public.scheme and parsed.netloc == public.netloc:
            prefix = f"/{bucket}/"
            if parsed.path.startswith(prefix):
                return unquote(parsed.path[len(prefix):])

    if parsed.hostname in {"minio", "localhost", "127.0.0.1"} and parsed.path.startswith(f"/{bucket}/"):
        return unquote(parsed.path[len(f"/{bucket}/"):])

    return None


def _download_pdf(pdf_url: str, storage=None) -> bytes:
    if storage is not None:
        storage_path = _storage_path_from_public_url(pdf_url, storage)
        if storage_path:
            return storage.download_bytes(storage_path)

    response = requests.get(pdf_url, timeout=20)
    response.raise_for_status()
    return response.content


def _image_ext(filename: str, content_type: str) -> str:
    ext = os.path.splitext(filename)[1].lower()
    if ext in (".jpg", ".jpeg", ".png"):
        return ".jpg" if ext == ".jpeg" else ext
    return _PUBLISH_IMAGE_TYPES[content_type]


@router.post("", status_code=201)
def create_project(
    req: CreateProjectRequest,
    db: Session = Depends(get_db),
    user_id: str = Depends(_user_id),
):
    count = db.query(Project).filter(Project.user_id == user_id, Project.published_at.is_(None)).count()
    if count >= _MAX_PROJECTS:
        raise HTTPException(
            status_code=400,
            detail="You can't create more than 3 not published projects. Publish or delete one first.",
        )
    p = Project(user_id=user_id, name=req.name)
    db.add(p)
    db.commit()
    db.refresh(p)
    return {
        "id": p.id,
        "name": p.name,
        "status": _project_status(p),
        "created_at": p.created_at.isoformat(),
        "image_count": 0,
    }


@router.get("")
def list_projects(
    db: Session = Depends(get_db),
    user_id: str = Depends(_user_id),
):
    projects = db.query(Project).filter(Project.user_id == user_id).all()
    return [
        {
            "id": p.id,
            "name": p.name,
            "status": _project_status(p),
            "created_at": p.created_at.isoformat(),
            "image_count": len(p.images),
        }
        for p in projects
    ]


@router.get("/published")
def list_published_projects(db: Session = Depends(get_db)):
    try:
        storage = get_storage_adapter()
    except Exception:
        storage = None

    projects = (
        db.query(Project)
        .filter(Project.published_at.is_not(None))
        .order_by(Project.published_at.desc())
        .all()
    )
    if storage is None:
        return [
            {
                "id": p.id,
                "name": p.name,
                "researcher_comment": p.researcher_comment or "",
                "published_at": p.published_at.isoformat() if p.published_at else None,
                "pdf_url": "",
                "image_urls": [],
                "published_image_urls": [],
                "research_image_urls": [],
                "research_images": [],
            }
            for p in projects
        ]
    return [_public_project_response(p, storage) for p in projects]


@router.get("/generated-previews")
def generated_previews(
    lids: str,
):
    requested = [lid.strip() for lid in lids.split(",") if lid.strip()]
    if not requested:
        return {}

    try:
        storage = get_storage_adapter()
    except Exception:
        return {}

    tails = {_lid_tail(lid): lid for lid in requested if _lid_tail(lid)}
    if not tails:
        return {}

    preview_paths = [
        path for path in storage.list_objects("transformed/mastcamz/")
        if path.endswith("/rgb.jpg") or path.endswith("/gray.jpg")
    ]

    response = {}
    for lid in tails.values():
        matches = [
            path for path in preview_paths
            if _preview_path_matches_request(path, lid)
        ]
        if not matches:
            continue
        selected = next((path for path in matches if path.endswith("/rgb.jpg")), matches[0])
        response[lid] = {
            "thumb_url": storage.presigned_url(selected),
            "preview_source": "generated_transform",
        }
    return response


@router.get("/{project_id}")
def get_project(
    project_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(_user_id),
):
    p = _get_project_or_404(project_id, user_id, db)
    try:
        storage = get_storage_adapter()
    except Exception:
        storage = None

    return {
        "id": p.id,
        "name": p.name,
        "status": _project_status(p),
        "created_at": p.created_at.isoformat(),
        "images": [
            {
                "id": img.id,
                "lid": img.lid,
                "thumb_url": (
                    _display_thumb_url(img.thumb_url, storage)
                    if storage is not None
                    else img.thumb_url
                ),
                "preview_source": _preview_source(img.thumb_url),
                "sol": img.sol or "",
                "added_at": img.added_at.isoformat(),
                "analysis_cache": _analysis_cache_for_lid(db, img.lid),
            }
            for img in p.images
        ],
    }


@router.post("/{project_id}/publish")
def publish_project(
    project_id: str,
    comment: str = Form(...),
    pdf_url: str = Form(...),
    images: list[UploadFile] = File(default=[]),
    db: Session = Depends(get_db),
    user_id: str = Depends(_user_id),
):
    p = _get_project_or_404(project_id, user_id, db)
    comment = comment.strip()
    if not comment:
        raise HTTPException(status_code=400, detail="Researcher comment is required.")
    if not pdf_url.strip():
        raise HTTPException(status_code=400, detail="PDF report URL is required.")

    validated_images = _validate_publish_images(images)

    try:
        storage = get_storage_adapter()
        pdf_bytes = _download_pdf(pdf_url.strip(), storage)
        pdf_path = f"published/{project_id}/report.pdf"
        storage.upload_bytes(pdf_path, pdf_bytes, "application/pdf")

        image_paths = []
        for idx, (filename, content_type, data) in enumerate(validated_images, start=1):
            image_path = f"published/{project_id}/images/{idx}{_image_ext(filename, content_type)}"
            storage.upload_bytes(image_path, data, content_type)
            image_paths.append(image_path)
    except requests.RequestException as exc:
        raise HTTPException(status_code=400, detail=f"Could not download PDF report: {exc}") from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Could not publish project: {exc}") from exc

    p.researcher_comment = comment
    p.published_pdf_path = pdf_path
    p.published_image_paths = json.dumps(image_paths)
    p.published_at = datetime.utcnow()
    db.commit()
    db.refresh(p)

    return _public_project_response(p, storage)


@router.delete("/{project_id}", status_code=204)
def delete_project(
    project_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(_user_id),
):
    p = _get_project_or_404(project_id, user_id, db)
    db.delete(p)
    db.commit()


@router.post("/{project_id}/images", status_code=201)
def add_image(
    project_id: str,
    req: AddImageRequest,
    db: Session = Depends(get_db),
    user_id: str = Depends(_user_id),
):
    p = _get_project_or_404(project_id, user_id, db)
    if len(p.images) >= _MAX_IMAGES:
        raise HTTPException(status_code=400, detail=f"Maximum {_MAX_IMAGES} images per project")
    if any(img.lid == req.lid for img in p.images):
        raise HTTPException(status_code=409, detail="Image already in project")

    result = {}
    index_warning = None
    if req.thumb_url.strip():
        result = index_product(req.lid, req.thumb_url)
        if result.get("status", "").startswith("error"):
            index_warning = f"Could not add image to vector search: {result.get('error') or result.get('status')}"
    else:
        index_warning = "Could not add image to vector search: no preview URL is available."

    img = ProjectImage(
        project_id=project_id,
        lid=req.lid,
        thumb_url=req.thumb_url,
        sol=result.get("sol") or "",
    )
    db.add(img)
    db.commit()
    db.refresh(img)
    return {
        "id": img.id,
        "lid": img.lid,
        "thumb_url": img.thumb_url,
        "sol": img.sol or "",
        "added_at": img.added_at.isoformat(),
        "index_warning": index_warning,
    }


@router.delete("/{project_id}/images/{lid}", status_code=204)
def remove_image(
    project_id: str,
    lid: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(_user_id),
):
    p = _get_project_or_404(project_id, user_id, db)
    img = next((i for i in p.images if i.lid == lid), None)
    if not img:
        raise HTTPException(status_code=404, detail="Image not in project")
    db.delete(img)
    db.commit()
