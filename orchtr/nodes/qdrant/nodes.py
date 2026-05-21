import uuid
from urllib.parse import quote

import requests

from nodes.qdrant.clip_client import embed_image
from nodes.qdrant.qdrant_client import COLLECTION_NAME, get_qdrant_client

_PDS_API = "https://pds.mcp.nasa.gov/api/search/1"
_NAMESPACE = uuid.NAMESPACE_URL

_SOL_KEY      = "mars2020:Observation_Information.mars2020:sol_number"
_FILENAME_KEY = "pds:File.pds:file_name"


def lid_to_point_id(lid: str) -> str:
    return str(uuid.uuid5(_NAMESPACE, lid))


def fetch_image(state: dict) -> dict:
    lid       = state["lid"]
    thumb_url = state["thumb_url"]
    messages  = list(state.get("messages", []))

    # Download thumbnail
    try:
        resp = requests.get(thumb_url, timeout=30)
        resp.raise_for_status()
        img_bytes = resp.content
    except Exception as exc:
        return {
            "status":   f"error_thumb: {exc}",
            "error":    str(exc),
            "messages": messages,
        }

    # Fetch full PDS metadata (non-blocking on failure)
    pds_meta: dict = {}
    try:
        r = requests.get(f"{_PDS_API}/products/{quote(lid, safe='')}", timeout=15)
        if r.ok:
            data = r.json()
            pds_meta = (
                data.get("properties")
                or (data.get("data") or [{}])[0].get("properties")
                or {}
            )
    except Exception:
        pass

    # Parse sol and photo_id
    sol_raw  = (pds_meta.get(_SOL_KEY) or [None])[0]
    sol      = str(sol_raw).zfill(5) if sol_raw else "00000"
    raw_name = (pds_meta.get(_FILENAME_KEY) or [None])[0] or ""
    photo_id = raw_name.split(".")[0] or lid.split(":")[-1]

    return {
        "img_bytes": img_bytes,
        "pds_meta":  pds_meta,
        "photo_id":  photo_id,
        "sol":       sol,
        "status":    "fetched",
        "messages":  messages + [f"fetch_image: ok sol={sol} photo_id={photo_id}"],
    }


def embed_clip(state: dict) -> dict:
    messages = list(state.get("messages", []))
    if state.get("status", "").startswith("error"):
        return state

    try:
        vector = embed_image(state["img_bytes"])
    except RuntimeError as exc:
        return {
            "status":   f"error_clip: {exc}",
            "error":    str(exc),
            "messages": messages,
        }

    return {
        "vector":   vector,
        "status":   "embedded",
        "messages": messages + ["embed_clip: ok (512-dim)"],
    }


def upsert_qdrant(state: dict) -> dict:
    from qdrant_client.models import PointStruct

    messages = list(state.get("messages", []))
    if state.get("status", "").startswith("error"):
        return state

    lid      = state["lid"]
    point_id = lid_to_point_id(lid)

    payload = {
        "lid":       lid,
        "photo_id":  state["photo_id"],
        "sol":       state["sol"],
        "thumb_url": state["thumb_url"],
        **state.get("pds_meta", {}),
    }

    try:
        get_qdrant_client().upsert(
            collection_name=COLLECTION_NAME,
            points=[PointStruct(id=point_id, vector=state["vector"], payload=payload)],
        )
    except Exception as exc:
        return {
            "status":   f"error_qdrant: {exc}",
            "error":    str(exc),
            "messages": messages,
        }

    return {
        "status":   "ok",
        "point_id": point_id,
        "messages": messages + [f"upsert_qdrant: ok point_id={point_id}"],
    }
