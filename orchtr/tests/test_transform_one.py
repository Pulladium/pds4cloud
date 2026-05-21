import json
from unittest.mock import MagicMock, patch


def test_transform_one_skip_loads_existing_array_summary():
    from nodes.transform.one import run_transform_one

    summary_path = "transformed/mastcamz/sol=00042/PHOTO_1/array_summary.json"
    summary = {"ndim": 2, "shape": [10, 12], "dtype": "uint16", "bands": 1}

    storage = MagicMock()
    storage.exists.side_effect = lambda path: path.endswith("rgb.jpg") or path == summary_path
    storage.download_bytes.return_value = json.dumps(summary).encode("utf-8")

    with patch("nodes.transform.one.get_storage_adapter", return_value=storage):
        result = run_transform_one({
            "photo_id": "PHOTO_1",
            "sol": "00042",
            "status": "already_transformed",
            "messages": ["ingest_one: skip (already transformed)"],
        })

    assert result["status"] == "transform_skipped"
    assert result["array_summary_path"] == summary_path
    assert result["array_summary"] == summary


def test_process_one_task_retries_storage_download_after_transient_failure():
    from nodes.transform.logic import process_one_task

    storage = MagicMock()
    storage.exists.return_value = False
    storage.download_bytes.side_effect = [TimeoutError("minio timeout"), b"raw-img"]

    with (
        patch("nodes.transform.logic.read_imgdata", return_value=__import__("numpy").array([[1, 2], [3, 4]], dtype="uint16")),
        patch("nodes.transform.logic.db.pg_mark_done"),
        patch("nodes.transform.logic.db.pg_mark_failed"),
    ):
        result = process_one_task("PHOTO_1", 42, "mastcamz/sol=00042/PHOTO_1.IMG", storage)

    assert result["status"] == "ok"
    assert storage.download_bytes.call_count == 2


def test_process_one_task_recovers_after_gray_upload_fault(monkeypatch, capsys):
    from nodes.transform import logic

    class Registry:
        def __init__(self):
            self.calls = 0

        def should_fail(self, stage, job_id, lid=None):
            if stage == "transform_gray_upload" and self.calls == 0:
                self.calls += 1
                return {"fault_id": "f-transform-gray", "stage": stage, "job_id": job_id, "lid": lid}
            return None

    class Storage:
        def __init__(self):
            self.uploads = []

        def exists(self, _path):
            return False

        def download_bytes(self, _path):
            return b"raw"

        def upload_bytes(self, path, data, content_type):
            self.uploads.append((path, content_type))
            return True

    registry = Registry()
    storage = Storage()
    monkeypatch.setattr(logic, "get_eval_fault_registry", lambda: registry)
    monkeypatch.setattr(logic, "read_imgdata", lambda _raw: __import__("numpy").zeros((2, 2), dtype="uint8"))
    monkeypatch.setattr(logic.db, "pg_mark_done", lambda *_args: None)
    monkeypatch.setattr(logic.db, "pg_mark_failed", lambda *_args: None)

    result = logic.process_one_task("photo-1", 1, "mastcamz/sol=00001/A.IMG", storage)

    assert result["status"] == "ok"
    assert result["gray"] == "uploaded"
    assert ("transformed/mastcamz/sol=00001/A/gray.jpg", "image/jpeg") in storage.uploads
    assert "EVAL_FAULT injected" in capsys.readouterr().out


def test_process_one_task_recovers_after_download_fault(monkeypatch, capsys):
    from nodes.transform import logic

    class Registry:
        def __init__(self):
            self.calls = 0

        def should_fail(self, stage, job_id, lid=None):
            if stage == "transform_storage_download" and self.calls == 0:
                self.calls += 1
                return {"fault_id": "f-transform-download", "stage": stage, "job_id": job_id, "lid": lid}
            return None

    storage = MagicMock()
    storage.exists.return_value = False
    storage.download_bytes.return_value = b"raw-img"

    registry = Registry()
    monkeypatch.setattr(logic, "get_eval_fault_registry", lambda: registry)
    monkeypatch.setattr(logic, "read_imgdata", lambda _raw: __import__("numpy").array([[1, 2], [3, 4]], dtype="uint16"))
    monkeypatch.setattr(logic.db, "pg_mark_done", lambda *_args: None)
    monkeypatch.setattr(logic.db, "pg_mark_failed", lambda *_args: None)

    result = logic.process_one_task("PHOTO_1", 42, "mastcamz/sol=00042/PHOTO_1.IMG", storage)

    assert result["status"] == "ok"
    assert storage.download_bytes.call_count == 1
    assert "EVAL_FAULT injected" in capsys.readouterr().out
