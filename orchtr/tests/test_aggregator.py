import logging
from unittest.mock import MagicMock, patch


def _result(job_id="job-1", lid="lid1", total=2, status="ok"):
    return {
        "job_id": job_id,
        "project_id": "proj-1",
        "lid": lid,
        "thumb_url": "http://t",
        "total_images": total,
        "status": status,
        "analysis": {"description": "Rocks"} if status == "ok" else None,
        "sol": "00042" if status == "ok" else None,
        "photo_id": lid if status == "ok" else None,
        "error": None if status == "ok" else "failed",
    }


def _result_with_analysis_id(lid="lid1", total=1):
    r = _result(lid=lid, total=total)
    r["analysis_id"] = f"analysis-{lid}"
    r["result_path"] = f"analysis/mastcamz/sol=00042/{lid}/analysis-{lid}/result.json"
    return r


def test_aggregate_does_not_trigger_pdf_until_all_results_received():
    state = {}
    with patch("messaging.aggregator.generate_pdf_bytes") as mock_pdf:
        from messaging.aggregator import _handle_image_result
        _handle_image_result(_result(lid="lid1", total=2), state)
        mock_pdf.assert_not_called()


def test_aggregate_triggers_pdf_when_all_results_received():
    state = {}
    with (
        patch("messaging.aggregator.generate_pdf_bytes", return_value=b"%PDF"),
        patch("messaging.aggregator.upload_pdf", return_value="http://minio/r.pdf"),
        patch("messaging.aggregator.publish_status") as mock_status,
    ):
        from messaging.aggregator import _handle_image_result
        _handle_image_result(_result(lid="lid1", total=2), state)
        _handle_image_result(_result(lid="lid2", total=2), state)

    call = mock_status.call_args_list[-1]  # last call is COMPLETED
    assert call[0][1] == "COMPLETED"
    assert call[1]["pdf_url"] == "http://minio/r.pdf"
    assert "job-1" not in state  # cleaned up after completion


def test_aggregate_marks_artifacts_in_report_then_evictable_after_pdf_upload():
    state = {}
    events = []

    def record(event, return_value=None):
        def side_effect(*_, **__):
            events.append(event)
            return return_value
        return side_effect

    with (
        patch("messaging.aggregator.generate_pdf_bytes", side_effect=record("generate_pdf_bytes", b"%PDF")),
        patch("messaging.aggregator.upload_pdf", side_effect=record("upload_pdf", "http://minio/r.pdf")),
        patch("messaging.aggregator.publish_status"),
        patch("messaging.aggregator.SessionLocal") as SessionLocal,
        patch("messaging.aggregator.mark_in_report", side_effect=record("mark_in_report")) as mark_in_report,
        patch(
            "messaging.aggregator.mark_evictable_and_prune",
            side_effect=record("mark_evictable_and_prune"),
        ) as mark_evictable,
        patch("messaging.aggregator.get_storage_adapter", return_value=MagicMock()) as get_storage,
    ):
        db = MagicMock()
        SessionLocal.return_value = db
        from messaging.aggregator import _handle_image_result
        _handle_image_result(_result_with_analysis_id(), state)

    assert events == [
        "mark_in_report",
        "generate_pdf_bytes",
        "upload_pdf",
        "mark_evictable_and_prune",
    ]
    mark_in_report.assert_called_once_with(db, ["analysis-lid1"])
    mark_evictable.assert_called_once_with(db, ["analysis-lid1"], storage=get_storage.return_value)
    db.close.assert_called_once()


def test_aggregate_releases_artifacts_to_ready_when_pdf_generation_fails():
    state = {}
    with (
        patch("messaging.aggregator.generate_pdf_bytes", side_effect=RuntimeError("pdf failed")),
        patch("messaging.aggregator.publish_status"),
        patch("messaging.aggregator.SessionLocal") as SessionLocal,
        patch("messaging.aggregator.mark_in_report"),
        patch("messaging.aggregator.release_to_ready") as release_to_ready,
    ):
        db = MagicMock()
        SessionLocal.return_value = db
        from messaging.aggregator import _handle_image_result
        _handle_image_result(_result_with_analysis_id(), state)

    release_to_ready.assert_called_once_with(db, ["analysis-lid1"])


def test_aggregate_publishes_failed_when_session_creation_fails():
    state = {}
    captured = {}

    def fake_publish(job_id, status, stage_info, **kwargs):
        if status == "FAILED":
            captured.update(kwargs)

    with (
        patch("messaging.aggregator.publish_status", side_effect=fake_publish),
        patch("messaging.aggregator.SessionLocal", side_effect=RuntimeError("db down")),
    ):
        from messaging.aggregator import _handle_image_result
        _handle_image_result(_result_with_analysis_id(), state)

    assert "db down" in captured["error"]


def test_aggregate_releases_artifacts_to_ready_when_pdf_upload_fails():
    state = {}
    captured = {}

    def fake_publish(job_id, status, stage_info, **kwargs):
        if status == "FAILED":
            captured.update(kwargs)

    with (
        patch("messaging.aggregator.generate_pdf_bytes", return_value=b"%PDF"),
        patch("messaging.aggregator.upload_pdf", side_effect=RuntimeError("upload failed")),
        patch("messaging.aggregator.publish_status", side_effect=fake_publish),
        patch("messaging.aggregator.SessionLocal") as SessionLocal,
        patch("messaging.aggregator.mark_in_report"),
        patch("messaging.aggregator.release_to_ready") as release_to_ready,
        patch("messaging.aggregator.time.sleep"),
    ):
        db = MagicMock()
        SessionLocal.return_value = db
        from messaging.aggregator import _handle_image_result
        _handle_image_result(_result_with_analysis_id(), state)

    release_to_ready.assert_called_once_with(db, ["analysis-lid1"])
    assert "upload failed" in captured["error"]


def test_aggregate_failed_status_includes_release_error_when_pdf_generation_and_release_fail():
    state = {}
    captured = {}

    def fake_publish(job_id, status, stage_info, **kwargs):
        if status == "FAILED":
            captured.update(kwargs)

    with (
        patch("messaging.aggregator.generate_pdf_bytes", side_effect=RuntimeError("pdf failed")),
        patch("messaging.aggregator.publish_status", side_effect=fake_publish),
        patch("messaging.aggregator.SessionLocal") as SessionLocal,
        patch("messaging.aggregator.mark_in_report"),
        patch("messaging.aggregator.release_to_ready", side_effect=RuntimeError("release failed")),
        patch("messaging.aggregator.time.sleep"),
    ):
        db = MagicMock()
        SessionLocal.return_value = db
        from messaging.aggregator import _handle_image_result
        _handle_image_result(_result_with_analysis_id(), state)

    assert "pdf failed" in captured["error"]
    assert "release failed" in captured["error"]


def test_aggregate_without_analysis_id_skips_lifecycle_and_still_uploads_pdf():
    state = {}
    with (
        patch("messaging.aggregator.generate_pdf_bytes", return_value=b"%PDF") as generate_pdf,
        patch("messaging.aggregator.upload_pdf", return_value="http://minio/r.pdf") as upload_pdf,
        patch("messaging.aggregator.publish_status"),
        patch("messaging.aggregator.SessionLocal") as SessionLocal,
        patch("messaging.aggregator.mark_in_report") as mark_in_report,
        patch("messaging.aggregator.mark_evictable_and_prune") as mark_evictable,
    ):
        from messaging.aggregator import _handle_image_result
        _handle_image_result(_result(total=1), state)

    generate_pdf.assert_called_once()
    upload_pdf.assert_called_once()
    SessionLocal.assert_not_called()
    mark_in_report.assert_not_called()
    mark_evictable.assert_not_called()


def test_aggregate_all_images_failed_skips_lifecycle_session():
    state = {}
    with (
        patch("messaging.aggregator.publish_status"),
        patch("messaging.aggregator.SessionLocal") as SessionLocal,
    ):
        from messaging.aggregator import _handle_image_result
        _handle_image_result(_result(lid="lid1", total=2, status="error"), state)
        _handle_image_result(_result(lid="lid2", total=2, status="error"), state)

    SessionLocal.assert_not_called()


def test_aggregate_partial_success_completes_with_error_message():
    state = {}
    captured = {}

    def fake_publish(job_id, status, stage_info, **kwargs):
        if status == "COMPLETED":
            captured.update(kwargs)

    with (
        patch("messaging.aggregator.generate_pdf_bytes", return_value=b"%PDF"),
        patch("messaging.aggregator.upload_pdf", return_value="http://minio/r.pdf"),
        patch("messaging.aggregator.publish_status", side_effect=fake_publish),
        patch("messaging.aggregator._fetch_langsmith_job_cost", return_value=None),
    ):
        from messaging.aggregator import _handle_image_result
        _handle_image_result(_result(lid="lid1", total=2), state)
        _handle_image_result(_result(lid="lid2", total=2, status="error"), state)

    assert captured["pdf_url"] == "http://minio/r.pdf"
    assert "1 image(s) failed" in captured["error"]
    assert "lid2" in captured["error"]


def test_aggregate_publishes_failed_when_all_images_failed():
    state = {}
    with patch("messaging.aggregator.publish_status") as mock_status:
        from messaging.aggregator import _handle_image_result
        _handle_image_result(_result(lid="lid1", total=2, status="error"), state)
        _handle_image_result(_result(lid="lid2", total=2, status="error"), state)

    last_call = mock_status.call_args
    assert last_call[0][1] == "FAILED"
    assert "job-1" not in state


def test_aggregate_publishes_progress_on_each_result():
    state = {}
    statuses = []

    def fake_publish(job_id, status, stage_info, **_):
        statuses.append((status, stage_info))

    with (
        patch("messaging.aggregator.generate_pdf_bytes", return_value=b"%PDF"),
        patch("messaging.aggregator.upload_pdf", return_value="http://minio/r.pdf"),
        patch("messaging.aggregator.publish_status", side_effect=fake_publish),
    ):
        from messaging.aggregator import _handle_image_result
        _handle_image_result(_result(lid="lid1", total=2), state)
        _handle_image_result(_result(lid="lid2", total=2), state)

    progress = [(s, i) for s, i in statuses if s == "PROCESSING_IMAGES"]
    assert ("PROCESSING_IMAGES", "1/2") in progress
    assert ("PROCESSING_IMAGES", "2/2") in progress


def _result_with_tokens(job_id="job-1", lid="lid1", total=2, status="ok",
                         prompt_tokens=100, completion_tokens=50, cost_usd=None):
    base = _result(job_id=job_id, lid=lid, total=total, status=status)
    if status == "ok":
        base.update({
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "model": "gpt-4o",
            "cost_usd": cost_usd,
        })
    else:
        base.update({"prompt_tokens": 0, "completion_tokens": 0, "model": None, "cost_usd": None})
    return base


def test_aggregate_sums_tokens_from_all_succeeded_images():
    state = {}
    captured = {}

    def fake_publish(job_id, status, stage_info, **kwargs):
        if status == "COMPLETED":
            captured.update(kwargs)

    with (
        patch("messaging.aggregator.generate_pdf_bytes", return_value=b"%PDF"),
        patch("messaging.aggregator.upload_pdf", return_value="http://minio/r.pdf"),
        patch("messaging.aggregator.publish_status", side_effect=fake_publish),
    ):
        from messaging.aggregator import _handle_image_result
        _handle_image_result(_result_with_tokens(lid="lid1", total=2, prompt_tokens=100, completion_tokens=50), state)
        _handle_image_result(_result_with_tokens(lid="lid2", total=2, prompt_tokens=200, completion_tokens=80), state)

    assert captured["prompt_tokens"] == 300
    assert captured["completion_tokens"] == 130
    assert captured["model"] == "gpt-4o"
    assert captured["cost_usd"] is None


def test_aggregate_sums_observed_cost_when_available():
    state = {}
    captured = {}

    def fake_publish(job_id, status, stage_info, **kwargs):
        if status == "COMPLETED":
            captured.update(kwargs)

    with (
        patch("messaging.aggregator.generate_pdf_bytes", return_value=b"%PDF"),
        patch("messaging.aggregator.upload_pdf", return_value="http://minio/r.pdf"),
        patch("messaging.aggregator.publish_status", side_effect=fake_publish),
    ):
        from messaging.aggregator import _handle_image_result
        _handle_image_result(_result_with_tokens(lid="lid1", total=2, cost_usd=0.01), state)
        _handle_image_result(_result_with_tokens(lid="lid2", total=2, cost_usd=0.02), state)

    assert abs(captured["cost_usd"] - 0.03) < 1e-9


def test_fetch_langsmith_job_cost_sums_llm_run_costs():
    from decimal import Decimal
    from messaging.aggregator import _fetch_langsmith_job_cost

    run1 = MagicMock()
    run1.total_cost = Decimal("0.01")
    run2 = MagicMock()
    run2.total_cost = Decimal("0.02")

    client = MagicMock()
    client.list_runs.return_value = [run1, run2]

    with patch("messaging.aggregator._langsmith_client", return_value=client):
        cost = _fetch_langsmith_job_cost("job-1", attempts=1, sleep_s=0)

    assert abs(cost - 0.03) < 1e-9
    kwargs = client.list_runs.call_args.kwargs
    assert kwargs["run_type"] == "llm"
    assert kwargs["limit"] == 100
    assert "job:job-1" in kwargs["filter"]


def test_aggregate_uses_langsmith_job_cost_when_available():
    state = {}
    captured = {}

    def fake_publish(job_id, status, stage_info, **kwargs):
        if status == "COMPLETED":
            captured.update(kwargs)

    with (
        patch("messaging.aggregator.generate_pdf_bytes", return_value=b"%PDF"),
        patch("messaging.aggregator.upload_pdf", return_value="http://minio/r.pdf"),
        patch("messaging.aggregator.publish_status", side_effect=fake_publish),
        patch("messaging.aggregator._fetch_langsmith_job_cost", return_value=0.04),
    ):
        from messaging.aggregator import _handle_image_result
        _handle_image_result(_result_with_tokens(lid="lid1", total=1, cost_usd=None), state)

    assert captured["cost_usd"] == 0.04


def test_aggregate_tokens_zero_when_all_failed():
    state = {}
    captured = {}

    def fake_publish(job_id, status, stage_info, **kwargs):
        if status == "FAILED":
            captured.update(kwargs)

    with patch("messaging.aggregator.publish_status", side_effect=fake_publish):
        from messaging.aggregator import _handle_image_result
        _handle_image_result(_result_with_tokens(lid="lid1", total=2, status="error"), state)
        _handle_image_result(_result_with_tokens(lid="lid2", total=2, status="error"), state)

    assert captured.get("prompt_tokens", 0) == 0
    assert captured.get("completion_tokens", 0) == 0
    assert captured.get("cost_usd") is None
    # FAILED call must not have passed non-zero tokens
    assert "prompt_tokens" not in captured or captured["prompt_tokens"] == 0


def test_aggregate_retries_pdf_generation_after_transient_failure():
    state = {}
    captured = {}

    def fake_publish(job_id, status, stage_info, **kwargs):
        if status == "COMPLETED":
            captured.update(kwargs)

    with (
        patch("messaging.aggregator.generate_pdf_bytes", side_effect=[TimeoutError("pdf timeout"), b"%PDF"]),
        patch("messaging.aggregator.upload_pdf", return_value="http://minio/r.pdf"),
        patch("messaging.aggregator.publish_status", side_effect=fake_publish),
        patch("messaging.aggregator.time.sleep"),
    ):
        from messaging.aggregator import _handle_image_result
        _handle_image_result(_result_with_tokens(lid="lid1", total=1), state)

    assert captured["pdf_url"] == "http://minio/r.pdf"


def test_aggregate_retries_pdf_upload_after_transient_failure():
    state = {}
    captured = {}

    def fake_publish(job_id, status, stage_info, **kwargs):
        if status == "COMPLETED":
            captured.update(kwargs)

    with (
        patch("messaging.aggregator.generate_pdf_bytes", return_value=b"%PDF"),
        patch("messaging.aggregator.upload_pdf", side_effect=[TimeoutError("upload timeout"), "http://minio/r.pdf"]),
        patch("messaging.aggregator.publish_status", side_effect=fake_publish),
        patch("messaging.aggregator.time.sleep"),
    ):
        from messaging.aggregator import _handle_image_result
        _handle_image_result(_result_with_tokens(lid="lid1", total=1), state)

    assert captured["pdf_url"] == "http://minio/r.pdf"


def test_aggregate_recovers_after_eval_pdf_upload_fault(monkeypatch):
    state = {}
    completed = {}

    def fake_publish(job_id, status, stage_info, **kwargs):
        if status == "COMPLETED":
            completed.update(kwargs)

    class Registry:
        def __init__(self):
            self.calls = []

        def should_fail(self, stage, job_id, lid=None):
            self.calls.append(stage)
            if stage == "pdf_upload" and self.calls.count("pdf_upload") == 1:
                return {"fault_id": "f-pdf", "stage": stage, "job_id": job_id}
            return None

    registry = Registry()
    upload_pdf = MagicMock(return_value="http://minio/report.pdf")

    monkeypatch.setattr("messaging.aggregator.get_eval_fault_registry", lambda: registry)
    monkeypatch.setattr("messaging.aggregator.generate_pdf_bytes", lambda *_args: b"%PDF")
    monkeypatch.setattr("messaging.aggregator.upload_pdf", upload_pdf)
    monkeypatch.setattr("messaging.aggregator.publish_status", fake_publish)
    monkeypatch.setattr("messaging.aggregator.time.sleep", lambda _delay: None)

    from messaging.aggregator import _handle_image_result
    _handle_image_result(_result_with_tokens(lid="lid1", total=1), state)

    assert completed["pdf_url"] == "http://minio/report.pdf"
    assert registry.calls.count("pdf_upload") == 2
    upload_pdf.assert_called_once()


def test_aggregate_recovers_after_eval_pdf_generation_fault(monkeypatch, caplog):
    state = {}
    completed = {}

    def fake_publish(job_id, status, stage_info, **kwargs):
        if status == "COMPLETED":
            completed.update(kwargs)

    class Registry:
        def __init__(self):
            self.calls = []

        def should_fail(self, stage, job_id, lid=None):
            self.calls.append(stage)
            if stage == "pdf_generation" and self.calls.count("pdf_generation") == 1:
                return {"fault_id": "f-pdf-generation", "stage": stage, "job_id": job_id, "lid": lid}
            return None

    registry = Registry()
    generate_pdf_bytes = MagicMock(return_value=b"%PDF")

    monkeypatch.setattr("messaging.aggregator.get_eval_fault_registry", lambda: registry)
    monkeypatch.setattr("messaging.aggregator.generate_pdf_bytes", generate_pdf_bytes)
    monkeypatch.setattr("messaging.aggregator.upload_pdf", lambda *_args: "http://minio/report.pdf")
    monkeypatch.setattr("messaging.aggregator.publish_status", fake_publish)
    monkeypatch.setattr("messaging.aggregator._fetch_langsmith_job_cost", lambda _job_id: None)
    monkeypatch.setattr("messaging.aggregator.time.sleep", lambda _delay: None)

    from messaging.aggregator import _handle_image_result
    with caplog.at_level(logging.WARNING, logger="messaging.aggregator"):
        _handle_image_result(_result_with_tokens(lid="lid1", total=1), state)

    assert completed["pdf_url"] == "http://minio/report.pdf"
    assert registry.calls.count("pdf_generation") == 2
    generate_pdf_bytes.assert_called_once()
    assert 'EVAL_FAULT injected {"fault_id": "f-pdf-generation", "job_id": "job-1", "lid": null, "stage": "pdf_generation"}' in caplog.text


def test_duplicate_image_result_is_logged_and_skipped(caplog):
    state = {}

    from messaging.aggregator import _handle_image_result
    with (
        patch("messaging.aggregator.publish_status") as publish_status,
        caplog.at_level(logging.WARNING, logger="messaging.aggregator"),
    ):
        _handle_image_result(_result(job_id="job-dup", lid="lid-1", total=2), state)
        _handle_image_result(_result(job_id="job-dup", lid="lid-1", total=2), state)

    assert len(state["job-dup"]["results"]) == 1
    assert state["job-dup"]["seen_lids"] == {"lid-1"}
    publish_status.assert_called_once_with("job-dup", "PROCESSING_IMAGES", "1/2")
    assert (
        "KAFKA_IDEMPOTENCY duplicate_image_result job=job-dup lid=lid-1 "
        "guard=seen_lids final_effect=skipped_duplicate"
    ) in caplog.text


def test_duplicate_image_result_fault_replays_and_skips_duplicate(monkeypatch, caplog):
    state = {}

    class Registry:
        def should_duplicate(self, stage, job_id, lid=None):
            if stage == "duplicate_image_result":
                return {
                    "fault_id": "dup-image",
                    "stage": stage,
                    "job_id": job_id,
                    "lid": lid,
                    "attempt": 1,
                    "duplicates": 1,
                }
            return None

    monkeypatch.setattr("messaging.aggregator.get_eval_fault_registry", lambda: Registry())

    from messaging.aggregator import _handle_image_result
    with (
        patch("messaging.aggregator.publish_status") as publish_status,
        caplog.at_level(logging.WARNING, logger="messaging.aggregator"),
    ):
        _handle_image_result(_result(job_id="job-dup", lid="lid-1", total=2), state)

    assert len(state["job-dup"]["results"]) == 1
    assert publish_status.call_count == 1
    assert "EVAL_FAULT injected" in caplog.text
    assert '"stage": "duplicate_image_result"' in caplog.text
    assert (
        "KAFKA_IDEMPOTENCY duplicate_image_result job=job-dup lid=lid-1 "
        "guard=seen_lids final_effect=skipped_duplicate"
    ) in caplog.text
