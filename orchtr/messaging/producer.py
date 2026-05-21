import json
import logging
import os
import threading
import time

from kafka import KafkaProducer as _KafkaProducer
from utils.eval_faults import get_eval_fault_registry
from utils.retry import retry_call

logger = logging.getLogger(__name__)

_producer = None
_lock = threading.Lock()


def _get_producer():
    global _producer
    if _producer is None:
        with _lock:
            if _producer is None:
                _producer = _KafkaProducer(
                    bootstrap_servers=os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"),
                )
    return _producer


def publish_status(
    job_id: str,
    status: str,
    stage_info: str,
    pdf_url: str | None = None,
    error: str | None = None,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    model: str | None = None,
    cost_usd: float | None = None,
) -> None:
    payload = {
        "job_id":            job_id,
        "status":            status,
        "stage_info":        stage_info,
        "pdf_url":           pdf_url,
        "error":             error,
        "prompt_tokens":     prompt_tokens,
        "completion_tokens": completion_tokens,
        "model":             model,
        "cost_usd":          cost_usd,
    }
    try:
        encoded = json.dumps(payload).encode()
        fault_registry = get_eval_fault_registry()

        def _publish_status():
            fault = fault_registry.should_fail("job_status_publish", job_id)
            if fault:
                logger.warning("EVAL_FAULT injected %s", json.dumps(fault, sort_keys=True))
                raise TimeoutError(f"eval fault injected: {fault['fault_id']}")
            producer = _get_producer()
            producer.send("job.status", value=encoded)
            producer.flush()
            should_duplicate = getattr(fault_registry, "should_duplicate", None)
            duplicate = (
                should_duplicate("late_terminal_status", job_id)
                if status == "COMPLETED" and should_duplicate
                else None
            )
            if duplicate:
                logger.warning("EVAL_FAULT injected %s", json.dumps(duplicate, sort_keys=True))
                producer.send("job.status", value=encoded)
                producer.flush()

        retry_call(
            _publish_status,
            attempts=3,
            delays=(0.0, 2.0),
            sleep_fn=time.sleep,
            on_retry=lambda attempt, exc, delay: logger.warning(
                "publish_status attempt %d failed for job %s (%s), retry in %.0fs",
                attempt,
                job_id,
                exc,
                delay,
            ),
        )
    except Exception as exc:
        logger.warning("publish_status failed (fire-and-forget): %s", exc)
