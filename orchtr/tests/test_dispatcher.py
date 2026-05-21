import json
from unittest.mock import MagicMock, patch


def _submit_payload(n=2):
    return {
        "job_id": "job-1",
        "project_id": "proj-1",
        "images": [{"lid": f"lid{i}", "thumb_url": f"http://t{i}"} for i in range(n)],
    }


def test_handle_job_submitted_fans_out_n_image_tasks():
    mock_producer = MagicMock()
    with patch("messaging.dispatcher.publish_status"):
        from messaging.dispatcher import _handle_job_submitted
        _handle_job_submitted(_submit_payload(n=3), mock_producer)

    assert mock_producer.send.call_count == 3
    sent_lids = []
    for call in mock_producer.send.call_args_list:
        topic = call[0][0]
        payload = json.loads(call[1]["value"])
        assert topic == "image.task"
        assert payload["job_id"] == "job-1"
        assert payload["total_images"] == 3
        assert payload["project_id"] == "proj-1"
        sent_lids.append(payload["lid"])
    assert sorted(sent_lids) == ["lid0", "lid1", "lid2"]
    assert mock_producer.flush.call_count == 3


def test_handle_job_submitted_publishes_processing_images_zero_of_n():
    mock_producer = MagicMock()
    statuses = []

    def fake_publish(job_id, status, stage_info, **_):
        statuses.append((status, stage_info))

    with patch("messaging.dispatcher.publish_status", side_effect=fake_publish):
        from messaging.dispatcher import _handle_job_submitted
        _handle_job_submitted(_submit_payload(n=2), mock_producer)

    assert ("PROCESSING_IMAGES", "0/2") in statuses


def test_handle_job_submitted_publishes_failed_for_empty_images():
    mock_producer = MagicMock()
    errors = []

    def fake_publish(job_id, status, stage_info, error=None, **_):
        if error:
            errors.append(error)

    with patch("messaging.dispatcher.publish_status", side_effect=fake_publish):
        from messaging.dispatcher import _handle_job_submitted
        _handle_job_submitted({"job_id": "j1", "project_id": "p1", "images": []}, mock_producer)

    assert errors
    mock_producer.send.assert_not_called()


def test_dispatcher_includes_model_in_image_tasks():
    def _payload(model="gpt-4o-mini"):
        return {
            "job_id": "job-1",
            "project_id": "proj-1",
            "model": model,
            "images": [
                {"lid": "lid1", "thumb_url": "http://t1"},
                {"lid": "lid2", "thumb_url": "http://t2"},
            ],
        }

    mock_producer = MagicMock()
    with patch("messaging.dispatcher.publish_status"):
        from messaging.dispatcher import _handle_job_submitted
        _handle_job_submitted(_payload("gpt-4-turbo"), mock_producer)

    assert mock_producer.send.call_count == 2
    for call in mock_producer.send.call_args_list:
        task = json.loads(call[1]["value"])
        assert task["model"] == "gpt-4-turbo"


def test_dispatcher_defaults_model_when_missing():
    def _payload(model="gpt-4o-mini"):
        return {
            "job_id": "job-1",
            "project_id": "proj-1",
            "model": model,
            "images": [
                {"lid": "lid1", "thumb_url": "http://t1"},
                {"lid": "lid2", "thumb_url": "http://t2"},
            ],
        }

    mock_producer = MagicMock()
    payload = _payload()
    del payload["model"]
    with patch("messaging.dispatcher.publish_status"):
        from messaging.dispatcher import _handle_job_submitted
        _handle_job_submitted(payload, mock_producer)

    task = json.loads(mock_producer.send.call_args_list[0][1]["value"])
    assert task["model"] == "gpt-4o"


def test_dispatcher_passes_user_id_to_image_tasks():
    producer = MagicMock()
    payload = {
        "job_id": "job-1",
        "project_id": "project-1",
        "user_id": "user-1",
        "model": "gpt-4o",
        "images": [{"lid": "lid-1", "thumb_url": "http://thumb"}],
    }

    from messaging.dispatcher import _handle_job_submitted
    _handle_job_submitted(payload, producer)

    task = json.loads(producer.send.call_args[1]["value"].decode())
    assert task["user_id"] == "user-1"


def test_handle_job_submitted_retries_image_task_publish_after_transient_failure():
    producer = MagicMock()
    producer.send.side_effect = [TimeoutError("broker busy"), MagicMock()]
    payload = {
        "job_id": "job-1",
        "project_id": "project-1",
        "user_id": "user-1",
        "model": "gpt-4o",
        "images": [{"lid": "lid-1", "thumb_url": "http://thumb"}],
    }

    with (
        patch("messaging.dispatcher.publish_status"),
        patch("messaging.dispatcher.time.sleep"),
    ):
        from messaging.dispatcher import _handle_job_submitted
        _handle_job_submitted(payload, producer)

    assert producer.send.call_count == 2
    producer.flush.assert_called_once()


def test_handle_job_submitted_retries_image_task_publish_after_ambiguous_flush_failure():
    producer = MagicMock()
    producer.flush.side_effect = [TimeoutError("flush timed out"), None]
    payload = {
        "job_id": "job-1",
        "project_id": "project-1",
        "user_id": "user-1",
        "model": "gpt-4o",
        "images": [{"lid": "lid-1", "thumb_url": "http://thumb"}],
    }

    with (
        patch("messaging.dispatcher.publish_status"),
        patch("messaging.dispatcher.time.sleep"),
    ):
        from messaging.dispatcher import _handle_job_submitted
        _handle_job_submitted(payload, producer)

    assert producer.send.call_count == 2
    assert producer.flush.call_count == 2


def test_dispatcher_recovers_after_image_task_publish_fault(monkeypatch):
    from messaging.dispatcher import _handle_job_submitted

    class Registry:
        def __init__(self):
            self.calls = 0

        def should_fail(self, stage, job_id, lid=None):
            if stage == "image_task_publish" and self.calls == 0:
                self.calls += 1
                return {"fault_id": "f-image-task", "stage": stage, "job_id": job_id, "lid": lid}
            return None

    class Producer:
        def __init__(self):
            self.sent = 0

        def send(self, *_args, **_kwargs):
            self.sent += 1

        def flush(self):
            pass

    producer = Producer()
    monkeypatch.setattr("messaging.dispatcher.get_eval_fault_registry", lambda: Registry())
    monkeypatch.setattr("messaging.dispatcher.time.sleep", lambda _delay: None)
    monkeypatch.setattr("messaging.dispatcher.publish_status", lambda *_args, **_kwargs: None)

    _handle_job_submitted({"job_id": "job-1", "images": [{"lid": "lid-1"}]}, producer)

    assert producer.sent == 1
