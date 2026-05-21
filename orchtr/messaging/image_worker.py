import json
import logging
import os
import threading
import time
from datetime import datetime, timezone

from kafka import KafkaConsumer, KafkaProducer as _KafkaProducer

from graph_single import process_product
from services.project_preview import backfill_generated_preview
from utils.eval_faults import get_eval_fault_registry

logger = logging.getLogger(__name__)

_MAX_WORKERS = 6
_MAX_RETRIES = 2
_IMAGE_TASK_TOPIC = "image.task"
KafkaAdminClient = None
NewPartitions = None
NewTopic = None


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _publish_image_progress(
    producer,
    job_id: str,
    lid: str,
    thumb_url: str,
    worker_id: int,
    status: str,
    error: str | None = None,
    metadata_loaded: bool = False,
    metadata_summary: dict | None = None,
    array_summary: dict | None = None,
    kafka_partition: int | None = None,
    kafka_offset: int | None = None,
) -> None:
    image_progress = {
        "worker_id": worker_id,
        "lid": lid,
        "thumb_url": thumb_url,
        "status": status,
        "error": error,
        "event_at": _utc_now_iso(),
    }
    if kafka_partition is not None:
        image_progress["kafka_partition"] = kafka_partition
    if kafka_offset is not None:
        image_progress["kafka_offset"] = kafka_offset
    if metadata_loaded:
        image_progress["metadata_loaded"] = True
    if metadata_summary:
        image_progress["metadata_summary"] = metadata_summary
    if array_summary:
        image_progress["array_summary"] = array_summary

    payload = {
        "job_id": job_id,
        "status": "PROCESSING_IMAGES",
        "image_progress": image_progress,
        "worker_count": _MAX_WORKERS,
    }
    encoded = json.dumps(payload).encode()
    producer.send("job.status", value=encoded)

    registry = get_eval_fault_registry()
    should_duplicate = getattr(registry, "should_duplicate", None)
    fault = should_duplicate("duplicate_job_status", job_id, lid) if should_duplicate else None
    if fault:
        logger.warning("EVAL_FAULT injected %s", json.dumps(fault, sort_keys=True))
        producer.send("job.status", value=encoded)


def _ensure_image_task_partitions(bootstrap: str) -> None:
    global KafkaAdminClient, NewPartitions, NewTopic
    admin = None
    try:
        if KafkaAdminClient is None or NewPartitions is None or NewTopic is None:
            from kafka.admin import KafkaAdminClient as _KafkaAdminClient, NewPartitions as _NewPartitions, NewTopic as _NewTopic
            KafkaAdminClient = _KafkaAdminClient
            NewPartitions = _NewPartitions
            NewTopic = _NewTopic
        admin = KafkaAdminClient(bootstrap_servers=bootstrap)
        try:
            admin.create_topics([
                NewTopic(name=_IMAGE_TASK_TOPIC, num_partitions=_MAX_WORKERS, replication_factor=1),
            ])
        except Exception:
            admin.create_partitions({
                _IMAGE_TASK_TOPIC: NewPartitions(total_count=_MAX_WORKERS),
            })
        logger.info("Ensured %s can use %d worker partitions", _IMAGE_TASK_TOPIC, _MAX_WORKERS)
    except Exception as exc:
        logger.info("Could not expand %s partitions: %s", _IMAGE_TASK_TOPIC, exc)
    finally:
        if admin is not None:
            admin.close()


def _process_with_retry(
    lid: str,
    model: str = "gpt-4o",
    job_id: str | None = None,
    project_id: str | None = None,
    user_id: str = "",
) -> tuple[dict, Exception | None]:
    last_exc = None
    eval_faults = get_eval_fault_registry()
    for attempt in range(_MAX_RETRIES + 1):
        try:
            fault = eval_faults.should_fail("image_worker_process", job_id or "", lid)
            if fault:
                logger.warning("EVAL_FAULT injected %s", json.dumps(fault))
                raise TimeoutError(f"eval fault injected: {fault['fault_id']}")
            result = process_product(lid, model=model, job_id=job_id, project_id=project_id, user_id=user_id)
            status = result.get("status", "")
            if status.startswith("error") or status.endswith("_error"):
                return {}, RuntimeError(f"pipeline error: {result.get('error') or status}")
            if result.get("analysis") is None:
                raise RuntimeError("pipeline error: missing analysis")
            return result, None
        except Exception as exc:
            last_exc = exc
            if attempt < _MAX_RETRIES:
                wait = 2 ** attempt
                logger.warning("image %s attempt %d failed (%s), retry in %ds", lid, attempt + 1, exc, wait)
                time.sleep(wait)
    return {}, last_exc


def _handle_image_task(payload: dict, producer, worker_id: int) -> None:
    job_id = payload["job_id"]
    lid = payload["lid"]
    total = payload.get("total_images", 1)
    project_id = payload.get("project_id", "")
    user_id = payload.get("user_id", "")
    thumb_url = payload.get("thumb_url", "")
    model = payload.get("model", "gpt-4o")
    kafka_partition = payload.get("kafka_partition")
    kafka_offset = payload.get("kafka_offset")

    _publish_image_progress(
        producer,
        job_id,
        lid,
        thumb_url,
        worker_id,
        "processing",
        kafka_partition=kafka_partition,
        kafka_offset=kafka_offset,
    )
    result, exc = _process_with_retry(lid, model=model, job_id=job_id, project_id=project_id, user_id=user_id)

    out: dict = {
        "job_id": job_id,
        "project_id": project_id,
        "lid": lid,
        "thumb_url": thumb_url,
        "total_images": total,
    }

    if exc is None:
        analysis = result.get("analysis", {}) or {}
        generated_preview = {}
        if not thumb_url:
            try:
                generated_preview = backfill_generated_preview(project_id, lid, result)
                thumb_url = generated_preview.get("thumb_url") or thumb_url
            except Exception as preview_exc:
                logger.warning("Generated preview backfill failed job=%s lid=%s: %s", job_id, lid, preview_exc)
        out.update({
            "status":            "ok",
            "analysis":          result.get("analysis"),
            "sol":               result.get("sol"),
            "photo_id":          result.get("photo_id"),
            "prompt_tokens":     result.get("prompt_tokens", 0) or 0,
            "completion_tokens": result.get("completion_tokens", 0) or 0,
            "model":             result.get("model"),
            "cost_usd":          result.get("cost_usd"),
            "analysis_id":       result.get("analysis_id"),
            "result_path":       result.get("result_path"),
            "error":             None,
            "generated_preview":  generated_preview or None,
            "metadata_loaded":   bool(analysis.get("metadata_loaded")),
            "metadata_summary":  analysis.get("metadata_summary", {}),
            "array_summary":     analysis.get("array_summary", {}),
        })
        out["thumb_url"] = thumb_url
        _publish_image_progress(
            producer,
            job_id,
            lid,
            thumb_url,
            worker_id,
            "done",
            error=None,
            metadata_loaded=bool(analysis.get("metadata_loaded")),
            metadata_summary=analysis.get("metadata_summary", {}),
            array_summary=analysis.get("array_summary", {}),
            kafka_partition=kafka_partition,
            kafka_offset=kafka_offset,
        )
    else:
        out.update({
            "status":            "error",
            "analysis":          None,
            "sol":               None,
            "photo_id":          None,
            "prompt_tokens":     0,
            "completion_tokens": 0,
            "model":             None,
            "cost_usd":          None,
            "error":             str(exc),
        })
        _publish_image_progress(
            producer,
            job_id,
            lid,
            thumb_url,
            worker_id,
            "error",
            str(exc),
            kafka_partition=kafka_partition,
            kafka_offset=kafka_offset,
        )

    producer.send("image.result", value=json.dumps(out).encode())
    producer.flush()
    logger.info("Published image.result job=%s lid=%s status=%s", job_id, lid, out["status"])


def _worker_loop(bootstrap: str, worker_id: int) -> None:
    producer = _KafkaProducer(bootstrap_servers=bootstrap)
    consumer = KafkaConsumer(
        _IMAGE_TASK_TOPIC,
        bootstrap_servers=bootstrap,
        group_id="pipeline-image-workers",
        auto_offset_reset="earliest",
        enable_auto_commit=False,
    )
    logger.info("Image worker %d ready", worker_id)
    for message in consumer:
        try:
            payload = json.loads(message.value.decode())
            payload["kafka_partition"] = message.partition
            payload["kafka_offset"] = message.offset
            _handle_image_task(payload, producer, worker_id)
            consumer.commit()
        except Exception as exc:
            logger.error("Worker %d unhandled error on %s: %s", worker_id, message.value[:80], exc)


def start_workers() -> list[threading.Thread]:
    bootstrap = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    _ensure_image_task_partitions(bootstrap)
    threads = []
    for i in range(_MAX_WORKERS):
        t = threading.Thread(
            target=_worker_loop, args=(bootstrap, i),
            daemon=True, name=f"image-worker-{i}"
        )
        t.start()
        threads.append(t)
    logger.info("Started %d image worker threads", _MAX_WORKERS)
    return threads
