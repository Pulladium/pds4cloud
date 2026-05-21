import base64
import os

import requests

CLIP_SERVICE_URL = os.getenv("CLIP_SERVICE_URL", "http://localhost:8001")


def embed_text(text: str) -> list[float]:
    try:
        resp = requests.post(
            f"{CLIP_SERVICE_URL}/embed/text",
            json={"text": text},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()["vector"]
    except requests.ConnectionError as exc:
        raise RuntimeError("CLIP service unavailable") from exc


def embed_image(img_bytes: bytes) -> list[float]:
    try:
        resp = requests.post(
            f"{CLIP_SERVICE_URL}/embed/image",
            json={"image_b64": base64.b64encode(img_bytes).decode()},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()["vector"]
    except requests.ConnectionError as exc:
        raise RuntimeError("CLIP service unavailable") from exc
