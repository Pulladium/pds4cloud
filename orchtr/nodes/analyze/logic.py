"""
nodes/analyze/logic.py — analyze_one_task and OpenAI helpers.
"""

import base64
import json
import os
import time
from datetime import datetime, timezone

from utils.eval_faults import get_eval_fault_registry
from utils.retry import NonRetryableError, retry_call

try:
    from .db import pg_mark_analysis_running, pg_mark_analysis_done, pg_mark_analysis_failed
except ImportError:
    pg_mark_analysis_running = None  # type: ignore[assignment]
    pg_mark_analysis_done = None  # type: ignore[assignment]
    pg_mark_analysis_failed = None  # type: ignore[assignment]

_DEFAULT_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o")


def _maybe_raise_eval_fault(stage: str, lid: str) -> None:
    fault = get_eval_fault_registry().should_fail(stage, "", lid)
    if fault:
        print(f"EVAL_FAULT injected {json.dumps(fault, sort_keys=True)}", flush=True)
        raise TimeoutError(f"eval fault injected: {fault['fault_id']}")


def _metadata_properties(metadata: dict) -> dict:
    if not isinstance(metadata, dict):
        return {}
    return metadata.get("properties") or metadata


def _pick0(v, default="unknown"):
    if isinstance(v, list) and v:
        return v[0]
    if v is None:
        return default
    return v


def _metadata_context_value(metadata: dict, key: str, default="unknown"):
    raw = _metadata_properties(metadata)
    return _pick0(raw.get(key), default)


def _analysis_context_text(
    metadata: dict,
    array_summary: dict | None = None,
    metadata_loaded: bool = False,
) -> str:
    array_summary = array_summary or {}
    image_type = metadata.get("image_type") or _metadata_context_value(
        metadata,
        "img_surface:Instrument_Information.img_surface:image_type",
    )
    sol = metadata.get("sol") or _metadata_context_value(
        metadata,
        "mars2020:Observation_Information.mars2020:sol_number",
    )
    processing = metadata.get("processing") or _metadata_context_value(
        metadata,
        "pds:Primary_Result_Summary.pds:processing_level",
    )
    metadata_json = json.dumps(metadata, ensure_ascii=False, indent=2)
    return (
        "\nSCIENTIFIC CONTEXT:\n"
        f"- Full raw metadata loaded: {'yes' if metadata_loaded else 'no'}\n"
        f"- Image Type: {image_type}\n"
        f"- Bands Used: R=631nm, G=544nm, B=480nm\n"
        f"- Location:   Jezero Crater\n"
        f"- Sol:        {sol}\n"
        f"- Processing: {processing}\n"
        f"- Array shape: {array_summary.get('shape', 'unknown')}\n"
        f"- Array dtype: {array_summary.get('dtype', 'unknown')}\n"
        f"- PDS4 bands: {array_summary.get('bands', 'unknown')}\n"
        f"- Selected RGB bands: {array_summary.get('selected_rgb_bands', 'unknown')}\n"
        "\nFULL RAW PDS METADATA JSON:\n"
        f"{metadata_json}\n"
    )


def _call_openai(
    img_bytes: bytes,
    metadata: dict,
    array_summary: dict | object,
    client=None,
    model: str | None = None,
    metadata_loaded: bool = False,
) -> dict:
    if client is None:
        client = array_summary
        array_summary = {}

    b64 = base64.b64encode(img_bytes).decode("utf-8")

    ctx = _analysis_context_text(metadata, array_summary if isinstance(array_summary, dict) else {}, metadata_loaded=metadata_loaded)

    prompt = (
        "You are a planetary science expert analyzing Mars rover Mastcam-Z imagery.\n"
        f"{ctx}\n"
        "ANALYSIS TASK:\n"
        "1. Geological Features\n"
        "2. Spectral Analysis\n"
        "3. Scientific Significance\n"
        "4. Data Quality Assessment\n"
        "5. Hypotheses\n\n"
        "Return STRICT JSON:\n"
        "{\n"
        '  "geological_features": "...",\n'
        '  "spectral_interpretation": "...",\n'
        '  "scientific_significance": "...",\n'
        '  "data_quality": "...",\n'
        '  "hypotheses": ["...", "..."],\n'
        '  "recommended_followup": "..."\n'
        "}"
    )

    effective_model = model or _DEFAULT_MODEL

    resp = client.chat.completions.create(
        model=effective_model,
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {
                    "url": f"data:image/jpeg;base64,{b64}",
                    "detail": "high",
                }},
            ],
        }],
    )

    content = resp.choices[0].message.content or ""
    start = content.find("{")
    end = content.rfind("}") + 1
    if start < 0 or end <= start:
        raise NonRetryableError(f"Model returned non-JSON: {content[:200]}")
    try:
        analysis = json.loads(content[start:end])
    except json.JSONDecodeError as exc:
        raise NonRetryableError(f"Model returned invalid JSON: {content[:200]}") from exc

    usage = resp.usage
    prompt_tokens     = getattr(usage, "prompt_tokens",     0) or 0
    completion_tokens = getattr(usage, "completion_tokens", 0) or 0
    actual_model      = getattr(resp, "model", None) or effective_model

    return {
        **analysis,
        "prompt_tokens":     prompt_tokens,
        "completion_tokens": completion_tokens,
        "model":             actual_model,
        "cost_usd":          None,
    }


def analyze_one_task(
    photo_id: str,
    sol_str: str,
    storage,
    openai_client,
    model: str | None = None,
    result_path: str | None = None,
) -> dict:
    effective_model = model or _DEFAULT_MODEL

    result_path = result_path or f"analysis/mastcamz/sol={sol_str}/{photo_id}/result.json"

    # --- idempotency ---
    if storage.exists(result_path):
        pg_mark_analysis_done(photo_id, result_path)
        print(f"  SKIP: result exists {result_path}")
        return {"status": "skip", "photo_id": photo_id, "result_path": result_path}

    pg_mark_analysis_running(photo_id)

    try:
        # --- find best image (prefer rgb) ---
        rgb_path  = f"transformed/mastcamz/sol={sol_str}/{photo_id}/rgb.jpg"
        gray_path = f"transformed/mastcamz/sol={sol_str}/{photo_id}/gray.jpg"

        if storage.exists(rgb_path):
            img_path, kind = rgb_path, "rgb"
        elif storage.exists(gray_path):
            img_path, kind = gray_path, "gray"
        else:
            raise FileNotFoundError(
                f"No transformed image found for sol={sol_str} photo_id={photo_id}"
            )

        def _download_image_bytes():
            _maybe_raise_eval_fault("analyze_image_download", photo_id)
            return storage.download_bytes(img_path)

        img_bytes = retry_call(
            _download_image_bytes,
            attempts=3,
            delays=(0.0, 2.0),
            sleep_fn=time.sleep,
        )

        # --- metadata (best-effort; explicitly report if not found) ---
        metadata: dict = {"sol": sol_str, "location": "Jezero Crater"}
        metadata_loaded = False
        meta_path: str | None = None
        candidate = f"mastcamz/sol={sol_str}/{photo_id}_metadata.json"
        try:
            metadata = json.loads(storage.download_bytes(candidate).decode("utf-8"))
            metadata_loaded = True
            meta_path = candidate
        except Exception:
            pass

        array_summary = {}
        array_summary_path = f"transformed/mastcamz/sol={sol_str}/{photo_id}/array_summary.json"
        try:
            array_summary = json.loads(storage.download_bytes(array_summary_path).decode("utf-8"))
        except Exception:
            array_summary_path = None

        # --- OpenAI call ---
        def _run_openai_analysis():
            _maybe_raise_eval_fault("analyze_openai_call", photo_id)
            return _call_openai(
                img_bytes,
                metadata,
                array_summary,
                openai_client,
                model=effective_model,
                metadata_loaded=metadata_loaded,
            )

        analysis = retry_call(
            _run_openai_analysis,
            attempts=3,
            delays=(0.0, 2.0),
            sleep_fn=time.sleep,
            on_retry=lambda attempt, exc, delay: print(
                f"  WARN: analyze retry {attempt}/3 photo_id={photo_id}: {exc}"
                + (f" — retry in {delay:.0f}s" if delay > 0 else ""),
                flush=True,
            ),
        )

        # --- upload result ---
        payload = {
            "photo_id":      photo_id,
            "sol":           sol_str,
            "analyzed_at":   datetime.now(timezone.utc).isoformat(),
            "used_image":    {"path": img_path, "kind": kind},
            "metadata_path": meta_path,
            "metadata_loaded": metadata_loaded,
            "metadata_summary": metadata,
            "array_summary_path": array_summary_path,
            "array_summary": array_summary,
            "analysis":      analysis,
        }
        def _upload_analysis_result():
            _maybe_raise_eval_fault("analyze_result_upload", photo_id)
            return storage.upload_bytes(
                result_path,
                json.dumps(payload, ensure_ascii=False, indent=2).encode(),
                "application/json",
            )

        retry_call(
            _upload_analysis_result,
            attempts=3,
            delays=(0.0, 2.0),
            sleep_fn=time.sleep,
        )
        print(f"  OK: uploaded {result_path}")
        pg_mark_analysis_done(photo_id, result_path)
        return {"status": "ok", "photo_id": photo_id, "result_path": result_path}

    except Exception as e:
        pg_mark_analysis_failed(photo_id, type(e).__name__)
        print(f"  ERROR: analyze failed photo_id={photo_id}: {e}")
        return {"status": "error", "photo_id": photo_id, "error": str(e)}
