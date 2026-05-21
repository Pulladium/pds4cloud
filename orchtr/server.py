"""
server.py — FastAPI server for the single-product pipeline.

Start with:
    .venv/bin/uvicorn server:app --host 0.0.0.0 --port 8000 --reload

Frontend calls:
    POST /api/process        — trigger pipeline for one product
    GET  /api/result/{photo_id}/{sol}  — fetch cached analysis
    GET  /api/image-url      — get presigned image URL
"""

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from graph_single import process_product
from nodes.ingest.storage import get_storage_adapter
from routers.qdrant import router as qdrant_router
from database import SessionLocal, init_db
from services.analysis_artifacts import completed_artifacts_for_photo
from routers.projects import router as projects_router
from routers.chat import router as chat_router
from routers.langsmith import router as langsmith_router
from routers.models import router as models_router

@asynccontextmanager
async def _lifespan(app: FastAPI):
    init_db()
    if os.getenv("KAFKA_ENABLED", "true").lower() != "false":
        from messaging.dispatcher import start_dispatcher
        from messaging.image_worker import start_workers
        from messaging.aggregator import start_aggregator
        start_dispatcher()
        start_workers()
        start_aggregator()
    yield


app = FastAPI(title="Mars Mastcam-Z Pipeline API", lifespan=_lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(qdrant_router)
app.include_router(projects_router)
app.include_router(chat_router)
app.include_router(langsmith_router)
app.include_router(models_router)


# ── Request / Response models ──────────────────────────────────────────────────

class ProcessRequest(BaseModel):
    lid: str


class ImageUrlRequest(BaseModel):
    path:    str
    expires: int = 3600   # seconds


# ── Endpoints ──────────────────────────────────────────────────────────────────
@app.post("/api/process")
def process(req: ProcessRequest, x_user_id: str | None = Header(default=None)):
    """
    Trigger the full pipeline for one product.

    The frontend should pass as many hints as possible (sol, label_url,
    img_filename) so the backend can skip the PDS registry lookup.

    Returns the analysis result plus presigned URLs for the images.
    """
    result = process_product(req.lid, user_id=x_user_id)

    if result.get("status", "").startswith("error"):
        raise HTTPException(
            status_code=500,
            detail={"status": result["status"], "error": result.get("error"), "messages": result.get("messages", [])},
        )

    storage = get_storage_adapter()

    gray_url = rgb_url = None
    if result.get("gray_path") and storage.exists(result["gray_path"]):
        gray_url = storage.presigned_url(result["gray_path"])
    if result.get("rgb_path") and storage.exists(result["rgb_path"]):
        rgb_url = storage.presigned_url(result["rgb_path"])

    return {
        "photo_id":    result["photo_id"],
        "sol":         result["sol"],
        "status":      result["status"],
        "gray_url":    gray_url,
        "rgb_url":     rgb_url,
        "gray_path":   result.get("gray_path"),
        "rgb_path":    result.get("rgb_path"),
        "result_path": result.get("result_path"),
        "analysis_id": result.get("analysis_id"),
        "analysis":    result.get("analysis", {}),
        "messages":    result.get("messages", []),
    }


@app.get("/api/result/{sol}/{photo_id}")
def get_result(sol: str, photo_id: str):
    """
    Return a previously computed analysis result (without re-running the pipeline).
    """
    import json
    sol_str     = sol.zfill(5)
    storage     = get_storage_adapter()
    db = SessionLocal()
    try:
        candidate_paths = [artifact.result_path for artifact in completed_artifacts_for_photo(db, sol_str, photo_id)]
    finally:
        db.close()
    legacy_path = f"analysis/mastcamz/sol={sol_str}/{photo_id}/result.json"
    candidate_paths.append(legacy_path)

    result_path = None
    for candidate_path in candidate_paths:
        if storage.exists(candidate_path):
            result_path = candidate_path
            break

    if result_path is None:
        raise HTTPException(status_code=404, detail="Result not found")

    payload  = json.loads(storage.download_bytes(result_path).decode("utf-8"))
    gray_url = rgb_url = None

    gray_path = f"transformed/mastcamz/sol={sol_str}/{photo_id}/gray.jpg"
    rgb_path  = f"transformed/mastcamz/sol={sol_str}/{photo_id}/rgb.jpg"
    if storage.exists(gray_path):
        gray_url = storage.presigned_url(gray_path)
    if storage.exists(rgb_path):
        rgb_url = storage.presigned_url(rgb_path)

    return {
        "photo_id":  photo_id,
        "sol":       sol_str,
        "gray_url":  gray_url,
        "rgb_url":   rgb_url,
        "analysis":  payload.get("analysis", {}),
    }


@app.post("/api/image-url")
def image_url(req: ImageUrlRequest):
    """Return a presigned URL for any object in storage."""
    storage = get_storage_adapter()
    if not storage.exists(req.path):
        raise HTTPException(status_code=404, detail="Object not found")
    return {"url": storage.presigned_url(req.path, expires=req.expires)}


@app.get("/health")
def health():
    return {"status": "ok"}
