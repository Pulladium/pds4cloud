import json
import logging
import os
import threading
import time

from kafka import KafkaConsumer, KafkaProducer as _KafkaProducer

from messaging.producer import publish_status
from utils.eval_faults import get_eval_fault_registry
from utils.retry import retry_call

logger = logging.getLogger(__name__)


def _handle_job_submitted(payload: dict, producer) -> None:
    job_id = payload["job_id"]
    project_id = payload.get("project_id", "")
    user_id = payload.get("user_id", "")
    images = payload.get("images", [])
    model = payload.get("model", "gpt-4o")
    n = len(images)

    if not images:
        publish_status(job_id, "FAILED", "", error="No images to process")
        return

    publish_status(job_id, "PROCESSING_IMAGES", f"0/{n}")

    for img in images:
        task = {
            "job_id": job_id,
            "project_id": project_id,
            "user_id": user_id,
            "lid": img["lid"],
            "thumb_url": img.get("thumb_url", ""),
            "total_images": n,
            "model": model,
        }
        encoded = json.dumps(task).encode()
        fault_registry = get_eval_fault_registry()

        def _publish_image_task():
            fault = fault_registry.should_fail("image_task_publish", job_id, img["lid"])
            if fault:
                logger.warning("EVAL_FAULT injected %s", json.dumps(fault, sort_keys=True))
                raise TimeoutError(f"eval fault injected: {fault['fault_id']}")
            producer.send("image.task", value=encoded)
            producer.flush()

        retry_call(
            _publish_image_task,
            attempts=3,
            delays=(0.0, 2.0),
            sleep_fn=time.sleep,
            on_retry=lambda attempt, exc, delay: logger.warning(
                "image.task publish attempt %d failed for job %s lid %s (%s), retry in %.0fs",
                attempt,
                job_id,
                img["lid"],
                exc,
                delay,
            ),
        )
    logger.info("Dispatched %d image tasks for job %s (model=%s)", n, job_id, model)


def _consume_loop(bootstrap: str) -> None:
    producer = _KafkaProducer(bootstrap_servers=bootstrap)
    consumer = KafkaConsumer(
        "job.submitted",
        bootstrap_servers=bootstrap,
        group_id="pipeline-dispatcher",
        auto_offset_reset="earliest",
    )
    for message in consumer:
        try:
            payload = json.loads(message.value.decode())
            _handle_job_submitted(payload, producer)
        except Exception as exc:
            logger.error("dispatcher error on message: %s", exc)


def start_dispatcher() -> threading.Thread:
    bootstrap = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    t = threading.Thread(target=_consume_loop, args=(bootstrap,), daemon=True, name="dispatcher")
    t.start()
    return t
