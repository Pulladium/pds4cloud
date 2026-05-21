import base64
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from nodes.qdrant.clip_client import embed_image, embed_text
from nodes.ingest.storage import get_storage_adapter
from nodes.qdrant.graph import index_product
from nodes.qdrant.nodes import lid_to_point_id
from nodes.qdrant.qdrant_client import COLLECTION_NAME, ensure_collection, get_qdrant_client

router = APIRouter(prefix="/api/qdrant", tags=["qdrant"])


class AddRequest(BaseModel):
    lid:       str
    thumb_url: str
    force:     bool = False


class SearchRequest(BaseModel):
    query_text:      Optional[str] = None
    query_image_b64: Optional[str] = None
    ref_lid:         Optional[str] = None
    limit:           int = 10


def _display_thumb_url(raw_url: str | None) -> str:
    if not raw_url:
        return ""
    marker = "storage:"
    if not raw_url.startswith(marker):
        return raw_url
    try:
        return get_storage_adapter().presigned_url(raw_url[len(marker):])
    except Exception:
        return raw_url


def _preview_source(raw_url: str | None) -> str:
    return "generated_transform" if raw_url and raw_url.startswith("storage:") else "external"


@router.post("/add")
def add_to_qdrant(req: AddRequest):
    ensure_collection()
    point_id = lid_to_point_id(req.lid)

    if not req.force:
        existing = get_qdrant_client().retrieve(
            collection_name=COLLECTION_NAME,
            ids=[point_id],
        )
        if existing:
            return {"status": "already_indexed", "point_id": point_id}

    result = index_product(req.lid, req.thumb_url)

    if result.get("status", "").startswith("error"):
        detail = result.get("error") or result["status"]
        if "CLIP service unavailable" in detail:
            raise HTTPException(status_code=503, detail="CLIP service unavailable")
        raise HTTPException(status_code=502, detail=detail)

    return {"status": "ok", "point_id": result["point_id"]}


@router.post("/search")
def search_qdrant(req: SearchRequest):
    provided = sum([
        req.query_text is not None,
        req.query_image_b64 is not None,
        req.ref_lid is not None,
    ])
    if provided != 1:
        raise HTTPException(
            status_code=400,
            detail="Provide exactly one of: query_text, query_image_b64, ref_lid",
        )

    ensure_collection()
    client = get_qdrant_client()

    if req.query_text:
        try:
            vector = embed_text(req.query_text)
        except RuntimeError:
            raise HTTPException(status_code=503, detail="CLIP service unavailable")

    elif req.query_image_b64:
        try:
            img_bytes = base64.b64decode(req.query_image_b64)
            vector = embed_image(img_bytes)
        except RuntimeError:
            raise HTTPException(status_code=503, detail="CLIP service unavailable")

    else:  # ref_lid
        point_id = lid_to_point_id(req.ref_lid)
        points = client.retrieve(
            collection_name=COLLECTION_NAME,
            ids=[point_id],
            with_vectors=True,
        )
        if not points:
            raise HTTPException(status_code=404, detail="Image not indexed yet")
        vector = points[0].vector

    response = client.query_points(
        collection_name=COLLECTION_NAME,
        query=vector,
        limit=req.limit,
        with_payload=True,
    )
    hits = response.points

    return [
        {
            "score":     h.score,
            "lid":       h.payload.get("lid"),
            "photo_id":  h.payload.get("photo_id"),
            "sol":       h.payload.get("sol"),
            "thumb_url": _display_thumb_url(h.payload.get("thumb_url")),
            "preview_source": _preview_source(h.payload.get("thumb_url")),
            "pds_meta":  {
                k: v for k, v in h.payload.items()
                if k not in ("lid", "photo_id", "sol", "thumb_url")
            },
        }
        for h in hits
    ]
