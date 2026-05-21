"""
nodes/transform/one.py — Transform a single product.

Reuses process_one_task from logic.py, then deletes the raw .IMG from
storage to free space (PDS data is re-downloadable on demand).
"""

import json

from nodes.ingest.storage import get_storage_adapter
from .logic import process_one_task


def run_transform_one(state: dict) -> dict:
    messages = list(state.get("messages", []))

    # skip if ingest already determined it's done
    if state.get("status") == "already_transformed":
        photo_id = state["photo_id"]
        sol      = state["sol"]
        gray_path = f"transformed/mastcamz/sol={sol}/{photo_id}/gray.jpg"
        rgb_path  = f"transformed/mastcamz/sol={sol}/{photo_id}/rgb.jpg"
        array_summary_path = f"transformed/mastcamz/sol={sol}/{photo_id}/array_summary.json"
        storage   = get_storage_adapter()
        array_summary = None
        summary_path = None
        if storage.exists(array_summary_path):
            try:
                array_summary = json.loads(storage.download_bytes(array_summary_path).decode("utf-8"))
                summary_path = array_summary_path
            except Exception as e:
                messages.append(f"transform_one: failed to load array summary: {e}")
        return {
            "gray_path": gray_path,
            "rgb_path":  rgb_path if storage.exists(rgb_path) else None,
            "array_summary_path": summary_path,
            "array_summary": array_summary,
            "status":    "transform_skipped",
            "messages":  messages + ["transform_one: skipped (already done)"],
        }

    if state.get("status", "").startswith("error"):
        return {"status": state["status"], "messages": messages}

    photo_id = state["photo_id"]
    sol      = state["sol"]
    img_path = state["img_path"]

    storage = get_storage_adapter()

    print(f"transform_one: photo_id={photo_id} sol={sol}", flush=True)
    result = process_one_task(photo_id, int(sol) if sol.isdigit() else None, img_path, storage)

    # --- delete raw .IMG to free space ---
    try:
        storage.delete_object(img_path)
        print(f"  Deleted raw IMG: {img_path}", flush=True)
    except Exception as e:
        print(f"  WARN: could not delete raw IMG: {e}", flush=True)

    sol_str   = sol
    gray_path = f"transformed/mastcamz/sol={sol_str}/{photo_id}/gray.jpg"
    rgb_path  = f"transformed/mastcamz/sol={sol_str}/{photo_id}/rgb.jpg"

    has_rgb = result.get("rgb") in ("uploaded", "exists")

    return {
        "gray_path": gray_path,
        "rgb_path":  rgb_path if has_rgb else None,
        "array_summary_path": result.get("array_summary_path"),
        "array_summary": result.get("array_summary"),
        "status":    result["status"],
        "messages":  messages + [
            f"transform_one: {result['status']} photo_id={photo_id} "
            f"gray={result.get('gray')} rgb={result.get('rgb')}"
        ],
    }
