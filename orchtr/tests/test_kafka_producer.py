import importlib
from unittest.mock import patch, MagicMock
import json
import pytest


@pytest.fixture(autouse=True)
def reset_kafka_producer():
    """Reset the cached _producer singleton between tests."""
    import messaging.producer as _kp_mod
    _kp_mod._producer = None
    yield
    _kp_mod._producer = None


def test_publish_status_sends_correct_message():
    mock_producer = MagicMock()
    with patch("messaging.producer._KafkaProducer", return_value=mock_producer):
        from messaging.producer import publish_status
        publish_status("job-123", "PROCESSING_IMAGES", "1/3")

    mock_producer.send.assert_called_once()
    call_args = mock_producer.send.call_args
    assert call_args[0][0] == "job.status"
    payload = json.loads(call_args[1]["value"])
    assert payload["job_id"] == "job-123"
    assert payload["status"] == "PROCESSING_IMAGES"
    assert payload["stage_info"] == "1/3"
    assert payload["pdf_url"] is None
    assert payload["error"] is None


def test_publish_status_completed_includes_pdf_url():
    mock_producer = MagicMock()
    with patch("messaging.producer._KafkaProducer", return_value=mock_producer):
        from messaging.producer import publish_status
        publish_status("job-123", "COMPLETED", "", pdf_url="http://minio/report.pdf")

    call_args = mock_producer.send.call_args
    payload = json.loads(call_args[1]["value"])
    assert payload["pdf_url"] == "http://minio/report.pdf"
    assert payload["error"] is None


def test_publish_status_retries_send_and_flush_after_transient_failure():
    mock_producer = MagicMock()
    mock_producer.send.side_effect = [TimeoutError("broker busy"), MagicMock()]

    with (
        patch("messaging.producer._KafkaProducer", return_value=mock_producer),
        patch("messaging.producer.time.sleep"),
    ):
        from messaging.producer import publish_status
        publish_status("job-123", "PROCESSING_IMAGES", "1/3")

    assert mock_producer.send.call_count == 2
    mock_producer.flush.assert_called_once()


def test_publish_status_retries_send_after_ambiguous_flush_failure():
    mock_producer = MagicMock()
    mock_producer.flush.side_effect = [TimeoutError("flush timed out"), None]

    with (
        patch("messaging.producer._KafkaProducer", return_value=mock_producer),
        patch("messaging.producer.time.sleep"),
    ):
        from messaging.producer import publish_status
        publish_status("job-123", "PROCESSING_IMAGES", "1/3")

    assert mock_producer.send.call_count == 2
    assert mock_producer.flush.call_count == 2


def test_publish_status_recovers_after_eval_fault(monkeypatch):
    from messaging import producer

    class Registry:
        def __init__(self):
            self.calls = 0

        def should_fail(self, stage, job_id, lid=None):
            if stage == "job_status_publish" and self.calls == 0:
                self.calls += 1
                return {"fault_id": "f-status", "stage": stage, "job_id": job_id, "lid": lid}
            return None

    class Producer:
        def __init__(self):
            self.sent = 0

        def send(self, *_args, **_kwargs):
            self.sent += 1

        def flush(self):
            pass

    fake = Producer()
    monkeypatch.setattr(producer, "get_eval_fault_registry", lambda: Registry())
    monkeypatch.setattr(producer, "_get_producer", lambda: fake)
    monkeypatch.setattr(producer.time, "sleep", lambda _delay: None)

    producer.publish_status("job-1", "PROCESSING_IMAGES", "0/1")

    assert fake.sent == 1


def test_publish_status_can_inject_late_terminal_duplicate(monkeypatch, caplog):
    from messaging import producer

    class Registry:
        def should_fail(self, *_args, **_kwargs):
            return None

        def should_duplicate(self, stage, job_id, lid=None):
            if stage == "late_terminal_status":
                return {
                    "fault_id": "dup-terminal",
                    "stage": stage,
                    "job_id": job_id,
                    "lid": lid,
                    "attempt": 1,
                    "duplicates": 1,
                }
            return None

    class Producer:
        def __init__(self):
            self.sent = 0

        def send(self, *_args, **_kwargs):
            self.sent += 1

        def flush(self):
            pass

    fake = Producer()
    monkeypatch.setattr(producer, "get_eval_fault_registry", lambda: Registry())
    monkeypatch.setattr(producer, "_get_producer", lambda: fake)

    with caplog.at_level("WARNING", logger="messaging.producer"):
        producer.publish_status("job-1", "COMPLETED", "", pdf_url="http://minio/report.pdf")

    assert fake.sent == 2
    assert "EVAL_FAULT injected" in caplog.text
    assert '"stage": "late_terminal_status"' in caplog.text
