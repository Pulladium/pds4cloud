import pytest

from utils.eval_faults import EvalFaultRegistry


def test_registry_disabled_when_env_empty(monkeypatch):
    monkeypatch.delenv("EVAL_FAULTS", raising=False)
    registry = EvalFaultRegistry.from_env()

    assert registry.should_fail("analyze", "job-1", "lid-1") is None


def test_registry_disabled_when_env_whitespace(monkeypatch):
    monkeypatch.setenv("EVAL_FAULTS", " \n\t ")
    registry = EvalFaultRegistry.from_env()

    assert registry.should_fail("analyze", "job-1", "lid-1") is None


def test_registry_rejects_non_list_json(monkeypatch):
    monkeypatch.setenv("EVAL_FAULTS", '{"fault_id":"f"}')

    with pytest.raises(ValueError, match="EVAL_FAULTS must be a JSON list"):
        EvalFaultRegistry.from_env()


def test_registry_rejects_non_object_entries(monkeypatch):
    monkeypatch.setenv("EVAL_FAULTS", '["not-an-object"]')

    with pytest.raises(ValueError, match="EVAL_FAULTS entries must be JSON objects"):
        EvalFaultRegistry.from_env()


def test_registry_injects_matching_fault_once(monkeypatch):
    monkeypatch.setenv(
        "EVAL_FAULTS",
        '[{"fault_id":"f-analyze","stage":"analyze","job_id":"job-1","lid":"lid-1","failures":1}]',
    )
    registry = EvalFaultRegistry.from_env()

    first = registry.should_fail("analyze", "job-1", "lid-1")
    second = registry.should_fail("analyze", "job-1", "lid-1")

    assert first == {
        "fault_id": "f-analyze",
        "stage": "analyze",
        "job_id": "job-1",
        "lid": "lid-1",
        "attempt": 1,
        "failures": 1,
        "duplicates": 0,
    }
    assert second is None


def test_registry_ignores_non_matching_stage(monkeypatch):
    monkeypatch.setenv(
        "EVAL_FAULTS",
        '[{"fault_id":"f-pdf","stage":"pdf_upload","job_id":"job-1","failures":1}]',
    )
    registry = EvalFaultRegistry.from_env()

    assert registry.should_fail("analyze", "job-1", "lid-1") is None


def test_registry_treats_empty_job_id_as_wildcard(monkeypatch):
    monkeypatch.setenv(
        "EVAL_FAULTS",
        '[{"fault_id":"f-pdf","stage":"pdf_upload","job_id":"","failures":1}]',
    )
    registry = EvalFaultRegistry.from_env()

    fault = registry.should_fail("pdf_upload", "real-job-id")

    assert fault["fault_id"] == "f-pdf"
    assert fault["job_id"] == "real-job-id"


def test_registry_treats_missing_lid_as_wildcard(monkeypatch):
    monkeypatch.setenv(
        "EVAL_FAULTS",
        '[{"fault_id":"f-any-lid","stage":"transform_gray_upload","job_id":"","failures":1}]',
    )
    registry = EvalFaultRegistry.from_env()

    fault = registry.should_fail("transform_gray_upload", "job-1", "lid-123")

    assert fault["fault_id"] == "f-any-lid"
    assert fault["job_id"] == "job-1"
    assert fault["lid"] == "lid-123"


def test_registry_continues_to_later_matching_fault_after_first_exhausted(monkeypatch):
    monkeypatch.setenv(
        "EVAL_FAULTS",
        "["
        '{"fault_id":"f-first","stage":"analyze","job_id":"job-1","lid":"lid-1","failures":1},'
        '{"fault_id":"f-second","stage":"analyze","job_id":"job-1","lid":"lid-1","failures":1}'
        "]",
    )
    registry = EvalFaultRegistry.from_env()

    first = registry.should_fail("analyze", "job-1", "lid-1")
    second = registry.should_fail("analyze", "job-1", "lid-1")
    third = registry.should_fail("analyze", "job-1", "lid-1")

    assert first["fault_id"] == "f-first"
    assert first["attempt"] == 1
    assert second["fault_id"] == "f-second"
    assert second["attempt"] == 1
    assert third is None


def test_registry_injects_matching_fault_for_configured_failure_count(monkeypatch):
    monkeypatch.setenv(
        "EVAL_FAULTS",
        '[{"fault_id":"f-analyze","stage":"analyze","job_id":"job-1","lid":"lid-1","failures":2}]',
    )
    registry = EvalFaultRegistry.from_env()

    first = registry.should_fail("analyze", "job-1", "lid-1")
    second = registry.should_fail("analyze", "job-1", "lid-1")
    third = registry.should_fail("analyze", "job-1", "lid-1")

    assert first["attempt"] == 1
    assert first["failures"] == 2
    assert second["attempt"] == 2
    assert second["failures"] == 2
    assert third is None


def test_registry_supports_duplicate_specs(monkeypatch):
    monkeypatch.setenv(
        "EVAL_FAULTS",
        '[{"fault_id":"dup-image","stage":"duplicate_image_result","job_id":"","lid":"lid-1","duplicates":2}]',
    )
    registry = EvalFaultRegistry.from_env()

    first = registry.should_duplicate("duplicate_image_result", "job-1", "lid-1")
    second = registry.should_duplicate("duplicate_image_result", "job-1", "lid-1")
    third = registry.should_duplicate("duplicate_image_result", "job-1", "lid-1")

    assert first["fault_id"] == "dup-image"
    assert first["attempt"] == 1
    assert first["duplicates"] == 2
    assert second["attempt"] == 2
    assert third is None


def test_failure_and_duplicate_attempts_are_tracked_independently(monkeypatch):
    monkeypatch.setenv(
        "EVAL_FAULTS",
        '[{"fault_id":"f","stage":"s","job_id":"j","failures":1,"duplicates":1}]',
    )
    registry = EvalFaultRegistry.from_env()

    assert registry.should_fail("s", "j")["attempt"] == 1
    assert registry.should_duplicate("s", "j")["attempt"] == 1
    assert registry.should_fail("s", "j") is None
    assert registry.should_duplicate("s", "j") is None
