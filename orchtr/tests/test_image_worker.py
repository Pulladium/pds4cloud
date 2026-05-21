import json
from unittest.mock import MagicMock, patch

import messaging.image_worker  # ensure module is registered in sys.modules before patching


def _task_payload(lid="lid1", total=2):
    return {
        "job_id": "job-1",
        "project_id": "proj-1",
        "lid": lid,
        "thumb_url": "http://t1",
        "total_images": total,
    }


def test_ensure_image_task_partitions_expands_topic_to_worker_count():
    admin = MagicMock()
    admin.create_topics.side_effect = Exception("already exists")
    with (
        patch("messaging.image_worker.KafkaAdminClient", return_value=admin),
        patch("messaging.image_worker.NewPartitions") as NewPartitions,
        patch("messaging.image_worker.NewTopic") as NewTopic,
    ):
        from messaging.image_worker import _ensure_image_task_partitions
        _ensure_image_task_partitions("localhost:9092")

    NewTopic.assert_called_once_with(name="image.task", num_partitions=6, replication_factor=1)
    NewPartitions.assert_called_once_with(total_count=6)
    admin.create_topics.assert_called_once_with([NewTopic.return_value])
    admin.create_partitions.assert_called_once_with({"image.task": NewPartitions.return_value})
    admin.close.assert_called_once()


def test_ensure_image_task_partitions_creates_topic_with_worker_count():
    admin = MagicMock()
    with (
        patch("messaging.image_worker.KafkaAdminClient", return_value=admin),
        patch("messaging.image_worker.NewPartitions"),
        patch("messaging.image_worker.NewTopic") as NewTopic,
    ):
        from messaging.image_worker import _ensure_image_task_partitions
        _ensure_image_task_partitions("localhost:9092")

    NewTopic.assert_called_once_with(name="image.task", num_partitions=6, replication_factor=1)
    admin.create_topics.assert_called_once_with([NewTopic.return_value])
    admin.create_partitions.assert_not_called()
    admin.close.assert_called_once()


def _ok_result(lid):
    return {
        "lid": lid,
        "photo_id": lid.split(":")[-1],
        "sol": "00042",
        "analysis": {"description": "Rocks and dust"},
        "status": "analyze_ok",
    }


def test_handle_image_task_publishes_ok_result_on_success():
    mock_producer = MagicMock()
    with patch("messaging.image_worker.process_product", return_value=_ok_result("lid1")):
        from messaging.image_worker import _handle_image_task
        _handle_image_task(_task_payload("lid1"), mock_producer, worker_id=3)

    result_calls = [c for c in mock_producer.send.call_args_list if c[0][0] == "image.result"]
    assert len(result_calls) == 1
    topic = result_calls[0][0][0]
    payload = json.loads(result_calls[0][1]["value"])
    assert topic == "image.result"
    assert payload["status"] == "ok"
    assert payload["lid"] == "lid1"
    assert payload["job_id"] == "job-1"
    assert payload["analysis"] == {"description": "Rocks and dust"}
    assert payload["total_images"] == 2
    mock_producer.flush.assert_called_once()


def test_handle_image_task_backfills_generated_preview_for_previewless_image():
    mock_producer = MagicMock()
    result = {
        **_ok_result("lid1"),
        "rgb_path": "transformed/mastcamz/sol=00042/lid1/rgb.jpg",
        "gray_path": "transformed/mastcamz/sol=00042/lid1/gray.jpg",
    }
    with (
        patch("messaging.image_worker.process_product", return_value=result),
        patch("messaging.image_worker.backfill_generated_preview", return_value={
            "status": "ok",
            "thumb_url": "storage:transformed/mastcamz/sol=00042/lid1/rgb.jpg",
        }) as backfill,
    ):
        from messaging.image_worker import _handle_image_task
        _handle_image_task({**_task_payload("lid1"), "thumb_url": ""}, mock_producer, worker_id=3)

    backfill.assert_called_once_with("proj-1", "lid1", result)
    result_calls = [c for c in mock_producer.send.call_args_list if c[0][0] == "image.result"]
    payload = json.loads(result_calls[0][1]["value"])
    assert payload["thumb_url"] == "storage:transformed/mastcamz/sol=00042/lid1/rgb.jpg"


def test_handle_image_task_publishes_worker_progress_start_and_done():
    mock_producer = MagicMock()
    with patch("messaging.image_worker.process_product", return_value=_ok_result("lid1")):
        from messaging.image_worker import _handle_image_task
        _handle_image_task(_task_payload("lid1"), mock_producer, worker_id=2)

    status_payloads = [
        json.loads(c[1]["value"])
        for c in mock_producer.send.call_args_list
        if c[0][0] == "job.status"
    ]
    for payload in status_payloads:
        assert payload["image_progress"].pop("event_at")

    assert status_payloads == [
        {
            "job_id": "job-1",
            "status": "PROCESSING_IMAGES",
            "image_progress": {
                "worker_id": 2,
                "lid": "lid1",
                "thumb_url": "http://t1",
                "status": "processing",
                "error": None,
            },
            "worker_count": 6,
        },
        {
            "job_id": "job-1",
            "status": "PROCESSING_IMAGES",
            "image_progress": {
                "worker_id": 2,
                "lid": "lid1",
                "thumb_url": "http://t1",
                "status": "done",
                "error": None,
            },
            "worker_count": 6,
        },
    ]


def test_handle_image_task_progress_includes_timing_and_worker_metadata():
    sent = []

    class Producer:
        def send(self, topic, value):
            sent.append((topic, json.loads(value.decode())))

        def flush(self):
            pass

    result = {
        "status": "analyze_ok",
        "analysis": {"summary": "ok"},
        "sol": 1,
        "photo_id": "p1",
        "prompt_tokens": 3,
        "completion_tokens": 4,
        "model": "gpt-4o",
        "cost_usd": 0.001,
    }

    with patch("messaging.image_worker._process_with_retry", return_value=(result, None)):
        from messaging.image_worker import _handle_image_task
        _handle_image_task(
            {
                "job_id": "job-1",
                "project_id": "proj-1",
                "lid": "lid-1",
                "thumb_url": "",
                "total_images": 1,
                "model": "gpt-4o",
                "kafka_partition": 2,
                "kafka_offset": 42,
            },
            Producer(),
            worker_id=5,
        )

    progress = [payload for topic, payload in sent if topic == "job.status"]
    assert progress[0]["image_progress"]["status"] == "processing"
    assert progress[0]["image_progress"]["worker_id"] == 5
    assert progress[0]["image_progress"]["event_at"]
    assert progress[0]["image_progress"]["kafka_partition"] == 2
    assert progress[0]["image_progress"]["kafka_offset"] == 42
    assert progress[-1]["image_progress"]["status"] == "done"
    assert progress[-1]["image_progress"]["worker_id"] == 5
    assert progress[-1]["image_progress"]["event_at"]
    assert progress[-1]["image_progress"]["kafka_partition"] == 2
    assert progress[-1]["image_progress"]["kafka_offset"] == 42


def test_handle_image_task_publishes_worker_progress_error():
    mock_producer = MagicMock()
    with (
        patch("messaging.image_worker.process_product", side_effect=Exception("timeout")),
        patch("messaging.image_worker.time.sleep"),
    ):
        from messaging.image_worker import _handle_image_task
        _handle_image_task(_task_payload("lid1"), mock_producer, worker_id=1)

    status_payloads = [
        json.loads(c[1]["value"])
        for c in mock_producer.send.call_args_list
        if c[0][0] == "job.status"
    ]

    assert status_payloads[-1]["image_progress"].pop("event_at")
    assert status_payloads[-1]["image_progress"] == {
        "worker_id": 1,
        "lid": "lid1",
        "thumb_url": "http://t1",
        "status": "error",
        "error": "timeout",
    }


def test_handle_image_task_reports_analyze_error_instead_of_missing_analysis():
    mock_producer = MagicMock()
    result = {
        "lid": "lid1",
        "photo_id": "lid1",
        "sol": "00042",
        "analysis": {},
        "status": "analyze_error",
        "error": "Unsupported parameter: max_tokens",
    }
    with (
        patch("messaging.image_worker.process_product", return_value=result) as process_product,
        patch("messaging.image_worker.time.sleep") as sleep,
    ):
        from messaging.image_worker import _handle_image_task
        _handle_image_task(_task_payload("lid1"), mock_producer, worker_id=1)

    status_payloads = [
        json.loads(c[1]["value"])
        for c in mock_producer.send.call_args_list
        if c[0][0] == "job.status"
    ]
    result_calls = [c for c in mock_producer.send.call_args_list if c[0][0] == "image.result"]
    result_payload = json.loads(result_calls[0][1]["value"])

    assert status_payloads[-1]["image_progress"]["status"] == "error"
    assert status_payloads[-1]["image_progress"]["error"] == "pipeline error: Unsupported parameter: max_tokens"
    assert result_payload["status"] == "error"
    assert result_payload["error"] == "pipeline error: Unsupported parameter: max_tokens"
    process_product.assert_called_once()
    sleep.assert_not_called()


def test_handle_image_task_allows_empty_analysis_dict_for_non_error_status():
    mock_producer = MagicMock()
    result = {
        "lid": "lid1",
        "photo_id": "lid1",
        "sol": "00042",
        "analysis": {},
        "status": "analyze_skipped",
    }
    with patch("messaging.image_worker.process_product", return_value=result):
        from messaging.image_worker import _handle_image_task
        _handle_image_task(_task_payload("lid1"), mock_producer, worker_id=1)

    status_payloads = [
        json.loads(c[1]["value"])
        for c in mock_producer.send.call_args_list
        if c[0][0] == "job.status"
    ]
    result_calls = [c for c in mock_producer.send.call_args_list if c[0][0] == "image.result"]
    result_payload = json.loads(result_calls[0][1]["value"])

    assert status_payloads[-1]["image_progress"]["status"] == "done"
    assert result_payload["status"] == "ok"
    assert result_payload["analysis"] == {}


def test_handle_image_task_treats_missing_analysis_as_error_progress():
    mock_producer = MagicMock()
    bad_result = {
        "lid": "lid1",
        "photo_id": "lid1",
        "sol": "00042",
        "analysis": None,
        "status": "analyze_ok",
    }
    with (
        patch("messaging.image_worker.process_product", return_value=bad_result),
        patch("messaging.image_worker.time.sleep"),
    ):
        from messaging.image_worker import _handle_image_task
        _handle_image_task(_task_payload("lid1"), mock_producer, worker_id=1)

    status_payloads = [
        json.loads(c[1]["value"])
        for c in mock_producer.send.call_args_list
        if c[0][0] == "job.status"
    ]
    result_calls = [c for c in mock_producer.send.call_args_list if c[0][0] == "image.result"]
    result_payload = json.loads(result_calls[0][1]["value"])

    assert status_payloads[-1]["image_progress"]["status"] == "error"
    assert all(payload["image_progress"]["status"] != "done" for payload in status_payloads)
    assert "missing analysis" in status_payloads[-1]["image_progress"]["error"]
    assert result_payload["status"] == "error"
    assert "missing analysis" in result_payload["error"]


def test_handle_image_task_passes_job_metadata_to_pipeline():
    mock_producer = MagicMock()
    with patch("messaging.image_worker.process_product", return_value=_ok_result("lid1")) as process_product:
        from messaging.image_worker import _handle_image_task
        _handle_image_task(_task_payload("lid1"), mock_producer, worker_id=0)

    process_product.assert_called_once_with(
        "lid1",
        model="gpt-4o",
        job_id="job-1",
        project_id="proj-1",
        user_id="",
    )


def test_handle_image_task_passes_user_and_publishes_analysis_id():
    mock_producer = MagicMock()
    result = {
        **_ok_result("lid1"),
        "analysis_id": "analysis-1",
        "result_path": "analysis/mastcamz/sol=00042/lid1/analysis-1/result.json",
    }
    task = {**_task_payload("lid1"), "user_id": "user-1"}
    with patch("messaging.image_worker.process_product", return_value=result) as process_product:
        from messaging.image_worker import _handle_image_task
        _handle_image_task(task, mock_producer, worker_id=0)

    process_product.assert_called_once_with(
        "lid1",
        model="gpt-4o",
        job_id="job-1",
        project_id="proj-1",
        user_id="user-1",
    )
    payload = json.loads([c for c in mock_producer.send.call_args_list if c[0][0] == "image.result"][0][1]["value"])
    assert payload["analysis_id"] == "analysis-1"
    assert payload["result_path"] == "analysis/mastcamz/sol=00042/lid1/analysis-1/result.json"


def test_handle_image_task_publishes_error_result_after_all_retries_fail():
    mock_producer = MagicMock()
    with (
        patch("messaging.image_worker.process_product", side_effect=Exception("timeout")),
        patch("messaging.image_worker.time.sleep"),
    ):
        from messaging.image_worker import _handle_image_task
        _handle_image_task(_task_payload("lid1"), mock_producer, worker_id=0)

    result_calls = [c for c in mock_producer.send.call_args_list if c[0][0] == "image.result"]
    payload = json.loads(result_calls[0][1]["value"])
    assert payload["status"] == "error"
    assert "timeout" in payload["error"]
    mock_producer.flush.assert_called_once()


def test_handle_image_task_retries_twice_before_giving_up():
    call_count = {"n": 0}

    def flaky(lid, model="gpt-4o", job_id=None, project_id=None, user_id=""):
        call_count["n"] += 1
        if call_count["n"] <= 2:
            raise Exception("network error")
        return _ok_result(lid)

    mock_producer = MagicMock()
    with (
        patch("messaging.image_worker.process_product", side_effect=flaky),
        patch("messaging.image_worker.time.sleep"),
    ):
        from messaging.image_worker import _handle_image_task
        _handle_image_task(_task_payload("lid1"), mock_producer, worker_id=0)

    assert call_count["n"] == 3
    result_calls = [c for c in mock_producer.send.call_args_list if c[0][0] == "image.result"]
    payload = json.loads(result_calls[0][1]["value"])
    assert payload["status"] == "ok"


def test_process_with_retry_recovers_after_eval_fault(monkeypatch):
    from messaging.image_worker import _process_with_retry

    class Registry:
        def __init__(self):
            self.calls = 0

        def should_fail(self, stage, job_id, lid):
            assert stage == "image_worker_process"
            self.calls += 1
            if self.calls == 1:
                return {"fault_id": "f-analyze", "stage": stage, "job_id": job_id, "lid": lid}
            return None

    monkeypatch.setattr("messaging.image_worker.get_eval_fault_registry", lambda: Registry())
    monkeypatch.setattr("messaging.image_worker.time.sleep", lambda _delay: None)
    monkeypatch.setattr("messaging.image_worker.process_product", lambda *args, **kwargs: {
        "status": "ok",
        "analysis": {"summary": "ok"},
    })

    result, exc = _process_with_retry("lid-1", job_id="job-1")

    assert exc is None
    assert result["analysis"] == {"summary": "ok"}


def test_publish_image_progress_can_inject_duplicate_job_status(monkeypatch, caplog):
    from messaging import image_worker

    class Registry:
        def should_duplicate(self, stage, job_id, lid=None):
            if stage == "duplicate_job_status":
                return {
                    "fault_id": "dup-status",
                    "stage": stage,
                    "job_id": job_id,
                    "lid": lid,
                    "attempt": 1,
                    "duplicates": 1,
                }
            return None

    producer = MagicMock()
    monkeypatch.setattr(image_worker, "get_eval_fault_registry", lambda: Registry())

    with caplog.at_level("WARNING", logger="messaging.image_worker"):
        image_worker._publish_image_progress(producer, "job-1", "lid-1", "thumb", 4, "done")

    assert producer.send.call_count == 2
    assert "EVAL_FAULT injected" in caplog.text
    assert '"stage": "duplicate_job_status"' in caplog.text


def _ok_result_with_tokens(lid, prompt_tokens=150, completion_tokens=75):
    return {
        "lid": lid,
        "photo_id": lid.split(":")[-1],
        "sol": "00042",
        "analysis": {"description": "Rocks"},
        "status": "analyze_ok",
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "model": "gpt-4o",
        "cost_usd": None,
    }


def test_image_result_payload_includes_token_fields_on_success():
    mock_producer = MagicMock()
    with patch("messaging.image_worker.process_product", return_value=_ok_result_with_tokens("lid1", 150, 75)):
        from messaging.image_worker import _handle_image_task
        _handle_image_task(_task_payload("lid1"), mock_producer, worker_id=0)

    result_calls = [c for c in mock_producer.send.call_args_list if c[0][0] == "image.result"]
    payload = json.loads(result_calls[0][1]["value"])
    assert payload["prompt_tokens"] == 150
    assert payload["completion_tokens"] == 75
    assert payload["model"] == "gpt-4o"
    assert payload["cost_usd"] is None


def test_image_result_payload_has_zero_tokens_on_failure():
    mock_producer = MagicMock()
    with (
        patch("messaging.image_worker.process_product", side_effect=Exception("timeout")),
        patch("messaging.image_worker.time.sleep"),
    ):
        from messaging.image_worker import _handle_image_task
        _handle_image_task(_task_payload("lid1"), mock_producer, worker_id=0)

    result_calls = [c for c in mock_producer.send.call_args_list if c[0][0] == "image.result"]
    payload = json.loads(result_calls[0][1]["value"])
    assert payload["prompt_tokens"] == 0
    assert payload["completion_tokens"] == 0
    assert payload["model"] is None
    assert payload["cost_usd"] is None
