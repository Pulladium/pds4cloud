"""
nodes/transform/core.py — LangGraph entry point for the transform node.
"""

import os
import re

from nodes.ingest.storage import get_storage_adapter
from .db import pg_fetch_pending
from .logic import process_one_task

_SOL_RE = re.compile(r"sol=(\d{5})", re.IGNORECASE)


def _scan_storage_for_pending(storage, limit: int | None) -> list[tuple]:
    """
    Fallback when Postgres is not available.
    Lists .IMG files under mastcamz/ and returns (photo_id, sol, source_path) tuples.
    """
    rows = []
    for path in storage.list_objects("mastcamz/"):
        if not path.lower().endswith(".img"):
            continue
        m = _SOL_RE.search(path)
        sol = int(m.group(1)) if m else None
        photo_id = os.path.splitext(os.path.basename(path))[0]
        rows.append((photo_id, sol, path))
        if limit is not None and len(rows) >= limit:
            break
    return rows


def run_transform(state) -> dict:
    limit = state.get("transform_limit")

    # --- storage first (needed for both the PG and scan paths) ---
    try:
        storage = get_storage_adapter()
    except Exception as e:
        msg = f"transform: storage unavailable ({type(e).__name__}), skipped"
        print(msg)
        return {
            "transformed": 0,
            "status": "transform_skipped",
            "messages": list(state.get("messages", [])) + [msg],
        }

    # --- primary: Postgres queue; fallback: scan storage ---
    try:
        rows = pg_fetch_pending(limit)
        source = "postgres"
    except RuntimeError:
        rows = _scan_storage_for_pending(storage, limit)
        source = "scan"

    print(f"transform: {len(rows)} pending rows (source={source})", flush=True)

    if not rows:
        msg = f"transform: nothing pending (source={source})"
        print(msg)
        return {
            "transformed": 0,
            "status": "transform_done",
            "messages": list(state.get("messages", [])) + [msg],
        }

    # --- sequential processing ---
    transformed = 0
    errors      = 0
    skipped     = 0

    for photo_id, sol, source_path in rows:
        result = process_one_task(photo_id, sol, source_path, storage)
        status = result.get("status", "")
        if status == "ok":
            transformed += 1
        elif status == "skip_all":
            skipped += 1
        else:
            errors += 1

    print(f"transform: done transformed={transformed} skipped={skipped} errors={errors}")

    return {
        "transformed": transformed,
        "status": "transform_done",
        "messages": list(state.get("messages", [])) + [
            f"transform: transformed={transformed} skipped={skipped} errors={errors} source={source}"
        ],
    }
