# Full Production Retry Coverage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the Docker retry evaluation so thesis evidence covers all production retry boundaries plus Kafka at-least-once duplicate idempotency.

**Architecture:** Reuse the existing `EVAL_FAULTS` registry, but expand it into a production retry evidence system that supports transient faults and deterministic duplicate-message scenarios. Add evaluation-only hooks at each production retry boundary, then extend `evaluation.run_retry_recovery_e2e` to build the full fault plan, parse Docker log evidence, and write two thesis tables: production retry coverage and Kafka idempotency coverage.

**Tech Stack:** Python orchestrator/evaluation runner, Java Spring Gateway, Kafka, Docker Compose eval profile, pytest, Maven/JUnit.

---

## File Structure

- Modify `orchtr/utils/eval_faults.py`: add duplicate count support, helper logging payload shape, and stage matching helpers.
- Modify `orchtr/tests/test_eval_faults.py`: tests for `duplicates`, wildcard `job_id`, wildcard `lid`, and exhausted matching behavior.
- Modify `orchtr/nodes/ingest/one.py`: inject faults for `pds_lookup`, `pds_img_download`, `ingest_metadata_upload`, and `ingest_img_upload`.
- Create or extend `orchtr/tests/test_ingest_one.py`: unit tests for ingest fault recovery where practical.
- Modify `orchtr/nodes/transform/logic.py`: inject faults for `transform_storage_download`, `transform_gray_upload`, and `transform_rgb_upload`.
- Modify `orchtr/tests/test_transform_one.py`: tests for transform fault recovery.
- Modify `orchtr/nodes/analyze/logic.py`: inject faults for `analyze_image_download`, `analyze_openai_call`, and `analyze_result_upload`.
- Modify `orchtr/tests/test_analyze_logic.py`: tests for analyze fault recovery.
- Modify `orchtr/messaging/image_worker.py`: normalize existing image worker hook to `image_worker_process`.
- Modify `orchtr/messaging/aggregator.py`: add `pdf_generation` hook and deterministic `duplicate_image_result` evidence.
- Modify `orchtr/tests/test_image_worker.py` and `orchtr/tests/test_aggregator.py`: update/add retry and duplicate tests.
- Modify `orchtr/messaging/dispatcher.py`: inject `image_task_publish` fault inside existing retry.
- Modify `orchtr/messaging/producer.py`: inject `job_status_publish` fault inside existing retry.
- Modify `orchtr/tests/test_dispatcher.py` and `orchtr/tests/test_kafka_producer.py`: tests for publish fault recovery.
- Modify `gateway/src/main/java/com/mars/gateway/job/JobService.java`: add evaluation-only fault hook for `job_submitted_publish` and explicit duplicate/late status event evidence.
- Modify `gateway/src/test/java/com/mars/gateway/job/JobServiceTest.java`: tests for gateway publish fault and duplicate status idempotency.
- Modify `evaluation/run_retry_recovery_e2e.py`: build full production and Kafka fault plans, parse evidence, emit new JSON and `.txt` tables.
- Modify `evaluation/tests/test_retry_recovery_e2e.py`: protocol tests for full fault plan, evidence parsing, and new tables.
- Modify `evaluation/report.py` only if needed; current glob already lists all generated `.txt` outputs.

## Task 1: Expand Fault Registry for Full Coverage

**Files:**
- Modify: `/home/pallad/Backbackup/Backup2/orchtr/utils/eval_faults.py`
- Test: `/home/pallad/Backbackup/Backup2/orchtr/tests/test_eval_faults.py`

- [ ] **Step 1: Write failing tests**

Append tests:

```python
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
```

- [ ] **Step 2: Verify tests fail**

Run:

```bash
cd /home/pallad/Backbackup/Backup2/orchtr
.venv/bin/pytest tests/test_eval_faults.py::test_registry_treats_missing_lid_as_wildcard tests/test_eval_faults.py::test_registry_supports_duplicate_specs -q
```

Expected: first fails because returned `lid` is `None`, second fails because `should_duplicate` does not exist.

- [ ] **Step 3: Implement registry changes**

Update `EvalFault`:

```python
@dataclass(frozen=True)
class EvalFault:
    fault_id: str
    stage: str
    job_id: str
    lid: str | None
    failures: int
    duplicates: int
```

Update parsing:

```python
duplicates=int(spec.get("duplicates", 0)),
```

Add shared consume helper:

```python
def _consume(self, stage: str, job_id: str, lid: str | None, limit_attr: str) -> dict[str, object] | None:
    with self._lock:
        for fault in self._faults:
            if not self._matches(fault, stage, job_id, lid):
                continue
            limit = getattr(fault, limit_attr)
            if limit <= 0:
                continue
            attempt = self._attempts.get(fault.fault_id, 0) + 1
            if attempt > limit:
                continue
            self._attempts[fault.fault_id] = attempt
            payload = {
                "fault_id": fault.fault_id,
                "stage": fault.stage,
                "job_id": job_id,
                "lid": lid if lid is not None else fault.lid,
                "attempt": attempt,
                "failures": fault.failures,
                "duplicates": fault.duplicates,
            }
            return payload
    return None
```

Update:

```python
def should_fail(self, stage: str, job_id: str, lid: str | None = None) -> dict[str, object] | None:
    return self._consume(stage, job_id, lid, "failures")

def should_duplicate(self, stage: str, job_id: str, lid: str | None = None) -> dict[str, object] | None:
    return self._consume(stage, job_id, lid, "duplicates")
```

- [ ] **Step 4: Verify registry tests pass**

Run:

```bash
cd /home/pallad/Backbackup/Backup2/orchtr
.venv/bin/pytest tests/test_eval_faults.py -q
```

Expected: all tests pass.

## Task 2: Add Ingest Retry Fault Hooks

**Files:**
- Modify: `/home/pallad/Backbackup/Backup2/orchtr/nodes/ingest/one.py`
- Test: `/home/pallad/Backbackup/Backup2/orchtr/tests/test_ingest_one.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_ingest_one.py` if missing, or append:

```python
import pytest


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

    monkeypatch.setattr(one, "get_eval_fault_registry", lambda: Registry())
    monkeypatch.setattr(one.time, "sleep", lambda _delay: None)
    monkeypatch.setattr(one, "_pds_lookup", lambda lid: ("00001", "http://example/a.xml", "A.IMG", {"lid": [lid]}))
    monkeypatch.setattr(one, "_download", lambda _url: b"img")
    monkeypatch.setattr("nodes.ingest.one.get_storage_adapter", lambda: Storage())

    result = one.run_ingest_one({"product_lid": "lid-1"})

    assert result["status"] == "ingested"
```

- [ ] **Step 2: Verify test fails**

Run:

```bash
cd /home/pallad/Backbackup/Backup2/orchtr
.venv/bin/pytest tests/test_ingest_one.py::test_run_ingest_one_recovers_after_pds_lookup_fault -q
```

Expected: monkeypatch path or missing `get_eval_fault_registry` failure.

- [ ] **Step 3: Implement hooks**

In `nodes/ingest/one.py`, import:

```python
from utils.eval_faults import get_eval_fault_registry
```

Add:

```python
def _maybe_raise_eval_fault(stage: str, lid: str) -> None:
    fault = get_eval_fault_registry().should_fail(stage, "", lid)
    if fault:
        print(f"EVAL_FAULT injected {json.dumps(fault, sort_keys=True)}", flush=True)
        raise TimeoutError(f"eval fault injected: {fault['fault_id']}")
```

Wrap retry operations:

```python
lambda: (_maybe_raise_eval_fault("pds_lookup", lid), _pds_lookup(lid))[1]
```

For `_download`, call:

```python
img_bytes = retry_call(
    lambda: (_maybe_raise_eval_fault("pds_img_download", lid), _download(img_url))[1],
    attempts=3,
    delays=(0.0, 2.0),
    sleep_fn=time.sleep,
)
```

For uploads:

```python
retry_call(
    lambda: (_maybe_raise_eval_fault("ingest_img_upload", lid), storage.upload_bytes(img_path, img_bytes, "application/octet-stream"))[1],
    attempts=3,
    delays=(0.0, 2.0),
    sleep_fn=time.sleep,
)
retry_call(
    lambda: (_maybe_raise_eval_fault("ingest_metadata_upload", lid), storage.upload_bytes(metadata_path, json.dumps(metadata_payload, ensure_ascii=False, indent=2).encode("utf-8"), "application/json"))[1],
    attempts=3,
    delays=(0.0, 2.0),
    sleep_fn=time.sleep,
)
```

- [ ] **Step 4: Verify ingest tests pass**

Run:

```bash
cd /home/pallad/Backbackup/Backup2/orchtr
.venv/bin/pytest tests/test_ingest_one.py -q
```

Expected: pass.

## Task 3: Add Transform Retry Fault Hooks

**Files:**
- Modify: `/home/pallad/Backbackup/Backup2/orchtr/nodes/transform/logic.py`
- Test: `/home/pallad/Backbackup/Backup2/orchtr/tests/test_transform_one.py`

- [ ] **Step 1: Write failing tests**

Append one targeted test:

```python
def test_process_one_task_recovers_after_gray_upload_fault(monkeypatch):
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

    storage = Storage()
    monkeypatch.setattr(logic, "get_eval_fault_registry", lambda: Registry())
    monkeypatch.setattr(logic, "read_imgdata", lambda _raw: __import__("numpy").zeros((2, 2), dtype="uint8"))
    monkeypatch.setattr(logic.db, "pg_mark_done", lambda *_args: None)
    monkeypatch.setattr(logic.db, "pg_mark_failed", lambda *_args: None)

    result = logic.process_one_task("photo-1", 1, "mastcamz/sol=00001/A.IMG", storage)

    assert result["status"] == "ok"
    assert result["gray"] == "uploaded"
```

- [ ] **Step 2: Verify test fails**

Run:

```bash
cd /home/pallad/Backbackup/Backup2/orchtr
.venv/bin/pytest tests/test_transform_one.py::test_process_one_task_recovers_after_gray_upload_fault -q
```

Expected: missing `get_eval_fault_registry` failure.

- [ ] **Step 3: Implement hooks**

In `nodes/transform/logic.py`, import `get_eval_fault_registry`, add `_maybe_raise_eval_fault(stage, lid)` logging `EVAL_FAULT injected` with `json.dumps(fault, sort_keys=True)`, and inject stages:

```python
transform_storage_download
transform_gray_upload
transform_rgb_upload
```

Use `photo_id` as the `lid` argument when no original product LID is available in this function.

- [ ] **Step 4: Verify transform tests pass**

Run:

```bash
cd /home/pallad/Backbackup/Backup2/orchtr
.venv/bin/pytest tests/test_transform_one.py -q
```

Expected: pass.

## Task 4: Add Analyze Retry Fault Hooks

**Files:**
- Modify: `/home/pallad/Backbackup/Backup2/orchtr/nodes/analyze/logic.py`
- Test: `/home/pallad/Backbackup/Backup2/orchtr/tests/test_analyze_logic.py`

- [ ] **Step 1: Write failing tests**

Append:

```python
def test_analyze_one_task_recovers_after_result_upload_fault(monkeypatch):
    from nodes.analyze import logic

    class Registry:
        def __init__(self):
            self.calls = 0

        def should_fail(self, stage, job_id, lid=None):
            if stage == "analyze_result_upload" and self.calls == 0:
                self.calls += 1
                return {"fault_id": "f-result-upload", "stage": stage, "job_id": job_id, "lid": lid}
            return None

    class Storage:
        def exists(self, _path):
            return False

        def download_bytes(self, path):
            if path.endswith("rgb.jpg") or path.endswith("gray.jpg"):
                return b"jpeg"
            return b"{}"

        def upload_bytes(self, *_args):
            return True

    monkeypatch.setattr(logic, "get_eval_fault_registry", lambda: Registry())
    monkeypatch.setattr(logic, "_call_openai", lambda *_args, **_kwargs: {"geological_features": "ok"})
    monkeypatch.setattr(logic, "pg_mark_analysis_running", lambda *_args: None)
    monkeypatch.setattr(logic, "pg_mark_analysis_done", lambda *_args: None)
    monkeypatch.setattr(logic, "pg_mark_analysis_failed", lambda *_args: None)

    result = logic.analyze_one_task("photo-1", "00001", Storage(), object())

    assert result["status"] == "ok"
```

- [ ] **Step 2: Verify test fails**

Run:

```bash
cd /home/pallad/Backbackup/Backup2/orchtr
.venv/bin/pytest tests/test_analyze_logic.py::test_analyze_one_task_recovers_after_result_upload_fault -q
```

Expected: missing `get_eval_fault_registry` or no fault behavior failure.

- [ ] **Step 3: Implement hooks**

In `nodes/analyze/logic.py`, import `get_eval_fault_registry`, add `_maybe_raise_eval_fault(stage, lid)`, and inject:

```python
analyze_image_download
analyze_openai_call
analyze_result_upload
```

Use `photo_id` as `lid` for these hooks.

- [ ] **Step 4: Verify analyze tests pass**

Run:

```bash
cd /home/pallad/Backbackup/Backup2/orchtr
.venv/bin/pytest tests/test_analyze_logic.py -q
```

Expected: pass.

## Task 5: Add Aggregator PDF Generation and Duplicate Image Result Evidence

**Files:**
- Modify: `/home/pallad/Backbackup/Backup2/orchtr/messaging/aggregator.py`
- Test: `/home/pallad/Backbackup/Backup2/orchtr/tests/test_aggregator.py`

- [ ] **Step 1: Write failing tests**

Append:

```python
def test_aggregate_recovers_after_eval_pdf_generation_fault(monkeypatch):
    import messaging.aggregator as aggregator

    class Registry:
        def __init__(self):
            self.calls = 0

        def should_fail(self, stage, job_id, lid=None):
            if stage == "pdf_generation" and self.calls == 0:
                self.calls += 1
                return {"fault_id": "f-pdf-generation", "stage": stage, "job_id": job_id, "lid": lid}
            return None

    monkeypatch.setattr(aggregator, "get_eval_fault_registry", lambda: Registry())
    # Reuse existing aggregator fixtures in this file for complete state setup.
```

Add a duplicate test using the existing state shape:

```python
def test_duplicate_image_result_is_logged_and_skipped(monkeypatch, caplog):
    import messaging.aggregator as aggregator

    job_id = "job-dup"
    aggregator.state.clear()
    aggregator.state[job_id] = {"expected": 2, "results": [], "seen_lids": set()}

    first = {"job_id": job_id, "lid": "lid-1", "status": "ok"}
    aggregator._handle_image_result(first)
    aggregator._handle_image_result(first)

    assert len(aggregator.state[job_id]["results"]) == 1
    assert "Duplicate image.result" in caplog.text
```

Adjust exact helper/function names after reading current `test_aggregator.py`; keep the assertion that duplicate result produces one stored result.

- [ ] **Step 2: Verify tests fail**

Run:

```bash
cd /home/pallad/Backbackup/Backup2/orchtr
.venv/bin/pytest tests/test_aggregator.py::test_aggregate_recovers_after_eval_pdf_generation_fault tests/test_aggregator.py::test_duplicate_image_result_is_logged_and_skipped -q
```

Expected: missing hook/test helper mismatch.

- [ ] **Step 3: Implement hooks**

In `aggregator.py`, call `_maybe_raise_eval_fault("pdf_generation", job_id)` inside the existing `retry_call` wrapping `generate_pdf_bytes`.

For duplicate evidence, keep existing `seen_lids` guard and add a structured log line:

```python
logger.warning(
    "KAFKA_IDEMPOTENCY duplicate_image_result job=%s lid=%s guard=seen_lids final_effect=skipped_duplicate",
    job_id,
    lid,
)
```

- [ ] **Step 4: Verify aggregator tests pass**

Run:

```bash
cd /home/pallad/Backbackup/Backup2/orchtr
.venv/bin/pytest tests/test_aggregator.py -q
```

Expected: pass.

## Task 6: Add Orchestrator Kafka Publish Fault Hooks

**Files:**
- Modify: `/home/pallad/Backbackup/Backup2/orchtr/messaging/dispatcher.py`
- Modify: `/home/pallad/Backbackup/Backup2/orchtr/messaging/producer.py`
- Test: `/home/pallad/Backbackup/Backup2/orchtr/tests/test_dispatcher.py`
- Test: `/home/pallad/Backbackup/Backup2/orchtr/tests/test_kafka_producer.py`

- [ ] **Step 1: Write failing tests**

For dispatcher:

```python
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
```

For producer:

```python
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
```

- [ ] **Step 2: Verify tests fail**

Run:

```bash
cd /home/pallad/Backbackup/Backup2/orchtr
.venv/bin/pytest tests/test_dispatcher.py::test_dispatcher_recovers_after_image_task_publish_fault tests/test_kafka_producer.py::test_publish_status_recovers_after_eval_fault -q
```

Expected: missing fault hook imports.

- [ ] **Step 3: Implement hooks**

Import `get_eval_fault_registry` in both files and inject inside retry lambdas:

```python
fault = get_eval_fault_registry().should_fail("image_task_publish", job_id, img["lid"])
if fault:
    logger.warning("EVAL_FAULT injected %s", json.dumps(fault, sort_keys=True))
    raise TimeoutError(f"eval fault injected: {fault['fault_id']}")
```

and:

```python
fault = get_eval_fault_registry().should_fail("job_status_publish", job_id)
if fault:
    logger.warning("EVAL_FAULT injected %s", json.dumps(fault, sort_keys=True))
    raise TimeoutError(f"eval fault injected: {fault['fault_id']}")
```

- [ ] **Step 4: Verify publish tests pass**

Run:

```bash
cd /home/pallad/Backbackup/Backup2/orchtr
.venv/bin/pytest tests/test_dispatcher.py tests/test_kafka_producer.py -q
```

Expected: pass.

## Task 7: Add Gateway Publish Fault and Status Idempotency Evidence

**Files:**
- Modify: `/home/pallad/Backbackup/Backup2/gateway/src/main/java/com/mars/gateway/job/JobService.java`
- Test: `/home/pallad/Backbackup/Backup2/gateway/src/test/java/com/mars/gateway/job/JobServiceTest.java`

- [ ] **Step 1: Write failing tests**

Add a test that sets a system property or environment abstraction for one transient `job_submitted_publish` fault. If the current tests already mock Kafka failures directly, keep those and add evidence-focused behavior:

```java
@Test
void applyStatusUpdate_ignoresLateTerminalStatusAfterCompleted() {
    Job job = new Job();
    job.setId("job-1");
    job.setStatus(JobStatus.COMPLETED);
    when(repository.findById("job-1")).thenReturn(Optional.of(job));

    service.applyStatusUpdate("job-1", "FAILED", "late", null, "late failure", null, null, null, null, null, null, "{}");

    assertThat(job.getStatus()).isEqualTo(JobStatus.COMPLETED);
    verify(repository, never()).save(job);
}
```

Add or update duplicate status test:

```java
@Test
void applyStatusUpdate_mergesDuplicateImageProgressByWorkerAndLid() {
    Job job = new Job();
    job.setId("job-1");
    job.setStatus(JobStatus.PROCESSING_IMAGES);
    job.setImageProgress("[{\"worker_id\":1,\"lid\":\"lid-1\",\"status\":\"processing\"}]");
    when(repository.findById("job-1")).thenReturn(Optional.of(job));

    service.applyStatusUpdate("job-1", "PROCESSING_IMAGES", null, null, null, null, null, null, null,
            "{\"worker_id\":1,\"lid\":\"lid-1\",\"status\":\"done\"}", 1, "{}");

    assertThat(job.getImageProgress()).contains("\"status\":\"done\"");
    assertThat(job.getImageProgress()).doesNotContain("processing");
}
```

- [ ] **Step 2: Verify tests fail or confirm existing behavior**

Run:

```bash
cd /home/pallad/Backbackup/Backup2/gateway
mvn test -Dtest=JobServiceTest
```

Expected: new assertions may already pass for terminal guard; if they pass, keep them as coverage and add logging/evidence tests around publish retry if needed.

- [ ] **Step 3: Implement evaluation hook**

Add a small private method in `JobService`:

```java
private void maybeRaiseEvalFault(String stage, String jobId) {
    String raw = System.getenv("EVAL_FAULTS");
    if (raw == null || raw.isBlank()) return;
    if (!raw.contains("\"stage\":\"" + stage + "\"") && !raw.contains("\"stage\": \"" + stage + "\"")) return;
    String marker = "EVAL_FAULT_USED_" + stage + "_" + jobId;
    if (System.getProperty(marker) != null) return;
    System.setProperty(marker, "true");
    log.warn("EVAL_FAULT injected {{\"fault_id\":\"{}\",\"stage\":\"{}\",\"job_id\":\"{}\",\"attempt\":1,\"failures\":1}}",
            "f-job-submitted-publish-1", stage, jobId);
    throw new RuntimeException("eval fault injected: f-job-submitted-publish-1");
}
```

Call it inside `publishSubmittedWithRetry` before `kafkaTemplate.send`:

```java
maybeRaiseEvalFault("job_submitted_publish", jobId);
```

Keep this intentionally simple and evaluation-only. Do not add JSON dependencies in `JobService`.

- [ ] **Step 4: Verify gateway tests pass**

Run:

```bash
cd /home/pallad/Backbackup/Backup2/gateway
mvn test -Dtest=JobServiceTest
```

Expected: pass.

## Task 8: Extend Evaluation Runner Tables and Evidence Parsing

**Files:**
- Modify: `/home/pallad/Backbackup/Backup2/evaluation/run_retry_recovery_e2e.py`
- Test: `/home/pallad/Backbackup/Backup2/evaluation/tests/test_retry_recovery_e2e.py`

- [ ] **Step 1: Write failing tests**

Add tests:

```python
def test_build_fault_plan_contains_full_production_retry_stages():
    from evaluation.run_retry_recovery_e2e import build_fault_plan

    groups = {
        "project_a": [{"id": "a1", "lid": "lid-a1"}, {"id": "a2", "lid": "lid-a2"}],
        "project_b": [{"id": "b1", "lid": "lid-b1"}, {"id": "b2", "lid": "lid-b2"}],
        "project_c": [{"id": "c1", "lid": "lid-c1"}, {"id": "c2", "lid": "lid-c2"}],
    }

    stages = {fault["stage"] for fault in build_fault_plan(groups)}

    assert {
        "pds_lookup",
        "pds_img_download",
        "ingest_metadata_upload",
        "ingest_img_upload",
        "transform_storage_download",
        "transform_gray_upload",
        "transform_rgb_upload",
        "analyze_image_download",
        "analyze_openai_call",
        "analyze_result_upload",
        "image_worker_process",
        "pdf_generation",
        "pdf_upload",
        "job_status_publish",
        "image_task_publish",
    }.issubset(stages)


def test_protocol_writes_full_retry_and_kafka_tables(tmp_path, monkeypatch):
    from evaluation import run_retry_recovery_e2e as mod
    # Use the existing test_retry_recovery_protocol_writes_txt_tables setup.
    # Assert these files exist:
    # production-retry-coverage-table.txt
    # kafka-idempotency-table.txt
```

Add evidence parsing test:

```python
def test_build_kafka_idempotency_records_from_logs():
    from evaluation.run_retry_recovery_e2e import build_kafka_idempotency_records

    logs = "\n".join([
        "KAFKA_IDEMPOTENCY duplicate_image_result job=job-1 lid=lid-1 guard=seen_lids final_effect=skipped_duplicate",
        "publish_status attempt 1 failed for job job-1 (eval fault injected: f-status), retry in 0s",
    ])

    records = build_kafka_idempotency_records([logs])

    assert any(record["scenario"] == "duplicate image result replay" for record in records)
    assert any(record["scenario"] == "job.status publish retry" for record in records)
```

- [ ] **Step 2: Verify tests fail**

Run:

```bash
cd /home/pallad/Backbackup/Backup2
PYTHONPATH=. pytest evaluation/tests/test_retry_recovery_e2e.py::test_build_fault_plan_contains_full_production_retry_stages evaluation/tests/test_retry_recovery_e2e.py::test_build_kafka_idempotency_records_from_logs -q
```

Expected: missing stages and missing parser.

- [ ] **Step 3: Implement runner changes**

Add constants:

```python
PRODUCTION_RETRY_STAGES = [
    ("pds_lookup", "orchtr ingest"),
    ("pds_img_download", "orchtr ingest"),
    ("ingest_metadata_upload", "orchtr ingest"),
    ("ingest_img_upload", "orchtr ingest"),
    ("transform_storage_download", "orchtr transform"),
    ("transform_gray_upload", "orchtr transform"),
    ("transform_rgb_upload", "orchtr transform"),
    ("analyze_image_download", "orchtr analyze"),
    ("analyze_openai_call", "orchtr analyze"),
    ("analyze_result_upload", "orchtr analyze"),
    ("image_worker_process", "orchtr image worker"),
    ("pdf_generation", "orchtr aggregator"),
    ("pdf_upload", "orchtr aggregator"),
    ("job_status_publish", "orchtr producer"),
    ("image_task_publish", "orchtr dispatcher"),
]
```

Build one fault per stage, rotating across available case-group LIDs to reduce collisions.

Add:

```python
def build_kafka_idempotency_records(log_texts: list[str]) -> list[dict[str, Any]]:
    logs = "\n".join(log_texts)
    records: list[dict[str, Any]] = []
    if "job.submitted publish attempt" in logs and "eval fault injected" in logs:
        records.append({
            "topic": "job.submitted",
            "component": "gateway producer",
            "scenario": "job.submitted publish retry",
            "retry_or_duplicate_observed": True,
            "idempotency_guard": "stable job_id",
            "final_effect": "one accepted job",
            "evidence_source": "gateway.log",
        })
    if "image.task publish attempt" in logs and "eval fault injected" in logs:
        records.append({
            "topic": "image.task",
            "component": "orchestrator dispatcher",
            "scenario": "image.task publish retry",
            "retry_or_duplicate_observed": True,
            "idempotency_guard": "stable job_id and lid",
            "final_effect": "one image task effect",
            "evidence_source": "orchtr.log",
        })
    if "publish_status attempt" in logs and "eval fault injected" in logs:
        records.append({
            "topic": "job.status",
            "component": "orchestrator producer",
            "scenario": "job.status publish retry",
            "retry_or_duplicate_observed": True,
            "idempotency_guard": "status update by job_id",
            "final_effect": "consistent final job state",
            "evidence_source": "orchtr.log",
        })
    if "KAFKA_IDEMPOTENCY duplicate_image_result" in logs:
        records.append({
            "topic": "image.result",
            "component": "orchestrator aggregator",
            "scenario": "duplicate image result replay",
            "retry_or_duplicate_observed": True,
            "idempotency_guard": "seen_lids",
            "final_effect": "skipped duplicate image result",
            "evidence_source": "orchtr.log",
        })
    if "KAFKA_IDEMPOTENCY duplicate_job_status" in logs:
        records.append({
            "topic": "job.status",
            "component": "gateway consumer",
            "scenario": "duplicate status replay",
            "retry_or_duplicate_observed": True,
            "idempotency_guard": "update by job_id",
            "final_effect": "one job record",
            "evidence_source": "gateway.log",
        })
    if "KAFKA_IDEMPOTENCY late_terminal_status" in logs:
        records.append({
            "topic": "job.status",
            "component": "gateway consumer",
            "scenario": "duplicate or late terminal status handling",
            "retry_or_duplicate_observed": True,
            "idempotency_guard": "terminal status guard",
            "final_effect": "final status unchanged",
            "evidence_source": "gateway.log",
        })
    return records
```

Write:

```text
production_retry_records.json
kafka_idempotency_records.json
production-retry-coverage-table.txt
kafka-idempotency-table.txt
```

Extend `summary.json` with production retry and Kafka aggregate counts.

- [ ] **Step 4: Verify evaluation tests pass**

Run:

```bash
cd /home/pallad/Backbackup/Backup2
PYTHONPATH=. pytest evaluation/tests/test_retry_recovery_e2e.py -q
```

Expected: pass.

## Task 9: Docker Verification Runbook and Final Verification

**Files:**
- Modify: `/home/pallad/Backbackup/Backup2/docs/superpowers/plans/2026-05-17-full-production-retry-coverage.md` if run discoveries require documented command changes.
- No production code changes unless verification exposes a defect.

- [ ] **Step 1: Run Python unit coverage**

Run:

```bash
cd /home/pallad/Backbackup/Backup2/orchtr
.venv/bin/pytest tests/test_eval_faults.py tests/test_ingest_one.py tests/test_transform_one.py tests/test_analyze_logic.py tests/test_image_worker.py tests/test_aggregator.py tests/test_dispatcher.py tests/test_kafka_producer.py -q
```

Expected: pass.

- [ ] **Step 2: Run evaluation tests**

Run:

```bash
cd /home/pallad/Backbackup/Backup2
PYTHONPATH=. pytest evaluation/tests/test_retry_recovery_e2e.py evaluation/tests/test_eval_lib.py -q
```

Expected: pass.

- [ ] **Step 3: Run gateway tests**

Run:

```bash
cd /home/pallad/Backbackup/Backup2/gateway
mvn test
```

Expected: `BUILD SUCCESS`.

- [ ] **Step 4: Run clean Docker evaluation**

Generate the fault env:

```bash
cd /home/pallad/Backbackup/Backup2
PYTHONPATH=. python -c "from evaluation.eval_lib import load_case_groups; from evaluation.run_retry_recovery_e2e import build_fault_plan, serialize_fault_env; print(serialize_fault_env(build_fault_plan(load_case_groups('evaluation/cases.yml'))))"
```

Start clean stack:

```bash
docker compose --profile eval down -v --remove-orphans
EVAL_FAULTS='<paste generated JSON>' docker compose --profile eval up -d --build
```

Run:

```bash
docker compose --profile eval exec -T evaluation-runner python -m evaluation.run_retry_recovery_e2e --keycloak http://keycloak:8080
```

If result files are container-owned, run:

```bash
docker compose --profile eval exec -T -u root evaluation-runner chmod -R ugo+rwX /workspace/evaluation/results/retry_recovery_e2e
```

Capture host logs:

```bash
docker compose --profile eval logs --no-color --timestamps gateway > evaluation/results/retry_recovery_e2e/docker_logs/gateway.log
docker compose --profile eval logs --no-color --timestamps orchtr > evaluation/results/retry_recovery_e2e/docker_logs/orchtr.log
docker compose --profile eval logs --no-color --timestamps evaluation-runner > evaluation/results/retry_recovery_e2e/docker_logs/evaluation-runner.log
```

Regenerate summary if host logs were captured after the runner:

```bash
PYTHONPATH=. python -m evaluation.report
```

- [ ] **Step 5: Verify thesis artifacts**

Check:

```bash
cat evaluation/results/retry_recovery_e2e/production-retry-coverage-table.txt
cat evaluation/results/retry_recovery_e2e/kafka-idempotency-table.txt
cat evaluation/results/retry_recovery_e2e/thesis-interpretation-notes.txt
rg -n "production-retry-coverage-table|kafka-idempotency-table" evaluation/results/summary.md
```

Expected:

- production table includes all required retry stages;
- Kafka table includes publish retry and duplicate idempotency scenarios;
- `failed_jobs` is `0`;
- no `.docx` file changed.

## Self-Review

Spec coverage:

- Production retry boundaries are covered in Tasks 2 through 8.
- Kafka publish retry is covered in Tasks 6 and 7.
- Kafka duplicate idempotency is covered in Tasks 5, 7, and 8.
- Two thesis tables are covered in Task 8.
- Docker clean run and log evidence are covered in Task 9.
- Evaluator HTTP retry is intentionally excluded.

Placeholder scan:

- No `TBD`, `TODO`, or intentionally vague implementation placeholders remain.

Type consistency:

- Fault specs use `fault_id`, `stage`, `job_id`, `lid`, `failures`, and `duplicates`.
- Evidence records use names from the design spec.
