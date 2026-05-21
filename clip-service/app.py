import base64
import io

from fastapi import FastAPI, HTTPException
from PIL import Image
from pydantic import BaseModel
from sentence_transformers import SentenceTransformer

app = FastAPI(title="CLIP Embedding Service")
_model: SentenceTransformer | None = None


@app.on_event("startup")
def load_model() -> None:
    global _model
    _model = SentenceTransformer("clip-ViT-B-32")


class TextRequest(BaseModel):
    text: str


class ImageRequest(BaseModel):
    image_b64: str


@app.post("/embed/text")
def embed_text(req: TextRequest):
    if _model is None:
        raise HTTPException(status_code=503, detail="Model not loaded")
    return {"vector": _model.encode(req.text).tolist()}


@app.post("/embed/image")
def embed_image(req: ImageRequest):
    if _model is None:
        raise HTTPException(status_code=503, detail="Model not loaded")
    try:
        raw = base64.b64decode(req.image_b64)
        img = Image.open(io.BytesIO(raw)).convert("RGB")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid image: {exc}")
    return {"vector": _model.encode(img).tolist()}


@app.get("/health")
def health():
    return {"status": "ok", "model_loaded": _model is not None}
