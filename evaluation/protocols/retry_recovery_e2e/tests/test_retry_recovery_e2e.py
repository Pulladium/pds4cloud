import json
import os
from types import SimpleNamespace


def test_build_parser_uses_retry_recovery_e2e_default_out():
    from evaluation.protocols.retry_recovery_e2e.run import build_parser

    args = build_parser().parse_args([])

    assert args.out == "evaluation/protocols/retry_recovery_e2e/results"


def test_build_fault_plan_covers_production_retries_and_kafka_idempotency():
    from evaluation.protocols.retry_recovery_e2e.run import build_fault_plan

    case_groups = {
        "project_a": [{"id": "a1", "lid": "lid-a"}],
        "project_b": [{"id": "b1", "lid": "lid-b"}],
        "project_c": [{"id": "c1", "lid": "lid-c"}],
    }

    faults = build_fault_plan(case_groups)
    by_stage = {fault["stage"]: fault for fault in faults}

    assert set(by_stage) >= {
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
        "job_submitted_publish",
        "duplicate_image_result",
        "duplicate_job_status",
        "late_terminal_status",
    }
    assert by_stage["pds_lookup"]["failures"] == 1
    assert by_stage["pds_lookup"]["job_id"] == ""
    assert by_stage["pds_lookup"]["lid"] == "lid-a"
    assert by_stage["pdf_upload"]["group"] == "project_a"
    assert by_stage["duplicate_image_result"]["duplicates"] == 1
    assert by_stage["duplicate_job_status"]["duplicates"] == 1
    assert by_stage["late_terminal_status"]["duplicates"] == 1


def test_build_fault_plan_uses_first_group_for_pdf_upload_when_second_missing():
    from evaluation.protocols.retry_recovery_e2e.run import build_fault_plan

    faults = build_fault_plan({"project_a": [{"id": "a1", "lid": "lid-a"}]})

    pdf_fault = next(fault for fault in faults if fault["stage"] == "pdf_upload")
    assert pdf_fault["fault_id"] == "f-pdf-upload-1"
    assert pdf_fault["group"] == "project_a"


def test_run_multi_user_workload_sets_and_restores_eval_faults(tmp_path, monkeypatch):
    from evaluation.protocols.multi_user_project import run as run_multi_user_project_e2e
    from evaluation.protocols.retry_recovery_e2e.run import run_multi_user_workload

    captured = {}
    previous = "previous-faults"
    monkeypatch.setenv("EVAL_FAULTS", previous)

    def fake_child_main(argv):
        captured["argv"] = argv
        captured["eval_faults"] = os.environ["EVAL_FAULTS"]
        out = tmp_path / "multi_user_project"
        out.mkdir()
        (out / "records.json").write_text(json.dumps([{"job_id": "job-a"}]), encoding="utf-8")
        return 0

    monkeypatch.setattr(run_multi_user_project_e2e, "main", fake_child_main)
    fault_plan = [
        {"fault_id": "f-analyze-1", "stage": "analyze", "lid": "lid-a", "job_id": "", "failures": 1},
        {"fault_id": "f-pdf-upload-1", "stage": "pdf_upload", "job_id": "", "failures": 1},
    ]
    args = SimpleNamespace(
        out=str(tmp_path),
        timeout_s=2400,
        poll_s=5.0,
        cases="custom-cases.yml",
        gateway="http://gateway:8080",
        keycloak="http://keycloak:8080",
        realm="pds4cloud",
        client_id="react-client-certedu-api",
        users="researcher,researcher-2,researcher-3",
        admin_username="admin-user",
        model="gpt-4o",
    )

    rows = run_multi_user_workload(args, fault_plan)

    assert rows == [{"job_id": "job-a"}]
    assert os.environ["EVAL_FAULTS"] == previous
    serialized = json.loads(captured["eval_faults"])
    assert serialized == fault_plan
    assert captured["argv"] == [
        "--out",
        str(tmp_path / "multi_user_project"),
        "--timeout-s",
        "2400",
        "--poll-s",
        "5.0",
        "--cases",
        "custom-cases.yml",
        "--gateway",
        "http://gateway:8080",
        "--keycloak",
        "http://keycloak:8080",
        "--realm",
        "pds4cloud",
        "--client-id",
        "react-client-certedu-api",
        "--users",
        "researcher,researcher-2,researcher-3",
        "--admin-username",
        "admin-user",
        "--model",
        "gpt-4o",
    ]


def test_fault_plan_serializes_to_eval_faults_env():
    from evaluation.protocols.retry_recovery_e2e.run import serialize_fault_env

    env_value = serialize_fault_env([
        {"fault_id": "f1", "stage": "analyze", "job_id": "job-1", "lid": "lid-1", "failures": 1}
    ])

    assert '"fault_id":"f1"' in env_value
    assert '"stage":"analyze"' in env_value
    assert " " not in env_value


def test_collect_job_events_reuses_nested_multi_user_events(tmp_path):
    from evaluation.protocols.retry_recovery_e2e.run import collect_job_events

    nested = tmp_path / "multi_user_project"
    nested.mkdir()
    (nested / "events.json").write_text(
        json.dumps([
            {"job_id": "job-a", "image_progress": [{"lid": "lid-a"}], "transitions": [{"stage": "analyze"}]},
            {"job_id": "job-b", "image_progress": [{"lid": "lid-b"}], "transitions": []},
        ]),
        encoding="utf-8",
    )

    events = collect_job_events(SimpleNamespace(out=str(tmp_path)), [])

    assert events == {
        "job-a": [{"job_id": "job-a", "image_progress": [{"lid": "lid-a"}], "transitions": [{"stage": "analyze"}]}],
        "job-b": [{"job_id": "job-b", "image_progress": [{"lid": "lid-b"}], "transitions": []}],
    }


def test_capture_docker_logs_uses_timestamps(tmp_path, monkeypatch):
    from evaluation.protocols.retry_recovery_e2e import run as mod

    commands = []

    def fake_run(command, capture_output, text, timeout, check):
        commands.append(command)
        return SimpleNamespace(stdout="log\n", stderr="", returncode=0)

    monkeypatch.setattr(mod.subprocess, "run", fake_run)

    mod.capture_docker_logs(tmp_path)

    assert commands[0] == ["docker", "compose", "logs", "--no-color", "--timestamps", "gateway"]


def test_retry_recovery_protocol_writes_txt_tables(tmp_path, monkeypatch):
    from evaluation.protocols.retry_recovery_e2e import run as mod

    calls = []
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
    written = {}

    def write_json(path, payload):
        written[path.name] = payload
        path.write_text(json.dumps(payload), encoding="utf-8")

    helpers = SimpleNamespace(
        load_case_groups=lambda path: calls.append(("load_case_groups", path)) or {"project_a": [{"id": "a1", "lid": "lid-a"}]},
        summarize_records=lambda records: {"jobs": 1, "images": 5, "failed_jobs": 0, "failure_rate": 0.0, "duration_seconds": 30.0, "throughput_images_per_minute": 10.0, "total_cost_usd": 0.12},
        summarize_worker_timeline=lambda parsed: {"distinct_worker_count": 1, "max_concurrent_workers_observed": 1, "intervals": []},
        summarize_retry_recovery_records=lambda records: {
            "faults": len(records),
            "recovered_faults": sum(1 for record in records if record.get("recovered_at") is not None),
            "unrecovered_faults": sum(1 for record in records if record.get("recovered_at") is None),
            "retry_attempts_observed": sum(record.get("retry_attempts_observed", 0) for record in records),
            "mttr_seconds": 0.0,
        },
        render_plain_text_table=lambda title, columns, table_rows: title + "\n",
        write_json=write_json,
        write_csv=lambda path, payload: path.write_text("", encoding="utf-8"),
        parse_job_events=lambda job_id, events: {"job_id": job_id, "image_progress": [], "transitions": [], "parse_errors": []},
    )
    monkeypatch.setattr(mod, "_load_helpers", lambda: helpers)

    def fake_workload(args, fault_plan):
        calls.append(("run_multi_user_workload", fault_plan))
        assert fault_plan[0]["fault_id"] == "f-pds-lookup-1"
        assert fault_plan[0]["lid"] == "lid-a"
        assert calls[0] == ("load_case_groups", "evaluation/cases.yml")
        return rows

    monkeypatch.setattr(mod, "run_multi_user_workload", fake_workload)
    monkeypatch.setattr(mod, "collect_job_events", lambda args, rows: {"job-a": []})
    monkeypatch.setattr(mod, "capture_docker_logs", lambda out: [])

    code = mod.main(["--out", str(tmp_path)])

    assert code == 0
    assert (tmp_path / "evaluation-results-table.txt").exists()
    assert (tmp_path / "worker-timeline-table.txt").exists()
    assert (tmp_path / "retry-recovery-table.txt").exists()
    assert (tmp_path / "production-retry-coverage-table.txt").exists()
    assert (tmp_path / "component-retry-mttr-table.txt").exists()
    assert (tmp_path / "kafka-idempotency-table.txt").exists()
    assert (tmp_path / "thesis-interpretation-notes.txt").exists()
    assert "production_retry_records.json" in written
    assert "component_retry_records.json" in written
    assert "kafka_idempotency_records.json" in written
    retry_summary = written["summary.json"]["retry_recovery"]
    assert written["summary.json"]["distinct_worker_count"] == 1
    assert written["summary.json"]["max_concurrent_workers_observed"] == 1
    assert retry_summary["recovered_faults"] == 0
    assert retry_summary["mttr_seconds"] == 0.0
    assert written["run_manifest.json"]["fault_plan"][0]["fault_id"] == "f-pds-lookup-1"
    assert written["run_manifest.json"]["fault_plan"][0]["failures"] == 1
    assert written["run_manifest.json"]["fault_plan"][0]["job_id"] == ""
    assert written["run_manifest.json"]["fault_plan"][0]["lid"] == "lid-a"


def test_build_retry_records_marks_logged_faults_recovered_when_group_completed():
    from evaluation.protocols.retry_recovery_e2e.run import _build_retry_records

    rows = [
        {"group": "project_a", "status": "COMPLETED", "finished_at": 100.0},
        {"group": "project_b", "status": "COMPLETED", "finished_at": 120.0},
    ]
    faults = [
        {"fault_id": "f-analyze-1", "stage": "analyze", "group": "project_a", "failures": 1},
        {"fault_id": "f-pdf-upload-1", "stage": "pdf_upload", "group": "project_b", "failures": 1},
    ]
    log_text = "\n".join([
        'pds4-orchtr | 2026-05-17T14:30:11.230415226Z EVAL_FAULT injected {"fault_id": "f-analyze-1"}',
        "pds4-orchtr | 2026-05-17T14:30:11.234231349Z image lid-a attempt 1 failed (eval fault injected: f-analyze-1), retry in 1s",
        'pds4-orchtr | 2026-05-17T14:32:27.686036908Z EVAL_FAULT injected {"fault_id": "f-pdf-upload-1"}',
        "pds4-orchtr | 2026-05-17T14:32:27.686060079Z PDF upload attempt 1 failed for job job-b (eval fault injected: f-pdf-upload-1), retry in 0s",
    ])

    records = _build_retry_records(rows, faults, [log_text])

    assert records[0]["final_status"] == "COMPLETED"
    assert records[0]["failure_injected_at"] is not None
    assert records[0]["recovered_at"] == 100.0
    assert records[0]["retry_attempts_observed"] == 1
    assert records[1]["final_status"] == "COMPLETED"
    assert records[1]["recovered_at"] == 120.0


def test_build_production_retry_records_writes_required_rows():
    from evaluation.protocols.retry_recovery_e2e.run import _build_production_retry_records

    rows = [{"group": "project_a", "status": "COMPLETED", "finished_at": 2_000_000_000.0}]
    faults = [
        {"fault_id": "f-pds-lookup-1", "stage": "pds_lookup", "group": "project_a", "failures": 1},
    ]
    logs = [
        'svc | 2026-05-17T14:30:11.000000000Z EVAL_FAULT injected {"fault_id":"f-pds-lookup-1","stage":"pds_lookup"}\n'
        "svc | retry failed (eval fault injected: f-pds-lookup-1), retry in 0s\n"
    ]

    records = _build_production_retry_records(rows, faults, logs)
    by_stage = {record["stage"]: record for record in records}

    assert by_stage["pds_lookup"]["component"] == "ingest"
    assert by_stage["pds_lookup"]["attempts_observed"] == 1
    assert by_stage["pds_lookup"]["recovered"] is True
    assert by_stage["pds_lookup"]["final_status"] == "COMPLETED"
    assert "pdf_upload" in by_stage


def test_build_component_retry_records_measures_local_recovery():
    from evaluation.protocols.retry_recovery_e2e.run import _build_component_retry_records

    faults = [
        {"fault_id": "f-transform-rgb-upload-1", "stage": "transform_rgb_upload", "failures": 1},
        {"fault_id": "f-pdf-generation-1", "stage": "pdf_generation", "job_id": "job-1", "failures": 1},
    ]
    logs = [
        "\n".join([
            'svc | 2026-05-17T14:30:11.000000000Z EVAL_FAULT injected {"fault_id":"f-transform-rgb-upload-1","stage":"transform_rgb_upload","lid":"PHOTO_1"}',
            "svc | 2026-05-17T14:30:11.025000000Z   OK photo_id=PHOTO_1 gray=uploaded rgb=uploaded",
            'svc | 2026-05-17T14:30:20.000000000Z EVAL_FAULT injected {"fault_id":"f-pdf-generation-1","stage":"pdf_generation","job_id":"job-1"}',
            'svc | 2026-05-17T14:30:20.250000000Z EVAL_FAULT injected {"fault_id":"f-pdf-upload-1","stage":"pdf_upload","job_id":"job-1"}',
        ])
    ]

    records = _build_component_retry_records(faults, logs)
    by_stage = {record["stage"]: record for record in records}

    assert by_stage["transform_rgb_upload"]["component_recovery_seconds"] == 0.025
    assert by_stage["transform_rgb_upload"]["component_recovered"] is True
    assert by_stage["pdf_generation"]["component_recovery_seconds"] == 0.25
    assert by_stage["pdf_generation"]["recovery_signal"] == "next retry boundary started"


def test_build_kafka_idempotency_records_parses_publish_and_duplicate_evidence():
    from evaluation.protocols.retry_recovery_e2e.run import _build_kafka_idempotency_records

    faults = [
        {"fault_id": "f-job-submitted-publish-1", "stage": "job_submitted_publish", "failures": 1},
        {"fault_id": "f-image-task-publish-1", "stage": "image_task_publish", "failures": 1},
        {"fault_id": "f-job-status-publish-1", "stage": "job_status_publish", "failures": 1},
    ]
    logs = [
        "\n".join([
            'gateway | EVAL_FAULT injected {"fault_id":"f-job-submitted-publish-1"}',
            "orchtr | eval fault injected: f-image-task-publish-1",
            "orchtr | eval fault injected: f-job-status-publish-1",
            "orchtr | KAFKA_IDEMPOTENCY duplicate_image_result job=job-1 lid=lid-1 guard=seen_lids final_effect=skipped_duplicate",
            "gateway | KAFKA_IDEMPOTENCY duplicate_job_status job=job-1 guard=update_by_job_id final_effect=one_job_record",
            "gateway | KAFKA_IDEMPOTENCY late_terminal_status job=job-1 guard=terminal_status final_effect=final_status_unchanged",
        ])
    ]

    records = _build_kafka_idempotency_records(faults, logs)
    by_scenario = {record["scenario"]: record for record in records}

    assert by_scenario["transient publish failure"]["retry_or_duplicate_observed"] is True
    assert by_scenario["duplicate image result replay"]["idempotency_guard"] == "seen_lids"
    assert by_scenario["duplicate status replay"]["retry_or_duplicate_observed"] is True
    assert by_scenario["duplicate or late terminal status handling"]["final_effect"] == "final_status_unchanged"
