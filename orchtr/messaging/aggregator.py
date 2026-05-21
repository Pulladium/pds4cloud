import json
import logging
import os
import threading
import time

from kafka import KafkaConsumer

from database import SessionLocal
from jobs.pdf_gen import generate_pdf_bytes, upload_pdf
from messaging.producer import publish_status
from nodes.ingest.storage import get_storage_adapter
from services.analysis_artifacts import mark_evictable_and_prune, mark_in_report, release_to_ready
from utils.eval_faults import get_eval_fault_registry
from utils.retry import retry_call

logger = logging.getLogger(__name__)


def _maybe_raise_eval_fault(stage: str, job_id: str) -> None:
    registry = getattr(_maybe_raise_eval_fault, "_registry", None)
    provider = getattr(_maybe_raise_eval_fault, "_provider", None)
    if registry is None or provider is not get_eval_fault_registry:
        registry = get_eval_fault_registry()
        _maybe_raise_eval_fault._registry = registry
        _maybe_raise_eval_fault._provider = get_eval_fault_registry

    fault = registry.should_fail(stage, job_id)
    if fault:
        logger.warning("EVAL_FAULT injected %s", json.dumps(fault, sort_keys=True))
        raise TimeoutError(f"eval fault injected: {fault['fault_id']}")


def _langsmith_client():
    from langsmith import Client

    api_key = os.environ.get("LANGSMITH_API_KEY") or os.environ.get("LANGCHAIN_API_KEY")
    api_url = os.environ.get("LANGSMITH_ENDPOINT") or os.environ.get("LANGCHAIN_ENDPOINT")
    return Client(api_key=api_key, api_url=api_url)


def _fetch_langsmith_job_cost(job_id: str, attempts: int = 3, sleep_s: float = 1.0) -> float | None:
    project = os.environ.get("LANGSMITH_PROJECT") or os.environ.get("LANGCHAIN_PROJECT", "mars2020")
    query = f'has(tags, "job:{job_id}")'

    for attempt in range(attempts):
        try:
            runs = list(
                _langsmith_client().list_runs(
                    project_name=project,
                    run_type="llm",
                    filter=query,
                    limit=100,
                )
            )
            costs = [float(r.total_cost) for r in runs if getattr(r, "total_cost", None) is not None]
            if costs:
                return sum(costs)
        except Exception as exc:
            logger.warning("LangSmith observed cost lookup failed for job %s: %s", job_id, exc)

        if attempt < attempts - 1:
            time.sleep(sleep_s)

    return None


def _handle_image_result(payload: dict, state: dict) -> None:
    job_id     = payload["job_id"]
    total      = payload.get("total_images", 1)
    project_id = payload.get("project_id", "")

    if job_id not in state:
        state[job_id] = {
            "expected":   total,
            "results":    [],
            "seen_lids":  set(),
            "project_id": project_id,
        }

    lid = payload.get("lid", "")
    if lid in state[job_id]["seen_lids"]:
        logger.warning(
            "KAFKA_IDEMPOTENCY duplicate_image_result job=%s lid=%s guard=seen_lids final_effect=skipped_duplicate",
            job_id,
            lid,
        )
        return
    state[job_id]["seen_lids"].add(lid)
    state[job_id]["results"].append(payload)
    registry = get_eval_fault_registry()
    should_duplicate = getattr(registry, "should_duplicate", None)
    fault = should_duplicate("duplicate_image_result", job_id, lid) if should_duplicate else None
    if fault:
        logger.warning("EVAL_FAULT injected %s", json.dumps(fault, sort_keys=True))
        _handle_image_result(dict(payload), state)
    received = len(state[job_id]["results"])

    publish_status(job_id, "PROCESSING_IMAGES", f"{received}/{total}")

    if received < state[job_id]["expected"]:
        return

    results   = state.pop(job_id)["results"]
    succeeded = [r for r in results if r.get("status") == "ok" and r.get("analysis") is not None]
    failed    = [r for r in results if r not in succeeded]

    if not succeeded:
        errors = "; ".join(r.get("error", "unknown") for r in results)
        publish_status(job_id, "FAILED", "", error=f"All images failed: {errors}")
        return

    prompt_tokens     = sum(r.get("prompt_tokens",     0) or 0 for r in succeeded)
    completion_tokens = sum(r.get("completion_tokens", 0) or 0 for r in succeeded)
    observed_costs    = [r.get("cost_usd") for r in succeeded if r.get("cost_usd") is not None]
    cost_usd          = sum(observed_costs) if observed_costs else None
    model             = next((r.get("model") for r in succeeded if r.get("model")), None)
    analysis_ids      = [r.get("analysis_id") for r in succeeded if r.get("analysis_id")]

    db = None
    in_report_marked = False
    try:
        if analysis_ids:
            db = SessionLocal()
            mark_in_report(db, analysis_ids)
            in_report_marked = True

        publish_status(job_id, "GENERATING_PDF", "")
        pdf_bytes = retry_call(
            lambda: (
                _maybe_raise_eval_fault("pdf_generation", job_id),
                generate_pdf_bytes(job_id, project_id, results),
            )[1],
            attempts=3,
            delays=(0.0, 2.0),
            sleep_fn=time.sleep,
            on_retry=lambda attempt, exc, delay: logger.warning(
                "PDF generation attempt %d failed for job %s (%s), retry in %.0fs",
                attempt,
                job_id,
                exc,
                delay,
            ),
        )
        pdf_url = retry_call(
            lambda: (
                _maybe_raise_eval_fault("pdf_upload", job_id),
                upload_pdf(job_id, pdf_bytes),
            )[1],
            attempts=3,
            delays=(0.0, 2.0),
            sleep_fn=time.sleep,
            on_retry=lambda attempt, exc, delay: logger.warning(
                "PDF upload attempt %d failed for job %s (%s), retry in %.0fs",
                attempt,
                job_id,
                exc,
                delay,
            ),
        )
        if analysis_ids:
            try:
                mark_evictable_and_prune(db, analysis_ids, storage=get_storage_adapter())
            except Exception as exc:
                logger.error("Artifact lifecycle failed after report upload for job %s: %s", job_id, exc)
                publish_status(job_id, "FAILED", "", error=f"Artifact lifecycle failed: {exc}")
                return
    except Exception as exc:
        release_error = None
        if in_report_marked:
            try:
                release_to_ready(db, analysis_ids)
            except Exception as release_exc:
                release_error = release_exc
                logger.error("Failed to release artifacts after PDF failure for job %s: %s", job_id, release_exc)
        if analysis_ids and not in_report_marked:
            logger.error("Artifact lifecycle failed before report generation for job %s: %s", job_id, exc)
            publish_status(job_id, "FAILED", "", error=f"Artifact lifecycle failed: {exc}")
            return

        logger.error("PDF generation or upload failed for job %s: %s", job_id, exc)
        error = f"PDF generation/upload failed: {exc}"
        if release_error is not None:
            error = f"{error}; artifact release failed: {release_error}"
        publish_status(job_id, "FAILED", "", error=error)
        return
    finally:
        if db is not None:
            db.close()

    langsmith_cost = _fetch_langsmith_job_cost(job_id)
    if langsmith_cost is not None:
        cost_usd = langsmith_cost

    partial_error = None
    if failed:
        failed_lids = ", ".join(r.get("lid", "<unknown>") for r in failed)
        partial_error = f"{len(failed)} image(s) failed: {failed_lids}"

    publish_status(
        job_id, "COMPLETED", "",
        pdf_url=pdf_url,
        error=partial_error,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        model=model,
        cost_usd=cost_usd,
    )
    logger.info("Job %s completed, pdf_url=%s tokens=%d observed_cost=%s",
                job_id, pdf_url, prompt_tokens + completion_tokens, cost_usd)


def _consume_loop(bootstrap: str) -> None:
    state: dict = {}
    consumer = KafkaConsumer(
        "image.result",
        bootstrap_servers=bootstrap,
        group_id="pipeline-aggregator",
        auto_offset_reset="earliest",
        enable_auto_commit=True,
    )
    logger.info("Aggregator ready")
    for message in consumer:
        payload = None
        try:
            payload = json.loads(message.value.decode())
            _handle_image_result(payload, state)
        except Exception as exc:
            job_id = payload.get("job_id", "unknown") if payload else "unparseable"
            logger.error("Aggregator error on job %s: %s", job_id, exc)


def start_aggregator() -> threading.Thread:
    bootstrap = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    t = threading.Thread(target=_consume_loop, args=(bootstrap,), daemon=True, name="aggregator")
    t.start()
    return t
