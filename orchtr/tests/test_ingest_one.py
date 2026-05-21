from unittest.mock import MagicMock, patch

from nodes.ingest.one import _img_url_from_label, run_ingest_one


def test_img_url_from_relative_label_url():
    url = _img_url_from_label("archive/m20/r11/file.xml")

    assert url == "https://pds-imaging.jpl.nasa.gov/data/mars2020/archive/m20/r11/file.IMG"


def test_img_url_from_absolute_label_url_does_not_prefix_base_url():
    url = _img_url_from_label(
        "https://pds-imaging.jpl.nasa.gov/archive/m20/r11/file.xml"
    )

    assert url == "https://pds-imaging.jpl.nasa.gov/archive/m20/r11/file.IMG"


def test_run_ingest_one_retries_pds_lookup_after_transient_failure():
    storage = MagicMock()
    storage.exists.return_value = True

    with (
        patch("nodes.ingest.one._pds_lookup", side_effect=[
            TimeoutError("pds timeout"),
            ("00042", "https://pds-imaging.jpl.nasa.gov/archive/m20/r11/file.xml", "file.IMG", {"lid": ["lid1"]}),
        ]) as lookup,
        patch("nodes.ingest.storage.get_storage_adapter", return_value=storage),
        patch("nodes.ingest.one.time.sleep"),
    ):
        result = run_ingest_one({"product_lid": "lid1"})

    assert result["status"] == "already_transformed"
    assert result["photo_id"] == "file"
    assert lookup.call_count == 2


def test_run_ingest_one_recovers_after_pds_lookup_fault(monkeypatch):
    from nodes.ingest import one

    class Registry:
        def __init__(self):
            self.calls = 0

        def should_fail(self, stage, job_id, lid=None):
            self.calls += 1
            if stage == "pds_lookup" and self.calls == 1:
                return {"fault_id": "f-pds-lookup", "stage": stage, "job_id": job_id, "lid": lid}
            return None

    class Storage:
        def exists(self, _path):
            return False

        def upload_bytes(self, *_args):
            return True

    registry = Registry()
    monkeypatch.setattr(one, "get_eval_fault_registry", lambda: registry)
    monkeypatch.setattr(one.time, "sleep", lambda _delay: None)
    monkeypatch.setattr(one, "_pds_lookup", lambda lid: ("00001", "http://example/a.xml", "A.IMG", {"lid": [lid]}))
    monkeypatch.setattr(one, "_download", lambda _url: b"img")
    monkeypatch.setattr("nodes.ingest.storage.get_storage_adapter", lambda: Storage())

    result = one.run_ingest_one({"product_lid": "lid-1"})

    assert result["status"] == "ingested"


def test_run_ingest_one_retries_metadata_upload_after_eval_fault(monkeypatch):
    from nodes.ingest import one

    class Registry:
        def __init__(self):
            self.calls_by_stage = {}

        def should_fail(self, stage, job_id, lid=None):
            self.calls_by_stage[stage] = self.calls_by_stage.get(stage, 0) + 1
            if stage == "ingest_metadata_upload" and self.calls_by_stage[stage] == 1:
                return {"fault_id": "f-metadata-upload", "stage": stage, "job_id": job_id, "lid": lid}
            return None

    class Storage:
        def __init__(self):
            self.uploads = []

        def exists(self, _path):
            return False

        def upload_bytes(self, path, data, content_type):
            self.uploads.append((path, data, content_type))
            return True

    registry = Registry()
    storage = Storage()
    monkeypatch.setattr(one, "get_eval_fault_registry", lambda: registry)
    monkeypatch.setattr(one.time, "sleep", lambda _delay: None)
    monkeypatch.setattr(one, "_pds_lookup", lambda lid: ("00001", "http://example/a.xml", "A.IMG", {"lid": [lid]}))
    monkeypatch.setattr(one, "_download", lambda _url: b"img")
    monkeypatch.setattr("nodes.ingest.storage.get_storage_adapter", lambda: storage)

    result = one.run_ingest_one({"product_lid": "lid-1"})

    assert result["status"] == "ingested"
    assert registry.calls_by_stage["ingest_metadata_upload"] == 2
    assert [upload[0] for upload in storage.uploads] == [
        "mastcamz/sol=00001/A.IMG",
        "mastcamz/sol=00001/A_metadata.json",
    ]
