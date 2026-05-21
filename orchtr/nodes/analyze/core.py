"""
nodes/analyze/core.py — LangGraph entry point for the analyze node.
"""

import os
import re

from nodes.ingest.storage import get_storage_adapter
from .db import pg_fetch_pending_analysis
from .logic import analyze_one_task

_SOL_STEM_RE = re.compile(r"sol=(\d{5})/([^/]+)/gray\.jpg$")


def _scan_storage_for_pending(storage, limit: int | None) -> list[tuple]:
    """
    Fallback when Postgres is not available.
    Lists gray.jpg files under transformed/mastcamz/ and returns
    (photo_id, sol_str) tuples that don't yet have a result.json.
    """
    rows = []
    for path in storage.list_objects("transformed/mastcamz/"):
        m = _SOL_STEM_RE.search(path)
        if not m:
            continue
        sol_str, stem = m.group(1), m.group(2)
        result_path = f"analysis/mastcamz/sol={sol_str}/{stem}/result.json"
        if storage.exists(result_path):
            continue  # already analyzed
        rows.append((stem, sol_str))
        if limit is not None and len(rows) >= limit:
            break
    return rows


def run_analyze(state) -> dict:
    limit    = state.get("analyze_limit")
    messages = list(state.get("messages", []))

    # --- storage ---
    try:
        storage = get_storage_adapter()
    except Exception as e:
        msg = f"analyze: storage unavailable ({type(e).__name__}), skipped"
        print(msg)
        return {"analyzed": 0, "status": "analyze_skipped", "messages": messages + [msg]}

    # --- OpenAI client ---
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        msg = "analyze: OPENAI_API_KEY not set, skipped"
        print(msg)
        return {"analyzed": 0, "status": "analyze_skipped", "messages": messages + [msg]}

    from openai import OpenAI
    openai_client = OpenAI(api_key=api_key)

    # --- primary: Postgres queue; fallback: scan storage ---
    try:
        pg_rows = pg_fetch_pending_analysis(limit)
        rows = [(str(photo_id), str(sol).zfill(5)) for photo_id, sol in pg_rows]
        source = "postgres"
    except RuntimeError:
        rows = _scan_storage_for_pending(storage, limit)
        source = "scan"

    print(f"analyze: {len(rows)} pending (source={source})", flush=True)

    if not rows:
        msg = f"analyze: nothing pending (source={source})"
        print(msg)
        return {"analyzed": 0, "status": "analyze_done", "messages": messages + [msg]}

    ok = fail = skip = 0
    for photo_id, sol_str in rows:
        result = analyze_one_task(photo_id, sol_str, storage, openai_client)
        s = result.get("status", "")
        if s == "ok":
            ok += 1
        elif s == "skip":
            skip += 1
        else:
            fail += 1

    print(f"analyze: done ok={ok} skip={skip} fail={fail}")
    return {
        "analyzed": ok,
        "status":   "analyze_done",
        "messages": messages + [
            f"analyze: done={ok} skip={skip} fail={fail} source={source}"
        ],
    }
