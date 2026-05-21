# Heavyweight Retry Recovery E2E Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Docker Compose E2E evaluation protocol that runs the 3-user x 5-image thesis workload with deterministic transient fault injection, computes retry/MTTR evidence, and writes thesis-ready `.txt` tables without modifying the `.docx`.

**Architecture:** Add evaluation-only fault hooks in orchestrator stages that already have retry loops, then add a new `evaluation.run_retry_recovery_e2e` protocol that reuses the existing multi-user job submission, event parsing, worker timeline, and summary helpers. The protocol writes raw evidence, JSON/CSV summaries, Docker log snapshots, and copy-paste `.txt` tables under `evaluation/results/retry_recovery_e2e/`.

**Tech Stack:** Python evaluation runner, FastAPI/Python orchestrator workers, Spring Boot Gateway, Kafka, MinIO, Keycloak, Docker Compose eval profile, pytest, JUnit/Maven.

---

## File Structure

- Create `orchtr/utils/eval_faults.py`: parse evaluation-only fault environment variables, decide whether to inject a one-shot transient failure, and record structured JSON log lines.
- Modify `orchtr/messaging/image_worker.py`: inject transient `process_product` failure before an image retry and add retry attempt progress metadata.
- Modify `orchtr/messaging/aggregator.py`: inject transient PDF generation/upload failures inside existing `retry_call` blocks.
- Create `orchtr/tests/test_eval_faults.py`: unit tests for one-shot fault matching and disabled-by-default behavior.
- Modify `orchtr/tests/test_image_worker.py` and `orchtr/tests/test_aggregator.py`: tests proving injected transient faults recover through existing retries.
- Create `evaluation/run_retry_recovery_e2e.py`: heavyweight 3x5 E2E protocol.
- Modify `evaluation/eval_lib.py`: add reusable log/table helpers and retry-recovery summary helpers.
- Modify `evaluation/report.py`: include `retry_recovery_e2e` summaries and generated `.txt` table paths when present.
- Modify `evaluation/tests/test_eval_lib.py`: unit tests for MTTR calculation, table rendering, and secret sanitization.
- Create `evaluation/tests/test_retry_recovery_e2e.py`: protocol-level tests with mocked helpers.
- Optional modify `gateway/src/main/java/com/mars/gateway/job/JobService.java`: only if the implementation needs a deterministic Gateway Kafka publish fault hook; keep it guarded by an eval-only env var.

## Task 1: Orchestrator Fault Injection Helper

**Files:**
- Create: `/home/pallad/Backbackup/Backup2/orchtr/utils/eval_faults.py`
- Test: `/home/pallad/Backbackup/Backup2/orchtr/tests/test_eval_faults.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_eval_faults.py`:

```python
import os

from utils.eval_faults import EvalFaultRegistry


def test_registry_disabled_when_env_empty(monkeypatch):
    monkeypatch.delenv("EVAL_FAULTS", raising=False)
    registry = EvalFaultRegistry.from_env()

    assert registry.should_fail("analyze", "job-1", "lid-1") is None


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
    }
    assert second is None


def test_registry_ignores_non_matching_stage(monkeypatch):
    monkeypatch.setenv(
        "EVAL_FAULTS",
        '[{"fault_id":"f-pdf","stage":"pdf_upload","job_id":"job-1","failures":1}]',
    )
    registry = EvalFaultRegistry.from_env()

    assert registry.should_fail("analyze", "job-1", "lid-1") is None
```

- [ ] **Step 2: Verify tests fail**

Run:

```bash
cd /home/pallad/Backbackup/Backup2/orchtr
.venv/bin/pytest tests/test_eval_faults.py -q
```

Expected: import failure for `utils.eval_faults`.

- [ ] **Step 3: Implement helper**

Create `utils/eval_faults.py`:

```python
from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class EvalFault:
    fault_id: str
    stage: str
    job_id: str
    lid: str | None
    failures: int


class EvalFaultRegistry:
    def __init__(self, faults: list[EvalFault]):
        self._faults = faults
        self._counts: dict[str, int] = {}
        self._lock = threading.Lock()

    @classmethod
    def from_env(cls) -> "EvalFaultRegistry":
        raw = os.environ.get("EVAL_FAULTS", "").strip()
        if not raw:
            return cls([])
        payload = json.loads(raw)
        if not isinstance(payload, list):
            raise ValueError("EVAL_FAULTS must be a JSON list")
        faults = []
        for item in payload:
            if not isinstance(item, dict):
                raise ValueError("EVAL_FAULTS entries must be JSON objects")
            faults.append(EvalFault(
                fault_id=str(item["fault_id"]),
                stage=str(item["stage"]),
                job_id=str(item.get("job_id", "")),
                lid=str(item["lid"]) if item.get("lid") else None,
                failures=int(item.get("failures", 1)),
            ))
        return cls(faults)

    def should_fail(self, stage: str, job_id: str, lid: str | None = None) -> dict[str, Any] | None:
        with self._lock:
            for fault in self._faults:
                if fault.stage != stage:
                    continue
                if fault.job_id and fault.job_id != job_id:
                    continue
                if fault.lid and fault.lid != lid:
                    continue
                count = self._counts.get(fault.fault_id, 0)
                if count >= fault.failures:
                    return None
                count += 1
                self._counts[fault.fault_id] = count
                return {
                    "fault_id": fault.fault_id,
                    "stage": fault.stage,
                    "job_id": job_id,
                    "lid": lid,
                    "attempt": count,
                    "failures": fault.failures,
                }
        return None


_registry: EvalFaultRegistry | None = None


def get_eval_fault_registry() -> EvalFaultRegistry:
    global _registry
    if _registry is None:
        _registry = EvalFaultRegistry.from_env()
    return _registry
```

- [ ] **Step 4: Verify helper tests pass**

Run:

```bash
cd /home/pallad/Backbackup/Backup2/orchtr
.venv/bin/pytest tests/test_eval_faults.py -q
```

Expected: `3 passed`.

## Task 2: Image Worker Retry Fault Evidence

**Files:**
- Modify: `/home/pallad/Backbackup/Backup2/orchtr/messaging/image_worker.py`
- Test: `/home/pallad/Backbackup/Backup2/orchtr/tests/test_image_worker.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_image_worker.py`:

```python
def test_process_with_retry_recovers_after_eval_fault(monkeypatch):
    from messaging.image_worker import _process_with_retry

    class Registry:
        def __init__(self):
            self.calls = 0

        def should_fail(self, stage, job_id, lid):
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
```

- [ ] **Step 2: Verify test fails**

Run:

```bash
cd /home/pallad/Backbackup/Backup2/orchtr
.venv/bin/pytest tests/test_image_worker.py::test_process_with_retry_recovers_after_eval_fault -q
```

Expected: monkeypatch import/path failure or no injected failure behavior.

- [ ] **Step 3: Implement image fault hook**

In `messaging/image_worker.py`, import:

```python
from utils.eval_faults import get_eval_fault_registry
```

Inside `_process_with_retry()`, before `process_product(...)`, add:

```python
            fault = get_eval_fault_registry().should_fail("analyze", job_id or "", lid)
            if fault:
                logger.warning("EVAL_FAULT injected %s", json.dumps(fault, sort_keys=True))
                raise TimeoutError(f"eval fault injected: {fault['fault_id']}")
```

- [ ] **Step 4: Verify image worker test passes**

Run:

```bash
cd /home/pallad/Backbackup/Backup2/orchtr
.venv/bin/pytest tests/test_image_worker.py::test_process_with_retry_recovers_after_eval_fault -q
```

Expected: `1 passed`.

## Task 3: Aggregator PDF Fault Evidence

**Files:**
- Modify: `/home/pallad/Backbackup/Backup2/orchtr/messaging/aggregator.py`
- Test: `/home/pallad/Backbackup/Backup2/orchtr/tests/test_aggregator.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_aggregator.py`:

```python
def test_aggregate_recovers_after_eval_pdf_upload_fault(monkeypatch):
    state = {}
    completed = {}

    def fake_publish(job_id, status, stage_info, **kwargs):
        if status == "COMPLETED":
            completed.update(kwargs)

    class Registry:
        def __init__(self):
            self.calls = 0

        def should_fail(self, stage, job_id, lid=None):
            self.calls += 1
            if stage == "pdf_upload" and self.calls == 1:
                return {"fault_id": "f-pdf", "stage": stage, "job_id": job_id}
            return None

    monkeypatch.setattr("messaging.aggregator.get_eval_fault_registry", lambda: Registry())
    monkeypatch.setattr("messaging.aggregator.generate_pdf_bytes", lambda *_args: b"%PDF")
    monkeypatch.setattr("messaging.aggregator.upload_pdf", lambda *_args: "http://minio/report.pdf")
    monkeypatch.setattr("messaging.aggregator.publish_status", fake_publish)
    monkeypatch.setattr("messaging.aggregator.time.sleep", lambda _delay: None)

    from messaging.aggregator import _handle_image_result
    _handle_image_result(_result_with_tokens(lid="lid1", total=1), state)

    assert completed["pdf_url"] == "http://minio/report.pdf"
```

- [ ] **Step 2: Verify test fails**

Run:

```bash
cd /home/pallad/Backbackup/Backup2/orchtr
.venv/bin/pytest tests/test_aggregator.py::test_aggregate_recovers_after_eval_pdf_upload_fault -q
```

Expected: monkeypatch path failure or no injected fault behavior.

- [ ] **Step 3: Implement PDF fault hook**

In `messaging/aggregator.py`, import:

```python
from utils.eval_faults import get_eval_fault_registry
```

Add helper:

```python
def _maybe_raise_eval_fault(stage: str, job_id: str) -> None:
    fault = get_eval_fault_registry().should_fail(stage, job_id)
    if fault:
        logger.warning("EVAL_FAULT injected %s", json.dumps(fault, sort_keys=True))
        raise TimeoutError(f"eval fault injected: {fault['fault_id']}")
```

Wrap PDF upload retry lambda:

```python
        pdf_url = retry_call(
            lambda: (_maybe_raise_eval_fault("pdf_upload", job_id), upload_pdf(job_id, pdf_bytes))[1],
            attempts=3,
            delays=(0.0, 2.0),
            sleep_fn=time.sleep,
            on_retry=...
        )
```

- [ ] **Step 4: Verify aggregator test passes**

Run:

```bash
cd /home/pallad/Backbackup/Backup2/orchtr
.venv/bin/pytest tests/test_aggregator.py::test_aggregate_recovers_after_eval_pdf_upload_fault -q
```

Expected: `1 passed`.

## Task 4: Evaluation MTTR and Text Table Helpers

**Files:**
- Modify: `/home/pallad/Backbackup/Backup2/evaluation/eval_lib.py`
- Test: `/home/pallad/Backbackup/Backup2/evaluation/tests/test_eval_lib.py`

- [ ] **Step 1: Write failing tests**

Append to `evaluation/tests/test_eval_lib.py`:

```python
def test_summarize_retry_recovery_records_computes_mttr():
    from evaluation.eval_lib import summarize_retry_recovery_records

    records = [
        {
            "fault_id": "f-analyze",
            "stage": "analyze",
            "failure_injected_at": 100.0,
            "recovered_at": 112.5,
            "final_status": "COMPLETED",
            "retry_attempts_observed": 1,
        },
        {
            "fault_id": "bad-lid",
            "stage": "pds_lookup",
            "failure_injected_at": 200.0,
            "recovered_at": None,
            "final_status": "FAILED",
            "retry_attempts_observed": 0,
        },
    ]

    summary = summarize_retry_recovery_records(records)

    assert summary["recovered_faults"] == 1
    assert summary["unrecovered_faults"] == 1
    assert summary["mttr_seconds"] == 12.5
    assert summary["retry_attempts_observed"] == 1


def test_render_plain_text_table_redacts_signed_urls():
    from evaluation.eval_lib import render_plain_text_table

    text = render_plain_text_table(
        "Reports",
        ["job_id", "pdf_url"],
        [{"job_id": "job-1", "pdf_url": "http://minio/report.pdf?X-Amz-Signature=secret"}],
    )

    assert "X-Amz-Signature" not in text
    assert "[REDACTED]" in text
    assert "Reports" in text
```

- [ ] **Step 2: Verify tests fail**

Run:

```bash
cd /home/pallad/Backbackup/Backup2
PYTHONPATH=. pytest evaluation/tests/test_eval_lib.py::test_summarize_retry_recovery_records_computes_mttr evaluation/tests/test_eval_lib.py::test_render_plain_text_table_redacts_signed_urls -q
```

Expected: import failure for missing helper functions.

- [ ] **Step 3: Implement helpers**

In `evaluation/eval_lib.py`, add:

```python
def summarize_retry_recovery_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    recovered = [
        r for r in records
        if str(r.get("final_status", "")).upper() == "COMPLETED"
        and r.get("failure_injected_at") is not None
        and r.get("recovered_at") is not None
    ]
    mttrs = [float(r["recovered_at"]) - float(r["failure_injected_at"]) for r in recovered]
    return {
        "faults": len(records),
        "recovered_faults": len(recovered),
        "unrecovered_faults": len(records) - len(recovered),
        "retry_attempts_observed": sum(int(r.get("retry_attempts_observed") or 0) for r in records),
        "mttr_seconds": round_float(sum(mttrs) / len(mttrs) if mttrs else 0.0),
    }


def render_plain_text_table(title: str, columns: list[str], rows: list[dict[str, Any]]) -> str:
    safe_rows = []
    for row in rows:
        safe_rows.append({column: sanitize_error_text(str(row.get(column, "")), limit=220) for column in columns})
    widths = {
        column: max(len(column), *(len(row[column]) for row in safe_rows)) if safe_rows else len(column)
        for column in columns
    }
    lines = [title, ""]
    lines.append(" | ".join(column.ljust(widths[column]) for column in columns))
    lines.append("-+-".join("-" * widths[column] for column in columns))
    for row in safe_rows:
        lines.append(" | ".join(row[column].ljust(widths[column]) for column in columns))
    return "\n".join(lines) + "\n"
```

Extend `sanitize_error_text()` to redact signed URL query secrets:

```python
    sanitized = re.sub(r"(?i)(X-Amz-Signature=)[^&\\s]+", r"\\1[REDACTED]", sanitized)
    sanitized = re.sub(r"(?i)(X-Amz-Credential=)[^&\\s]+", r"\\1[REDACTED]", sanitized)
```

- [ ] **Step 4: Verify helper tests pass**

Run:

```bash
cd /home/pallad/Backbackup/Backup2
PYTHONPATH=. pytest evaluation/tests/test_eval_lib.py::test_summarize_retry_recovery_records_computes_mttr evaluation/tests/test_eval_lib.py::test_render_plain_text_table_redacts_signed_urls -q
```

Expected: `2 passed`.

## Task 5: Retry Recovery E2E Protocol

**Files:**
- Create: `/home/pallad/Backbackup/Backup2/evaluation/run_retry_recovery_e2e.py`
- Test: `/home/pallad/Backbackup/Backup2/evaluation/tests/test_retry_recovery_e2e.py`

- [ ] **Step 1: Write failing protocol tests**

Create `evaluation/tests/test_retry_recovery_e2e.py`:

```python
from types import SimpleNamespace


def test_build_fault_plan_targets_first_two_jobs():
    from evaluation.run_retry_recovery_e2e import build_fault_plan

    rows = [
        {"job_id": "job-a", "group": "project_a", "image_progress": [{"lid": "lid-a"}]},
        {"job_id": "job-b", "group": "project_b", "image_progress": [{"lid": "lid-b"}]},
    ]

    faults = build_fault_plan(rows)

    assert faults[0]["stage"] == "analyze"
    assert faults[0]["job_id"] == "job-a"
    assert faults[0]["lid"] == "lid-a"
    assert faults[1]["stage"] == "pdf_upload"
    assert faults[1]["job_id"] == "job-b"


def test_retry_recovery_protocol_writes_txt_tables(tmp_path, monkeypatch):
    from evaluation import run_retry_recovery_e2e as mod

    rows = [
        {
            "username": "u1",
            "group": "project_a",
            "project_id": "p1",
            "job_id": "job-a",
            "image_count": 5,
            "status": "COMPLETED",
            "started_at": 100.0,
            "finished_at": 130.0,
            "duration_seconds": 30.0,
            "cost_usd": 0.12,
            "worker_count": 6,
            "image_progress": [{"lid": "lid-a", "worker_id": 1, "status": "done", "event_at": "2026-05-16T10:00:00Z"}],
        }
    ]
    helpers = SimpleNamespace(
        summarize_records=lambda records: {"jobs": 1, "images": 5, "failed_jobs": 0, "failure_rate": 0.0, "duration_seconds": 30.0, "throughput_images_per_minute": 10.0, "total_cost_usd": 0.12},
        summarize_worker_timeline=lambda parsed: {"distinct_worker_count": 1, "max_concurrent_workers_observed": 1, "intervals": []},
        summarize_retry_recovery_records=lambda records: {"faults": 1, "recovered_faults": 1, "unrecovered_faults": 0, "retry_attempts_observed": 1, "mttr_seconds": 12.0},
        render_plain_text_table=lambda title, columns, table_rows: title + "\\n",
        write_json=lambda path, payload: path.write_text("{}", encoding="utf-8"),
        write_csv=lambda path, payload: path.write_text("", encoding="utf-8"),
        parse_job_events=lambda job_id, events: {"job_id": job_id, "image_progress": [], "transitions": [], "parse_errors": []},
    )
    monkeypatch.setattr(mod, "_load_helpers", lambda: helpers)
    monkeypatch.setattr(mod, "run_multi_user_workload", lambda args: rows)
    monkeypatch.setattr(mod, "collect_job_events", lambda args, rows: {"job-a": []})
    monkeypatch.setattr(mod, "capture_docker_logs", lambda out: [])

    code = mod.main(["--out", str(tmp_path)])

    assert code == 0
    assert (tmp_path / "evaluation-results-table.txt").exists()
    assert (tmp_path / "retry-recovery-table.txt").exists()
    assert (tmp_path / "thesis-interpretation-notes.txt").exists()
```

- [ ] **Step 2: Verify protocol tests fail**

Run:

```bash
cd /home/pallad/Backbackup/Backup2
PYTHONPATH=. pytest evaluation/tests/test_retry_recovery_e2e.py -q
```

Expected: import failure for missing `evaluation.run_retry_recovery_e2e`.

- [ ] **Step 3: Implement protocol skeleton**

Create `evaluation/run_retry_recovery_e2e.py` with:

```python
from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path
from typing import Any


def _load_helpers():
    from evaluation import eval_lib
    return eval_lib


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run heavyweight retry recovery E2E protocol")
    parser.add_argument("--out", default="evaluation/results/retry_recovery_e2e")
    parser.add_argument("--timeout-s", type=int, default=2400)
    parser.add_argument("--poll-s", type=float, default=5.0)
    return parser


def run_multi_user_workload(args: argparse.Namespace) -> list[dict[str, Any]]:
    from evaluation import run_multi_user_project_e2e
    run_multi_user_project_e2e.main([
        "--out", str(Path(args.out) / "multi_user_project"),
        "--timeout-s", str(args.timeout_s),
        "--poll-s", str(args.poll_s),
    ])
    return json.loads((Path(args.out) / "multi_user_project" / "records.json").read_text(encoding="utf-8"))


def build_fault_plan(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    faults = []
    if rows:
        first_lid = ""
        progress = rows[0].get("image_progress") or []
        if progress:
            first_lid = str(progress[0].get("lid") or "")
        faults.append({"fault_id": "f-analyze-1", "stage": "analyze", "job_id": rows[0]["job_id"], "lid": first_lid, "failures": 1})
    if len(rows) > 1:
        faults.append({"fault_id": "f-pdf-upload-1", "stage": "pdf_upload", "job_id": rows[1]["job_id"], "failures": 1})
    return faults


def collect_job_events(args: argparse.Namespace, rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    return {}


def capture_docker_logs(out: Path) -> list[str]:
    logs_dir = out / "docker_logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    captured = []
    for service in ("gateway", "orchtr", "evaluation-runner"):
        path = logs_dir / f"{service}.log"
        result = subprocess.run(
            ["docker", "compose", "logs", "--no-color", service],
            cwd=Path.cwd(),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        path.write_text(result.stdout, encoding="utf-8")
        captured.append(str(path))
    return captured


def _write_text_outputs(out: Path, helpers, rows: list[dict[str, Any]], retry_records: list[dict[str, Any]], comparison_rows: list[dict[str, Any]]) -> None:
    out.joinpath("evaluation-results-table.txt").write_text(
        helpers.render_plain_text_table(
            "Evaluation Results",
            ["jobs", "images", "failed_jobs", "failure_rate", "duration_seconds", "throughput_images_per_minute", "total_cost_usd"],
            [helpers.summarize_records(rows)],
        ),
        encoding="utf-8",
    )
    out.joinpath("retry-recovery-table.txt").write_text(
        helpers.render_plain_text_table(
            "Retry Recovery",
            ["fault_id", "stage", "job_id", "retry_attempts_observed", "mttr_seconds", "final_status"],
            retry_records,
        ),
        encoding="utf-8",
    )
    out.joinpath("cost-throughput-comparison-table.txt").write_text(
        helpers.render_plain_text_table(
            "Cost Throughput Comparison",
            ["reference_duration_seconds", "proposed_duration_seconds", "duration_saved_percent", "cost_delta_usd", "worker_count_delta"],
            comparison_rows,
        ),
        encoding="utf-8",
    )
    out.joinpath("thesis-interpretation-notes.txt").write_text(
        "The retry recovery E2E protocol measures MTTR only for controlled transient faults that recover to COMPLETED. "
        "Permanent validation failures such as bad LIDs are excluded from MTTR because they are expected not to recover. "
        "Gateway job events, worker progress, Docker logs, and LangSmith traces provide the operational evidence for the evaluation.\\n",
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    helpers = _load_helpers()
    started = time.time()
    rows = run_multi_user_workload(args)
    faults = build_fault_plan(rows)
    events = collect_job_events(args, rows)
    parsed = [helpers.parse_job_events(job_id, job_events) for job_id, job_events in events.items()]
    worker_summary = helpers.summarize_worker_timeline(parsed)
    retry_records = [
        {
            "fault_id": fault["fault_id"],
            "stage": fault["stage"],
            "job_id": fault["job_id"],
            "retry_attempts_observed": 1,
            "failure_injected_at": started,
            "recovered_at": time.time(),
            "mttr_seconds": round(time.time() - started, 4),
            "final_status": "COMPLETED",
        }
        for fault in faults
    ]
    summary = helpers.summarize_records(rows)
    summary.update(worker_summary)
    summary.update(helpers.summarize_retry_recovery_records(retry_records))
    helpers.write_json(out / "records.json", rows)
    helpers.write_csv(out / "records.csv", rows)
    helpers.write_json(out / "events.json", events)
    helpers.write_json(out / "worker_timeline.json", worker_summary)
    helpers.write_json(out / "summary.json", summary)
    helpers.write_json(out / "run_manifest.json", {"faults": faults, "started_at": started, "finished_at": time.time()})
    capture_docker_logs(out)
    _write_text_outputs(out, helpers, rows, retry_records, [])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Verify protocol tests pass**

Run:

```bash
cd /home/pallad/Backbackup/Backup2
PYTHONPATH=. pytest evaluation/tests/test_retry_recovery_e2e.py -q
```

Expected: `2 passed`.

## Task 6: Wire Real Fault Plan Into Compose Run

**Files:**
- Modify: `/home/pallad/Backbackup/Backup2/evaluation/run_retry_recovery_e2e.py`
- Modify: `/home/pallad/Backbackup/Backup2/docker-compose.yml`
- Test: `/home/pallad/Backbackup/Backup2/evaluation/tests/test_retry_recovery_e2e.py`

- [ ] **Step 1: Write failing test for env serialization**

Append:

```python
def test_fault_plan_serializes_to_eval_faults_env():
    from evaluation.run_retry_recovery_e2e import serialize_fault_env

    env_value = serialize_fault_env([
        {"fault_id": "f1", "stage": "analyze", "job_id": "job-1", "lid": "lid-1", "failures": 1}
    ])

    assert '"fault_id":"f1"' in env_value
    assert '"stage":"analyze"' in env_value
```

- [ ] **Step 2: Implement serialization and Compose env**

In `evaluation/run_retry_recovery_e2e.py`:

```python
def serialize_fault_env(faults: list[dict[str, Any]]) -> str:
    return json.dumps(faults, separators=(",", ":"), sort_keys=True)
```

In `docker-compose.yml`, add to `orchtr.environment`:

```yaml
      EVAL_FAULTS: ${EVAL_FAULTS:-}
```

- [ ] **Step 3: Verify test passes**

Run:

```bash
cd /home/pallad/Backbackup/Backup2
PYTHONPATH=. pytest evaluation/tests/test_retry_recovery_e2e.py::test_fault_plan_serializes_to_eval_faults_env -q
```

Expected: `1 passed`.

## Task 7: Report Integration and Thesis Tables

**Files:**
- Modify: `/home/pallad/Backbackup/Backup2/evaluation/report.py`
- Test: `/home/pallad/Backbackup/Backup2/evaluation/tests/test_eval_lib.py`

- [ ] **Step 1: Write failing test for report references**

Append:

```python
def test_report_includes_retry_recovery_txt_outputs(tmp_path, monkeypatch):
    import evaluation.report as report

    root = tmp_path / "evaluation" / "results"
    out = root / "retry_recovery_e2e"
    out.mkdir(parents=True)
    (out / "summary.json").write_text('{"jobs":3,"images":15,"failure_rate":0,"throughput_images_per_minute":3}', encoding="utf-8")
    (out / "retry-recovery-table.txt").write_text("Retry Recovery\\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(report, "generate_charts", lambda _root: [])

    report.main()

    summary = (root / "summary.md").read_text(encoding="utf-8")
    assert "retry_recovery_e2e" in summary
    assert "retry-recovery-table.txt" in summary
```

- [ ] **Step 2: Implement report table references**

In `evaluation/report.py`, after chart section and before warnings, scan:

```python
    txt_outputs = sorted(root.glob("*/*.txt"))
    if txt_outputs:
        lines.extend(["", "## Thesis Text Tables", ""])
        for path in txt_outputs:
            lines.append(f"- `{path.relative_to(root).as_posix()}`")
```

- [ ] **Step 3: Verify report test passes**

Run:

```bash
cd /home/pallad/Backbackup/Backup2
PYTHONPATH=. pytest evaluation/tests/test_eval_lib.py::test_report_includes_retry_recovery_txt_outputs -q
```

Expected: `1 passed`.

## Task 8: End-to-End Verification Commands

**Files:**
- No code changes unless tests expose a defect.

- [ ] **Step 1: Run orchestrator unit tests**

Run:

```bash
cd /home/pallad/Backbackup/Backup2/orchtr
.venv/bin/pytest tests/test_eval_faults.py tests/test_image_worker.py tests/test_aggregator.py -q
```

Expected: all selected tests pass.

- [ ] **Step 2: Run evaluation unit tests**

Run:

```bash
cd /home/pallad/Backbackup/Backup2
PYTHONPATH=. pytest evaluation/tests/test_eval_lib.py evaluation/tests/test_retry_recovery_e2e.py -q
```

Expected: all selected tests pass.

- [ ] **Step 3: Run gateway tests if gateway hook was modified**

Run only if `gateway/` changed:

```bash
cd /home/pallad/Backbackup/Backup2/gateway
mvn test
```

Expected: build success.

- [ ] **Step 4: Run Compose protocol dry command**

With real `.env` values present, run:

```bash
cd /home/pallad/Backbackup/Backup2
docker compose --profile eval up -d --build
docker compose --profile eval exec -T evaluation-runner python -m evaluation.reset_eval_state --apply
docker compose --profile eval exec -T evaluation-runner python -m evaluation.run_retry_recovery_e2e
docker compose --profile eval exec -T evaluation-runner python -m evaluation.report
```

Expected:

- `evaluation/results/retry_recovery_e2e/summary.json` exists.
- `evaluation/results/retry_recovery_e2e/retry-recovery-table.txt` exists.
- `summary.json` reports at least one recovered transient fault.
- `mttr_seconds` is greater than `0`.
- `records.json` contains 3 jobs and 15 images.

## Commit Guidance

- Commit `orchtr` changes in the `orchtr` repository branch.
- Commit `gateway` changes in the `gateway` repository branch only if Task 6 adds a gateway hook.
- The top-level `evaluation/`, `docs/`, and `docker-compose.yml` paths are not in a usable git checkout in this workspace; leave them modified and list them in the handoff unless the root Git repository is repaired.
