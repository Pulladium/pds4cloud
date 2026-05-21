"""
nodes/analyze/one.py — Analyze a single product with OpenAI vision.

Reuses analyze_one_task from logic.py.
"""

import json
import os

from openai import OpenAI
from langsmith.wrappers import wrap_openai

from database import SessionLocal
from nodes.ingest.storage import get_storage_adapter
from services.analysis_artifacts import ready_artifacts_for_scope, mark_failed, mark_ready, reserve_analysis
from . import db
from .logic import analyze_one_task


def run_analyze_one(state: dict) -> dict:
    messages = list(state.get("messages", []))

    if state.get("status", "").startswith("error"):
        return {"status": state["status"], "messages": messages}

    photo_id = state["photo_id"]
    sol      = state["sol"]
    model    = state.get("model")
    product_lid = state.get("product_lid") or state.get("lid") or photo_id
    project_id = state.get("project_id") or ""
    job_id = state.get("job_id") or ""
    user_id = state.get("user_id")
    storage = get_storage_adapter()
    analysis_id = None
    result_path = None
    session = None
    artifact_failed = False
    used_reusable_artifact = False

    result = None
    session = SessionLocal()
    try:
        for reusable in ready_artifacts_for_scope(session, product_lid, project_id, user_id):
            if storage.exists(reusable.result_path):
                analysis_id = reusable.id
                result_path = reusable.result_path
                result = {"status": "skip", "photo_id": photo_id, "result_path": result_path}
                used_reusable_artifact = True
                break
    finally:
        session.close()

    api_key = os.environ.get("OPENAI_API_KEY")
    if result is None and not api_key:
        msg = "analyze_one: OPENAI_API_KEY not set, skipped"
        print(msg, flush=True)
        return {
            "analysis_id": None,
            "result_path": None,
            "analysis":    {},
            "status":      "analyze_skipped",
            "messages":    messages + [msg],
        }

    try:
        if result is None:
            session = SessionLocal()
            artifact = reserve_analysis(
                session,
                product_lid=product_lid,
                photo_id=photo_id,
                sol=sol,
                project_id=project_id,
                job_id=job_id,
                user_id=user_id,
                model=model,
            )
            analysis_id = artifact.id
            result_path = artifact.result_path

            openai_client = wrap_openai(OpenAI(api_key=api_key))
            print(f"analyze_one: photo_id={photo_id} sol={sol} model={model}", flush=True)
            result = analyze_one_task(
                photo_id,
                sol,
                storage,
                openai_client,
                model=model,
                result_path=result_path,
            )
    except Exception as exc:
        error_text = str(exc)
        if analysis_id:
            mark_failed(session, analysis_id, error_text)
            artifact_failed = True
        result = {"status": "error", "photo_id": photo_id, "error": error_text}
    finally:
        if session is not None:
            session.close()

    # Load the analysis dict from storage for the API response
    token_fields = {
        "prompt_tokens":     0,
        "completion_tokens": 0,
        "model":             None,
        "cost_usd":          None,
    }
    analysis = {}
    result_path = result.get("result_path") or result_path
    if result.get("status") in ("ok", "skip") and result_path:
        try:
            raw = storage.download_bytes(result_path)
            payload = json.loads(raw.decode("utf-8"))
            analysis = payload.get("analysis", {})
            analysis["metadata_loaded"] = payload.get("metadata_loaded", False)
            analysis["metadata_summary"] = payload.get("metadata_summary", {})
            analysis["array_summary"] = payload.get("array_summary", {})
            token_fields = {
                "prompt_tokens":     analysis.pop("prompt_tokens",     0) or 0,
                "completion_tokens": analysis.pop("completion_tokens", 0) or 0,
                "model":             analysis.pop("model",             None),
                "cost_usd":          analysis.pop("cost_usd",          None),
            }
        except Exception as _e:
            messages = messages + [f"analyze_one: failed to load token fields: {_e}"]

    result_status = result.get("status", "error")
    status = f"analyze_{result_status}"
    error = result.get("error")
    if result_status == "error":
        status = "error_analyze"
        if analysis_id and not artifact_failed:
            session = SessionLocal()
            try:
                mark_failed(session, analysis_id, error or "analysis failed")
            finally:
                session.close()
    elif result_status in ("ok", "skip") and analysis_id and not used_reusable_artifact:
        session = SessionLocal()
        try:
            mark_ready(session, analysis_id)
        finally:
            session.close()

    response = {
        "analysis_id": analysis_id if result_status in ("ok", "skip") else None,
        "result_path": result_path if result_status in ("ok", "skip") else None,
        "analysis":    analysis,
        "status":      status,
        "messages":    messages + [
            f"analyze_one: {result_status} photo_id={photo_id}"
        ],
        **token_fields,
    }
    if error:
        response["error"] = error
    return response
