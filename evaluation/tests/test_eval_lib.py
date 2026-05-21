from pathlib import Path
from types import SimpleNamespace
import urllib.error

import pytest

from evaluation.protocols.multi_user_project import run as multi_user
from evaluation.eval_lib import (
    assert_protocol_condition,
    compare_reference_cost_impact,
    compare_protocol_summaries,
    load_case_groups,
    http_json,
    parse_iso,
    parse_job_events,
    sanitize_error_text,
    summarize_records,
    summarize_worker_timeline,
    write_csv,
    write_json,
)


def test_summarize_records_computes_protocol_metrics():
    records = [
        {"job_id": "j1", "image_count": 2, "status": "COMPLETED", "started_at": 10.0, "finished_at": 20.0, "cost_usd": 0.30, "stage_latencies_ms": {"ingest": 100, "transform": 200}},
        {"job_id": "j2", "image_count": 1, "status": "FAILED", "started_at": 30.0, "finished_at": 36.0, "cost_usd": 0.10, "recovered_at": 34.0, "failed_at": 31.0, "stage_latencies_ms": {"ingest": 50, "transform": 150}},
    ]

    summary = summarize_records(records)

    assert summary["jobs"] == 2
    assert summary["images"] == 3
    assert summary["failure_rate"] == 0.5
    assert summary["duration_seconds"] == 26.0
    assert summary["total_work_seconds"] == 16.0
    assert summary["throughput_images_per_minute"] == 6.92
    assert summary["mttr_seconds"] == 3.0
    assert summary["total_cost_usd"] == 0.4
    assert summary["stage_latency_ms"]["ingest"]["avg"] == 75.0
    assert summary["stage_latency_ms"]["transform"]["avg"] == 175.0


def test_compare_reference_cost_impact_calculates_limit_cost_impact():
    reference = {"images": 10, "total_cost_usd": 2.0, "duration_seconds": 100.0}
    proposed = {"images": 6, "total_cost_usd": 1.2, "duration_seconds": 40.0, "rejected_images": 4}

    comparison = compare_reference_cost_impact(reference, proposed)

    assert comparison["cost_saved_usd"] == 0.8
    assert comparison["cost_saved_percent"] == 40.0
    assert comparison["duration_delta_seconds"] == -60.0
    assert comparison["estimated_avoided_cost_usd"] == 0.8


def test_compare_protocol_summaries_reports_time_cost_and_worker_delta():
    reference = {
        "duration_seconds": 300,
        "total_cost_usd": 0.30,
        "throughput_images_per_minute": 3,
        "distinct_worker_count": 1,
    }
    proposed = {
        "duration_seconds": 120,
        "total_cost_usd": 0.33,
        "throughput_images_per_minute": 7.5,
        "distinct_worker_count": 4,
    }

    comparison = compare_protocol_summaries(reference, proposed)

    assert comparison["duration_saved_seconds"] == 180
    assert comparison["duration_saved_percent"] == 60.0
    assert comparison["cost_delta_usd"] == 0.03
    assert comparison["worker_count_delta"] == 3


def test_assert_protocol_condition_raises_clear_error():
    with pytest.raises(AssertionError, match="^expected message$"):
        assert_protocol_condition(False, "expected message")


def test_write_json_creates_output_file(tmp_path: Path):
    path = tmp_path / "nested" / "payload.json"

    write_json(path, {"b": 2, "a": 1})

    assert path.read_text(encoding="utf-8") == '{\n  "a": 1,\n  "b": 2\n}'


def test_write_csv_creates_output_file(tmp_path: Path):
    path = tmp_path / "nested" / "records.csv"

    write_csv(path, [{"b": 2, "a": 1}])

    assert path.read_text(encoding="utf-8").splitlines() == ["a,b", "1,2"]


def test_write_csv_preserves_empty_file_behavior(tmp_path: Path):
    path = tmp_path / "nested" / "empty.csv"

    write_csv(path, [])

    assert path.read_text(encoding="utf-8") == ""


def test_load_case_groups_reads_project_groups(tmp_path: Path):
    path = tmp_path / "cases.yml"
    path.write_text(
        """
groups:
  project_a:
    - id: a1
      lid: "lid-a1"
      thumb_url: ""
    - id: a2
      lid: "lid-a2"
      thumb_url: "http://thumb/a2"
  project_b:
    - id: b1
      lid: "lid-b1"
      thumb_url: ""
failure:
  bad_lid: "lid-bad"
""",
        encoding="utf-8",
    )

    groups = load_case_groups(path)

    assert list(groups) == ["project_a", "project_b"]
    assert groups["project_a"][0]["lid"] == "lid-a1"
    assert groups["project_a"][1]["thumb_url"] == "http://thumb/a2"
    assert groups["project_b"][0]["id"] == "b1"
    assert len(groups["project_b"]) == 1


def test_load_case_groups_reads_json_project_groups(tmp_path: Path):
    path = tmp_path / "cases.json"
    path.write_text(
        '{"groups":{"project_a":[{"id":"a1","lid":"lid-a1","thumb_url":""}]}}',
        encoding="utf-8",
    )

    assert load_case_groups(path) == {"project_a": [{"id": "a1", "lid": "lid-a1", "thumb_url": ""}]}


def test_load_case_groups_rejects_cases_missing_lid(tmp_path: Path):
    path = tmp_path / "cases.yml"
    path.write_text(
        """
groups:
  project_a:
    - id: a1
      thumb_url: ""
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="lid"):
        load_case_groups(path)


def test_load_case_groups_rejects_json_groups_with_non_list_cases(tmp_path: Path):
    path = tmp_path / "cases.json"
    path.write_text(
        '{"groups":{"project_a":{"id":"a1","lid":"lid-a1"}}}',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="list"):
        load_case_groups(path)


def test_parse_iso_accepts_zulu_timestamps():
    assert parse_iso("2026-05-13T10:00:00Z") == 1778666400.0
    assert parse_iso(None) is None


def test_parse_job_events_extracts_image_progress_payloads():
    events = [
        {
            "stage": "PROCESSING_IMAGES",
            "created_at": "2026-05-13T10:00:00Z",
            "payload_json": '{"job_id":"job-1","image_progress":{"worker_id":1,"lid":"lid-a","status":"processing","event_at":"2026-05-13T10:00:00Z"}}',
        },
        {
            "stage": "PROCESSING_IMAGES",
            "created_at": "2026-05-13T10:00:05Z",
            "payload_json": '{"job_id":"job-1","image_progress":{"worker_id":1,"lid":"lid-a","status":"done","event_at":"2026-05-13T10:00:05Z"}}',
        },
        {
            "stage": "IGNORED_BAD_JSON",
            "created_at": "2026-05-13T10:00:06Z",
            "payload_json": "{bad json",
        },
    ]

    parsed = parse_job_events("job-1", events)

    assert parsed["job_id"] == "job-1"
    assert len(parsed["transitions"]) == 3
    assert len(parsed["image_progress"]) == 2
    assert parsed["image_progress"][0]["worker_id"] == 1
    assert parsed["parse_errors"][0]["stage"] == "IGNORED_BAD_JSON"
    assert "bad json" in parsed["parse_errors"][0]["payload_excerpt"]


def test_parse_job_events_surfaces_malformed_payloads_without_secrets():
    parsed = parse_job_events(
        "job-1",
        [
            {
                "stage": "PROCESSING_IMAGES",
                "created_at": "2026-05-13T10:00:00Z",
                "payload_json": '{"password":"topsecret","Authorization":"Bearer abc123", bad',
            }
        ],
    )

    assert len(parsed["parse_errors"]) == 1
    error = parsed["parse_errors"][0]
    assert error["created_at"] == "2026-05-13T10:00:00Z"
    assert "topsecret" not in error["payload_excerpt"]
    assert "abc123" not in error["payload_excerpt"]
    assert "[REDACTED]" in error["payload_excerpt"]


def test_summarize_worker_timeline_counts_workers_and_overlap():
    parsed_jobs = [
        {
            "job_id": "job-1",
            "image_progress": [
                {"worker_id": 1, "lid": "lid-a", "status": "processing", "event_at": "2026-05-13T10:00:00Z"},
                {"worker_id": 1, "lid": "lid-a", "status": "done", "event_at": "2026-05-13T10:00:10Z"},
                {"worker_id": 2, "lid": "lid-b", "status": "processing", "event_at": "2026-05-13T10:00:02Z"},
                {"worker_id": 2, "lid": "lid-b", "status": "done", "event_at": "2026-05-13T10:00:08Z"},
            ],
        }
    ]

    summary = summarize_worker_timeline(parsed_jobs)

    assert summary["distinct_worker_count"] == 2
    assert summary["workers"] == ["1", "2"]
    assert summary["images_per_worker"] == {"1": 1, "2": 1}
    assert summary["max_concurrent_workers_observed"] == 2
    assert summary["intervals"] == [
        {"started_at": 1778666400.0, "finished_at": 1778666410.0, "worker_id": "1", "lid": "lid-a"},
        {"started_at": 1778666402.0, "finished_at": 1778666408.0, "worker_id": "2", "lid": "lid-b"},
    ]


def test_summarize_worker_timeline_does_not_count_abutting_intervals_as_concurrent():
    parsed_jobs = [
        {
            "job_id": "job-1",
            "image_progress": [
                {"worker_id": 1, "lid": "lid-a", "status": "processing", "event_at": "2026-05-13T10:00:00Z"},
                {"worker_id": 1, "lid": "lid-a", "status": "done", "event_at": "2026-05-13T10:00:10Z"},
                {"worker_id": 2, "lid": "lid-b", "status": "processing", "event_at": "2026-05-13T10:00:10Z"},
                {"worker_id": 2, "lid": "lid-b", "status": "done", "event_at": "2026-05-13T10:00:20Z"},
            ],
        }
    ]

    summary = summarize_worker_timeline(parsed_jobs)

    assert summary["max_concurrent_workers_observed"] == 1


def test_sanitize_error_text_redacts_auth_and_password_like_values():
    text = (
        'Authorization: Bearer abc.def.ghi\n'
        '{"password":"topsecret","admin_password":"root-secret","detail":"'
        + ("x" * 500)
        + '"}'
    )

    sanitized = sanitize_error_text(text, limit=160)

    assert "abc.def.ghi" not in sanitized
    assert "topsecret" not in sanitized
    assert "root-secret" not in sanitized
    assert "[REDACTED]" in sanitized
    assert len(sanitized) <= 163


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
        [{
            "job_id": "job-1",
            "pdf_url": (
                "http://minio/report.pdf?"
                "X-Amz-Signature=secret&X-Amz-Credential=cred&X-Amz-Security-Token=token"
            ),
        }],
    )

    assert "X-Amz-Signature" not in text
    assert "X-Amz-Credential" not in text
    assert "X-Amz-Security-Token" not in text
    assert "[REDACTED]" in text
    assert "Reports" in text


def test_render_plain_text_table_normalizes_and_caps_cells():
    from evaluation.eval_lib import render_plain_text_table

    text = render_plain_text_table(
        "Errors",
        ["job_id", "error"],
        [{"job_id": "job-1", "error": "line1\nline2\t" + ("x" * 400)}],
    )

    lines = text.splitlines()
    assert len(lines) == 4
    assert "line1 line2" in lines[3]
    assert len(lines[3]) < 280


def test_report_includes_retry_recovery_txt_outputs(tmp_path, monkeypatch):
    import evaluation.report as report

    root = tmp_path / "evaluation" / "protocols"
    out = root / "retry_recovery_e2e" / "results"
    out.mkdir(parents=True)
    (out / "summary.json").write_text(
        '{"jobs":3,"images":15,"failure_rate":0,"throughput_images_per_minute":3}',
        encoding="utf-8",
    )
    (out / "retry-recovery-table.txt").write_text("Retry Recovery\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    report.main()

    summary = (tmp_path / "evaluation" / "summary.md").read_text(encoding="utf-8")
    assert "retry_recovery_e2e" in summary
    assert "retry-recovery-table.txt" in summary


def test_report_does_not_generate_or_reference_charts(tmp_path, monkeypatch):
    import evaluation.report as report

    root = tmp_path / "evaluation" / "protocols"
    out = root / "functional" / "results"
    out.mkdir(parents=True)
    (out / "summary.json").write_text(
        '{"jobs":1,"images":1,"failure_rate":0,"throughput_images_per_minute":1}',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    report.main()

    summary = (tmp_path / "evaluation" / "summary.md").read_text(encoding="utf-8")
    assert "## Charts" not in summary
    assert "charts/results" not in summary
    assert not (tmp_path / "evaluation" / "charts").exists()


def test_run_all_does_not_execute_charts(monkeypatch):
    import evaluation.run_all as run_all

    modules = []
    monkeypatch.setattr(run_all.sys, "argv", ["run_all.py"])
    monkeypatch.setattr(run_all, "_run", lambda module, *args: modules.append(module))

    run_all.main()

    assert "evaluation.charts" not in modules
    assert modules[-1] == "evaluation.report"


def test_cases_45_contains_nine_groups_of_unique_real_lids():
    groups = load_case_groups("evaluation/cases_45.yml")

    assert len(groups) == 9
    lids = []
    for group_name, cases in groups.items():
        assert group_name.startswith("project_")
        assert len(cases) == 5
        lids.extend(case["lid"] for case in cases)

    assert len(lids) == 45
    assert len(set(lids)) == 45
    assert all(lid.startswith("urn:nasa:pds:mars2020_mastcamz_ops_calibrated:data:") for lid in lids)


def test_heavy_45_protocol_validators_require_nine_groups_of_five():
    from evaluation.protocols.multi_user_project_45.run import _job_batch_size, _validate_groups as validate_concurrent
    from evaluation.protocols.sequential_reference_45.run import _validate_groups as validate_sequential

    groups = {f"project_{index}": [{"lid": f"urn:test:{index}:{item}"} for item in range(5)] for index in range(9)}

    assert len(validate_concurrent(groups)) == 9
    assert len(validate_sequential(groups)) == 9

    with pytest.raises(SystemExit, match="requires exactly nine case groups"):
        validate_concurrent(dict(list(groups.items())[:8]))

    broken = dict(groups)
    broken["project_8"] = broken["project_8"][:4]
    with pytest.raises(SystemExit, match="five images in each case group"):
        validate_sequential(broken)

    assert _job_batch_size(["u1", "u2", "u3"], 5) == 3
    assert _job_batch_size(["u1", "u2", "u3", "u4", "u5", "u6"], 5) == 5

    with pytest.raises(SystemExit, match="at least one eval user"):
        _job_batch_size([], 5)


def test_run_all_does_not_execute_heavy_45_protocols(monkeypatch):
    import evaluation.run_all as run_all

    modules = []
    monkeypatch.setattr(run_all.sys, "argv", ["run_all.py"])
    monkeypatch.setattr(run_all, "_run", lambda module, *args: modules.append(module))

    run_all.main()

    assert not any(module.endswith("_45.run") for module in modules)


def test_http_json_retries_500_then_returns_json(monkeypatch: pytest.MonkeyPatch):
    calls = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b'{"ok": true}'

    def fake_urlopen(_req, timeout):
        calls.append(timeout)
        if len(calls) == 1:
            raise urllib.error.HTTPError("http://svc", 500, "server error", {}, None)
        return Response()

    monkeypatch.setattr("evaluation.eval_lib.urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr("evaluation.eval_lib.time.sleep", lambda _delay: None)

    assert http_json("GET", "http://svc", timeout=7) == {"ok": True}
    assert calls == [7, 7]


def test_http_json_does_not_retry_404(monkeypatch: pytest.MonkeyPatch):
    calls = []

    def fake_urlopen(_req, timeout):
        calls.append("call")
        raise urllib.error.HTTPError("http://svc", 404, "missing", {}, None)

    monkeypatch.setattr("evaluation.eval_lib.urllib.request.urlopen", fake_urlopen)

    with pytest.raises(RuntimeError, match="HTTP 404"):
        http_json("GET", "http://svc")

    assert calls == ["call"]


def test_run_user_job_marks_non_terminal_poll_result_failed(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        multi_user,
        "_load_helpers",
        lambda: SimpleNamespace(
            keycloak_token=lambda *_args: "token",
        ),
    )
    monkeypatch.setattr(
        multi_user,
        "submit_job",
        lambda *_args: {"project_id": "p1", "job_id": "job-1", "submit_status": "QUEUED", "submitted_at": 100.0},
    )
    monkeypatch.setattr(
        multi_user,
        "poll_job",
        lambda *_args: {"status": "RUNNING", "polled_until": 130.0, "cost_usd": 0.25},
    )

    row = multi_user.run_user_job(
        SimpleNamespace(keycloak="kc", realm="realm", client_id="client", gateway="gw", model="model", timeout_s=30, poll_s=1),
        "user-1",
        "password",
        "project_a",
        [{"id": "a1", "lid": "lid-a1"}],
    )

    assert row["status"] == "FAILED"
    assert "non-terminal" in row["error"]
    assert row["cost_usd"] == 0.25


def test_main_writes_paid_run_records_when_event_fetch_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    groups = {
        "project_a": [{"id": f"a{i}", "lid": f"lid-a{i}"} for i in range(5)],
        "project_b": [{"id": f"b{i}", "lid": f"lid-b{i}"} for i in range(5)],
        "project_c": [{"id": f"c{i}", "lid": f"lid-c{i}"} for i in range(5)],
    }
    rows = [
        {
            "username": f"user-{i}",
            "group": group,
            "project_id": f"project-{i}",
            "job_id": f"job-{i}",
            "image_count": 5,
            "status": "COMPLETED",
            "started_at": float(i),
            "finished_at": float(i + 10),
            "duration_seconds": 10.0,
            "pdf_url": None,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "cost_usd": 0.1,
            "worker_count": 0,
            "image_progress": [],
            "error": None,
        }
        for i, group in enumerate(groups)
    ]

    helpers = SimpleNamespace(
        load_case_groups=lambda _path: groups,
        env=lambda name, default: {
            "EVAL_PASSWORDS": "p1,p2,p3",
            "EVAL_ADMIN_PASSWORD": "admin-secret",
        }.get(name, default),
        keycloak_token=lambda *_args: "admin-token",
        parse_job_events=parse_job_events,
        summarize_records=summarize_records,
        summarize_worker_timeline=summarize_worker_timeline,
        write_json=write_json,
        write_csv=write_csv,
    )
    monkeypatch.setattr(multi_user, "_load_helpers", lambda: helpers)
    monkeypatch.setattr(multi_user, "run_user_job", lambda *_args: rows.pop(0))
    monkeypatch.setattr(multi_user, "fetch_events", lambda *_args: (_ for _ in ()).throw(RuntimeError("events unavailable")))

    rc = multi_user.main(["--out", str(tmp_path), "--cases", "ignored.yml"])

    assert rc == 0
    records = (tmp_path / "records.json").read_text(encoding="utf-8")
    summary = (tmp_path / "summary.json").read_text(encoding="utf-8")
    assert records.count("event_fetch_error") == 3
    assert "events unavailable" in records
    assert '"event_fetch_errors": 3' in summary


def test_main_writes_parsed_event_details(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    groups = {
        "project_a": [{"id": f"a{i}", "lid": f"lid-a{i}"} for i in range(5)],
        "project_b": [{"id": f"b{i}", "lid": f"lid-b{i}"} for i in range(5)],
        "project_c": [{"id": f"c{i}", "lid": f"lid-c{i}"} for i in range(5)],
    }
    rows = [
        {
            "username": f"user-{i}",
            "group": group,
            "project_id": f"project-{i}",
            "job_id": f"job-{i}",
            "image_count": 5,
            "status": "COMPLETED",
            "started_at": float(i),
            "finished_at": float(i + 10),
            "duration_seconds": 10.0,
            "pdf_url": "http://minio/report.pdf",
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "cost_usd": 0.1,
            "worker_count": 0,
            "image_progress": [],
            "error": None,
        }
        for i, group in enumerate(groups)
    ]
    events = [
        {
            "stage": "PROCESSING_IMAGES",
            "created_at": "2026-05-13T10:00:00Z",
            "payload_json": "{bad json",
        }
    ]

    helpers = SimpleNamespace(
        load_case_groups=lambda _path: groups,
        env=lambda name, default: {
            "EVAL_PASSWORDS": "p1,p2,p3",
            "EVAL_ADMIN_PASSWORD": "admin-secret",
        }.get(name, default),
        keycloak_token=lambda *_args: "admin-token",
        parse_job_events=parse_job_events,
        summarize_records=summarize_records,
        summarize_worker_timeline=summarize_worker_timeline,
        write_json=write_json,
        write_csv=write_csv,
    )
    monkeypatch.setattr(multi_user, "_load_helpers", lambda: helpers)
    monkeypatch.setattr(multi_user, "run_user_job", lambda *_args: rows.pop(0))
    monkeypatch.setattr(multi_user, "fetch_events", lambda *_args: events)

    rc = multi_user.main(["--out", str(tmp_path), "--cases", "ignored.yml"])

    assert rc == 0
    event_details = (tmp_path / "events.json").read_text(encoding="utf-8")
    summary = (tmp_path / "summary.json").read_text(encoding="utf-8")
    assert "parse_errors" in event_details
    assert "payload_excerpt" in event_details
    assert '"event_parse_errors": 3' in summary


def test_runner_parser_does_not_expose_password_cli_arguments():
    option_strings = {
        option
        for action in multi_user.build_parser()._actions
        for option in action.option_strings
    }

    assert "--passwords" not in option_strings
    assert "--admin-password" not in option_strings
