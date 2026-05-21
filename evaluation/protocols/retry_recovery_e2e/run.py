from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, NamedTuple

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

REQUIRED_HELPERS = (
    "load_case_groups",
    "parse_job_events",
    "render_plain_text_table",
    "summarize_records",
    "summarize_retry_recovery_records",
    "summarize_worker_timeline",
    "write_csv",
    "write_json",
)

PRODUCTION_RETRY_COVERAGE = [
    ("pds_lookup", "ingest"),
    ("pds_img_download", "ingest"),
    ("ingest_metadata_upload", "ingest"),
    ("ingest_img_upload", "ingest"),
    ("transform_storage_download", "transform"),
    ("transform_gray_upload", "transform"),
    ("transform_rgb_upload", "transform"),
    ("analyze_image_download", "analyze"),
    ("analyze_openai_call", "analyze"),
    ("analyze_result_upload", "analyze"),
    ("image_worker_process", "image worker"),
    ("pdf_generation", "aggregator"),
    ("pdf_upload", "aggregator"),
    ("job_status_publish", "orchestrator producer"),
    ("image_task_publish", "orchestrator dispatcher"),
]

LID_SCOPED_STAGES = {
    "pds_lookup",
    "pds_img_download",
    "ingest_metadata_upload",
    "ingest_img_upload",
    "image_worker_process",
    "image_task_publish",
    "duplicate_image_result",
    "duplicate_job_status",
}

KAFKA_IDEMPOTENCY_COVERAGE = [
    {
        "topic": "job.submitted",
        "component": "gateway producer",
        "scenario": "transient publish failure",
        "stage": "job_submitted_publish",
        "idempotency_guard": "producer retry",
        "final_effect": "job submitted once after retry",
    },
    {
        "topic": "image.task",
        "component": "orchestrator dispatcher",
        "scenario": "transient publish failure",
        "stage": "image_task_publish",
        "idempotency_guard": "producer retry",
        "final_effect": "image task published after retry",
    },
    {
        "topic": "job.status",
        "component": "orchestrator producer",
        "scenario": "transient publish failure",
        "stage": "job_status_publish",
        "idempotency_guard": "producer retry",
        "final_effect": "status published after retry",
    },
    {
        "topic": "image.result",
        "component": "orchestrator aggregator",
        "scenario": "duplicate image result replay",
        "marker": "KAFKA_IDEMPOTENCY duplicate_image_result",
        "idempotency_guard": "seen_lids",
        "final_effect": "skipped_duplicate",
    },
    {
        "topic": "job.status",
        "component": "gateway consumer",
        "scenario": "duplicate status replay",
        "marker": "KAFKA_IDEMPOTENCY duplicate_job_status",
        "idempotency_guard": "update_by_job_id",
        "final_effect": "one_job_record",
    },
    {
        "topic": "job.status",
        "component": "gateway consumer",
        "scenario": "duplicate or late terminal status handling",
        "marker": "KAFKA_IDEMPOTENCY late_terminal_status",
        "idempotency_guard": "terminal_status",
        "final_effect": "final_status_unchanged",
    },
]


class Helpers(NamedTuple):
    load_case_groups: Callable[[str | Path], dict[str, list[dict[str, Any]]]]
    parse_job_events: Callable[[str, list[dict[str, Any]]], dict[str, Any]]
    render_plain_text_table: Callable[[str, list[str], list[dict[str, Any]]], str]
    summarize_records: Callable[[list[dict[str, Any]]], dict[str, Any]]
    summarize_retry_recovery_records: Callable[[list[dict[str, Any]]], dict[str, Any]]
    summarize_worker_timeline: Callable[[list[dict[str, Any]]], dict[str, Any]]
    write_csv: Callable[[str | Path, list[dict[str, Any]]], None]
    write_json: Callable[[str | Path, Any], None]


def _load_helpers() -> Helpers:
    from evaluation import eval_lib

    missing = [name for name in REQUIRED_HELPERS if not hasattr(eval_lib, name)]
    if missing:
        joined = ", ".join(missing)
        raise RuntimeError(f"evaluation.eval_lib is missing required helper(s): {joined}")
    return Helpers(*(getattr(eval_lib, name) for name in REQUIRED_HELPERS))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run retry recovery E2E protocol")
    parser.add_argument("--cases", default="evaluation/cases.yml")
    parser.add_argument("--gateway", default=os.environ.get("GATEWAY_URL", "http://gateway:8080"))
    parser.add_argument("--keycloak", default=os.environ.get("KEYCLOAK_URL", "http://keycloak:8080"))
    parser.add_argument("--realm", default=os.environ.get("KEYCLOAK_REALM", "pds4cloud"))
    parser.add_argument("--client-id", default=os.environ.get("KEYCLOAK_CLIENT_ID", "react-client-certedu-api"))
    parser.add_argument("--users", default=os.environ.get("EVAL_USERS", "researcher,researcher-2,researcher-3"))
    parser.add_argument("--admin-username", default="")
    parser.add_argument("--model", default=os.environ.get("OPENAI_MODEL", "gpt-4o"))
    parser.add_argument("--out", default="evaluation/protocols/retry_recovery_e2e/results")
    parser.add_argument("--timeout-s", type=int, default=2400)
    parser.add_argument("--poll-s", type=float, default=5.0)
    return parser


def serialize_fault_env(fault_plan: list[dict[str, Any]]) -> str:
    return json.dumps(fault_plan, separators=(",", ":"), sort_keys=True)


def run_multi_user_workload(args: argparse.Namespace, fault_plan: list[dict[str, Any]]) -> list[dict[str, Any]]:
    from evaluation.protocols.multi_user_project import run as run_multi_user_project_e2e

    out = Path(args.out) / "multi_user_project"
    child_args = [
        "--out",
        str(out),
        "--timeout-s",
        str(args.timeout_s),
        "--poll-s",
        str(args.poll_s),
        "--cases",
        str(args.cases),
        "--gateway",
        str(args.gateway),
        "--keycloak",
        str(args.keycloak),
        "--realm",
        str(args.realm),
        "--client-id",
        str(args.client_id),
        "--users",
        str(args.users),
    ]
    if args.admin_username:
        child_args.extend(["--admin-username", str(args.admin_username)])
    child_args.extend(["--model", str(args.model)])
    previous_faults = os.environ.get("EVAL_FAULTS")
    os.environ["EVAL_FAULTS"] = serialize_fault_env(fault_plan)
    try:
        code = run_multi_user_project_e2e.main(child_args)
    finally:
        if previous_faults is None:
            os.environ.pop("EVAL_FAULTS", None)
        else:
            os.environ["EVAL_FAULTS"] = previous_faults
    records_path = out / "records.json"
    if not records_path.exists():
        raise RuntimeError(f"multi-user workload did not write {records_path}")
    rows = json.loads(records_path.read_text(encoding="utf-8"))
    if code != 0:
        raise RuntimeError(f"multi-user workload failed with exit code {code}")
    if not isinstance(rows, list):
        raise RuntimeError(f"multi-user workload wrote invalid records to {records_path}")
    return rows


def build_fault_plan(case_groups: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    selected = list(case_groups.items())
    if not selected:
        return []

    def group_at(index: int) -> tuple[str, list[dict[str, Any]]]:
        return selected[index % len(selected)]

    def lid_for(cases: list[dict[str, Any]]) -> str | None:
        return str(cases[0].get("lid")) if cases and cases[0].get("lid") else None

    faults = []
    for index, (stage, _component) in enumerate(PRODUCTION_RETRY_COVERAGE):
        group, cases = group_at(index)
        fault = {
            "fault_id": f"f-{stage.replace('_', '-')}-1",
            "stage": stage,
            "job_id": "",
            "group": group,
            "failures": 1,
        }
        lid = lid_for(cases)
        if stage in LID_SCOPED_STAGES and lid:
            fault["lid"] = lid
        faults.append(fault)

    for index, stage in enumerate(("job_submitted_publish", "duplicate_image_result", "duplicate_job_status", "late_terminal_status"), start=len(faults)):
        group, cases = group_at(index)
        fault = {
            "fault_id": f"f-{stage.replace('_', '-')}-1",
            "stage": stage,
            "job_id": "",
            "group": group,
        }
        lid = lid_for(cases)
        if stage in LID_SCOPED_STAGES and lid:
            fault["lid"] = lid
        if stage.startswith("duplicate") or stage == "late_terminal_status":
            fault["duplicates"] = 1
        else:
            fault["failures"] = 1
        faults.append(fault)
    return faults


def collect_job_events(args: argparse.Namespace, rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    events_path = Path(args.out) / "multi_user_project" / "events.json"
    if not events_path.exists():
        return {}
    loaded = json.loads(events_path.read_text(encoding="utf-8"))
    if not isinstance(loaded, list):
        return {}

    events_by_job: dict[str, list[dict[str, Any]]] = {}
    for item in loaded:
        if not isinstance(item, dict):
            continue
        job_id = item.get("job_id")
        if not job_id:
            continue
        events_by_job.setdefault(str(job_id), []).append(item)
    return events_by_job


def capture_docker_logs(out: str | Path) -> list[dict[str, Any]]:
    logs_dir = Path(out) / "docker_logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    manifests = []
    services = ("gateway", "orchtr", "evaluation-runner")
    for service in services:
        command = ["docker", "compose", "logs", "--no-color", "--timestamps", service]
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=120, check=False)
            output = (result.stdout or "") + (result.stderr or "")
            returncode = result.returncode
        except Exception as exc:
            output = f"docker compose logs failed for {service}: {exc}\n"
            returncode = 127
        path = logs_dir / f"{service}.log"
        path.write_text(output, encoding="utf-8")
        manifests.append({"service": service, "path": str(path), "returncode": returncode})
    return manifests


def _parse_docker_timestamp(line: str) -> float | None:
    match = re.search(r"\b(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d+))?Z\b", line)
    if not match:
        return None
    fraction = (match.group(2) or "")[:6].ljust(6, "0")
    value = f"{match.group(1)}.{fraction}+00:00"
    return datetime.fromisoformat(value).timestamp()


def _timestamped_log_lines(log_texts: list[str] | None) -> list[tuple[float, str]]:
    lines = []
    for text in log_texts or []:
        for line in text.splitlines():
            ts = _parse_docker_timestamp(line)
            if ts is not None:
                lines.append((ts, line))
    return sorted(lines, key=lambda item: item[0])


def _parse_injected_fault_payload(line: str) -> dict[str, Any]:
    marker = "EVAL_FAULT injected"
    if marker not in line:
        return {}
    payload_text = line.split(marker, 1)[1].strip()
    start = payload_text.find("{")
    if start < 0:
        return {}
    try:
        payload = json.loads(payload_text[start:])
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _component_recovery_match(stage: str, fault: dict[str, Any], line: str) -> tuple[bool, str]:
    lid = str(fault.get("lid") or "")
    job_id = str(fault.get("job_id") or "")

    if stage == "pds_lookup":
        return "ingest_one: sol=" in line, "PDS product resolved"
    if stage == "pds_img_download":
        return "Downloaded:" in line or "Uploaded:" in line, "PDS image downloaded"
    if stage == "ingest_metadata_upload":
        return "Uploaded metadata:" in line, "metadata uploaded"
    if stage == "ingest_img_upload":
        return "Uploaded:" in line and "Uploaded metadata:" not in line, "image uploaded"
    if stage.startswith("transform_"):
        return "OK photo_id=" in line and (not lid or lid in line), "transform completed"
    if stage == "analyze_image_download":
        return (
            ("stage\": \"analyze_openai_call\"" in line or "\"stage\":\"analyze_openai_call\"" in line)
            and "EVAL_FAULT injected" in line
        ) or ("OK: uploaded analysis" in line and (not lid or lid in line)), "analysis advanced after image download"
    if stage == "analyze_openai_call":
        return "OK: uploaded analysis" in line and (not lid or lid in line), "OpenAI call and analysis upload completed"
    if stage == "analyze_result_upload":
        return "OK: uploaded analysis" in line and (not lid or lid in line), "analysis result uploaded"
    if stage == "image_worker_process":
        return "OK: uploaded analysis" in line, "image worker process completed"
    if stage == "pdf_generation":
        return (
            "stage\": \"pdf_upload\"" in line or "\"stage\":\"pdf_upload\"" in line or "PDF upload attempt" in line
        ) and (not job_id or job_id in line), "next retry boundary started"
    if stage == "pdf_upload":
        return "status=COMPLETED" in line and (not job_id or job_id in line), "completed status observed"
    if stage == "job_status_publish":
        return "JOB STATUS DEBUG updated job=" in line and (not job_id or job_id in line), "gateway consumed status"
    if stage == "image_task_publish":
        return "ingest_one: fetching metadata for" in line and (not lid or lid in line), "image task consumed"

    return False, ""


def _build_component_retry_records(
    faults: list[dict[str, Any]],
    log_texts: list[str] | None = None,
) -> list[dict[str, Any]]:
    lines = _timestamped_log_lines(log_texts)
    records = []
    for fault in faults:
        stage = str(fault.get("stage") or "")
        if stage not in {item[0] for item in PRODUCTION_RETRY_COVERAGE}:
            continue
        fault_id = str(fault.get("fault_id") or "")
        injected_index = None
        injected_at = None
        injected_payload: dict[str, Any] = {}
        for index, (ts, line) in enumerate(lines):
            if "EVAL_FAULT injected" in line and fault_id in line:
                injected_index = index
                injected_at = ts
                injected_payload = _parse_injected_fault_payload(line)
                break

        recovery_at = None
        recovery_signal = ""
        recovery_line = ""
        if injected_index is not None:
            effective_fault = {**fault, **injected_payload}
            for ts, line in lines[injected_index + 1:]:
                matched, signal = _component_recovery_match(stage, effective_fault, line)
                if matched:
                    recovery_at = ts
                    recovery_signal = signal
                    recovery_line = line
                    break

        component_recovery_seconds = None
        if injected_at is not None and recovery_at is not None:
            component_recovery_seconds = round(recovery_at - injected_at, 4)
        records.append({
            "stage": stage,
            "component": dict(PRODUCTION_RETRY_COVERAGE).get(stage, ""),
            "fault_id": fault_id,
            "component_recovered": component_recovery_seconds is not None,
            "component_recovery_seconds": component_recovery_seconds,
            "failure_injected_at": injected_at,
            "component_recovered_at": recovery_at,
            "recovery_signal": recovery_signal,
            "evidence_source": "docker_logs" if injected_at is not None else "missing",
            "recovery_evidence": recovery_line[:500] if recovery_line else "",
        })
    return records


def _completed_row_for_fault(rows: list[dict[str, Any]], fault: dict[str, Any]) -> dict[str, Any] | None:
    group = fault.get("group")
    job_id = fault.get("job_id")
    for row in rows:
        if group and row.get("group") != group:
            continue
        if job_id and row.get("job_id") != job_id:
            continue
        if str(row.get("status", "")).upper() == "COMPLETED":
            return row
    return None


def _build_retry_records(
    rows: list[dict[str, Any]],
    faults: list[dict[str, Any]],
    log_texts: list[str] | None = None,
) -> list[dict[str, Any]]:
    logs = "\n".join(log_texts or [])
    retry_records = []
    for fault in faults:
        fault_id = str(fault.get("fault_id"))
        injected_line = next(
            (line for line in logs.splitlines() if "EVAL_FAULT injected" in line and fault_id in line),
            None,
        )
        retry_attempts = sum(
            1
            for line in logs.splitlines()
            if f"eval fault injected: {fault_id}" in line
        )
        injection_attempts = sum(
            1
            for line in logs.splitlines()
            if "EVAL_FAULT injected" in line and fault_id in line
        )
        retry_attempts = max(retry_attempts, injection_attempts)
        injected_at = _parse_docker_timestamp(injected_line) if injected_line else None
        completed_row = _completed_row_for_fault(rows, fault) if injected_at is not None else None
        recovered_at = float(completed_row["finished_at"]) if completed_row and completed_row.get("finished_at") is not None else None
        retry_records.append({
            **fault,
            "failure_injected_at": injected_at,
            "recovered_at": recovered_at,
            "final_status": "COMPLETED" if recovered_at is not None else "PENDING_EVIDENCE",
            "retry_attempts_observed": retry_attempts,
        })
    return retry_records


def _build_production_retry_records(
    rows: list[dict[str, Any]],
    faults: list[dict[str, Any]],
    log_texts: list[str] | None = None,
) -> list[dict[str, Any]]:
    faults_by_stage = {str(fault.get("stage")): fault for fault in faults}
    records = []
    for stage, component in PRODUCTION_RETRY_COVERAGE:
        fault = faults_by_stage.get(stage, {"stage": stage, "fault_id": ""})
        retry = _build_retry_records(rows, [fault], log_texts)[0]
        injected_at = retry.get("failure_injected_at")
        recovered_at = retry.get("recovered_at")
        recovered = (
            str(retry.get("final_status", "")).upper() == "COMPLETED"
            and injected_at is not None
            and recovered_at is not None
            and float(recovered_at) > float(injected_at)
            and int(retry.get("retry_attempts_observed") or 0) > 0
        )
        mttr_seconds = None
        if injected_at is not None and recovered_at is not None:
            mttr_seconds = round(float(recovered_at) - float(injected_at), 4)
        records.append({
            "stage": stage,
            "component": component,
            "fault_id": retry.get("fault_id", ""),
            "attempts_observed": int(retry.get("retry_attempts_observed") or 0),
            "recovered": recovered,
            "end_to_end_recovery_seconds": mttr_seconds,
            "final_status": retry.get("final_status", "PENDING_EVIDENCE"),
            "evidence_source": "docker_logs" if injected_at is not None else "missing",
        })
    return records


def _build_kafka_idempotency_records(
    faults: list[dict[str, Any]],
    log_texts: list[str] | None = None,
) -> list[dict[str, Any]]:
    logs = "\n".join(log_texts or [])
    faults_by_stage = {str(fault.get("stage")): fault for fault in faults}
    records = []
    for spec in KAFKA_IDEMPOTENCY_COVERAGE:
        stage = spec.get("stage")
        marker = spec.get("marker")
        observed = False
        evidence_source = "missing"
        if stage:
            fault = faults_by_stage.get(str(stage), {})
            fault_id = str(fault.get("fault_id", ""))
            observed = bool(fault_id and fault_id in logs)
            evidence_source = "docker_logs" if observed else "missing"
        elif marker:
            observed = str(marker) in logs
            evidence_source = "docker_logs" if observed else "missing"
        records.append({
            "topic": spec["topic"],
            "component": spec["component"],
            "scenario": spec["scenario"],
            "retry_or_duplicate_observed": observed,
            "idempotency_guard": spec["idempotency_guard"],
            "final_effect": spec["final_effect"],
            "evidence_source": evidence_source,
        })
    return records


def _events_are_already_parsed(events: list[dict[str, Any]]) -> bool:
    return bool(events) and all(
        "job_id" in event and ("image_progress" in event or "transitions" in event)
        for event in events
    )


def _parse_or_reuse_job_events(
    helpers: Helpers,
    rows: list[dict[str, Any]],
    events_by_job: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    parsed_events = []
    for row in rows:
        job_id = row.get("job_id")
        if not job_id:
            continue
        events = events_by_job.get(str(job_id), [])
        if _events_are_already_parsed(events):
            parsed_events.extend(events)
        else:
            parsed_events.append(helpers.parse_job_events(str(job_id), events))
    return parsed_events


def _write_text_outputs(
    out: Path,
    helpers: Helpers,
    rows: list[dict[str, Any]],
    summary: dict[str, Any],
    worker_timeline: dict[str, Any],
    retry_summary: dict[str, Any],
    production_retry_records: list[dict[str, Any]],
    component_retry_records: list[dict[str, Any]],
    kafka_idempotency_records: list[dict[str, Any]],
) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "evaluation-results-table.txt").write_text(
        helpers.render_plain_text_table(
            "Retry Recovery Evaluation Results",
            ["jobs", "images", "failed_jobs", "failure_rate", "duration_seconds", "throughput_images_per_minute", "total_cost_usd"],
            [summary],
        ),
        encoding="utf-8",
    )
    (out / "worker-timeline-table.txt").write_text(
        helpers.render_plain_text_table(
            "Retry Recovery Worker Timeline",
            ["distinct_worker_count", "max_concurrent_workers_observed"],
            [worker_timeline],
        ),
        encoding="utf-8",
    )
    (out / "retry-recovery-table.txt").write_text(
        helpers.render_plain_text_table(
            "Retry Recovery End-to-End Summary",
            ["faults", "recovered_faults", "unrecovered_faults", "retry_attempts_observed", "end_to_end_recovery_seconds"],
            [{**retry_summary, "end_to_end_recovery_seconds": retry_summary.get("mttr_seconds")}],
        ),
        encoding="utf-8",
    )
    (out / "production-retry-coverage-table.txt").write_text(
        helpers.render_plain_text_table(
            "Production Retry End-to-End Impact",
            ["stage", "component", "fault_id", "attempts_observed", "recovered", "end_to_end_recovery_seconds", "final_status", "evidence_source"],
            production_retry_records,
        ),
        encoding="utf-8",
    )
    (out / "component-retry-mttr-table.txt").write_text(
        helpers.render_plain_text_table(
            "Component Retry MTTR",
            ["stage", "component", "fault_id", "component_recovered", "component_recovery_seconds", "recovery_signal", "evidence_source"],
            component_retry_records,
        ),
        encoding="utf-8",
    )
    (out / "kafka-idempotency-table.txt").write_text(
        helpers.render_plain_text_table(
            "Kafka At-Least-Once Idempotency Coverage",
            ["topic", "component", "scenario", "retry_or_duplicate_observed", "idempotency_guard", "final_effect", "evidence_source"],
            kafka_idempotency_records,
        ),
        encoding="utf-8",
    )
    notes = [
        "Retry Recovery Thesis Interpretation Notes",
        "",
        f"Observed jobs: {len(rows)}",
        f"Recovered faults: {retry_summary.get('recovered_faults', 0)} / {retry_summary.get('faults', 0)}",
        f"Unrecovered faults: {retry_summary.get('unrecovered_faults', 0)}",
        f"End-to-end recovery seconds: {retry_summary.get('mttr_seconds', 0)}",
        "Component-level MTTR is reported separately in component-retry-mttr-table.txt.",
        "",
    ]
    (out / "thesis-interpretation-notes.txt").write_text("\n".join(notes), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    helpers = _load_helpers()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    started_at = time.time()
    case_groups = helpers.load_case_groups(args.cases)
    fault_plan = build_fault_plan(case_groups)
    rows = run_multi_user_workload(args, fault_plan)
    raw_events = collect_job_events(args, rows)
    parsed_events = _parse_or_reuse_job_events(helpers, rows, raw_events)
    worker_timeline = helpers.summarize_worker_timeline(parsed_events)
    summary = helpers.summarize_records(rows)
    docker_logs = capture_docker_logs(out)
    docker_log_texts = []
    for item in docker_logs:
        path = item.get("path")
        if path and Path(path).exists():
            docker_log_texts.append(Path(path).read_text(encoding="utf-8", errors="replace"))
    retry_records = _build_retry_records(rows, fault_plan, docker_log_texts)
    production_retry_records = _build_production_retry_records(rows, fault_plan, docker_log_texts)
    component_retry_records = _build_component_retry_records(fault_plan, docker_log_texts)
    kafka_idempotency_records = _build_kafka_idempotency_records(fault_plan, docker_log_texts)
    retry_summary = helpers.summarize_retry_recovery_records(retry_records)
    summary_with_worker = {
        **summary,
        "distinct_worker_count": worker_timeline.get("distinct_worker_count", 0),
        "max_concurrent_workers_observed": worker_timeline.get("max_concurrent_workers_observed", 0),
        "images_per_worker": worker_timeline.get("images_per_worker", {}),
        "retry_recovery": retry_summary,
    }
    manifest = {
        "protocol": "retry_recovery_e2e",
        "started_at": started_at,
        "finished_at": time.time(),
        "timeout_s": args.timeout_s,
        "poll_s": args.poll_s,
        "fault_plan": fault_plan,
        "docker_logs": docker_logs,
    }

    helpers.write_json(out / "records.json", rows)
    helpers.write_csv(out / "records.csv", rows)
    helpers.write_json(out / "events.json", parsed_events)
    helpers.write_json(out / "worker_timeline.json", worker_timeline)
    helpers.write_json(out / "summary.json", summary_with_worker)
    helpers.write_json(out / "run_manifest.json", manifest)
    helpers.write_json(out / "production_retry_records.json", production_retry_records)
    helpers.write_json(out / "component_retry_records.json", component_retry_records)
    helpers.write_json(out / "kafka_idempotency_records.json", kafka_idempotency_records)
    _write_text_outputs(out, helpers, rows, summary, worker_timeline, retry_summary, production_retry_records, component_retry_records, kafka_idempotency_records)
    return 0


if __name__ == "__main__":
    sys.exit(main())
