from __future__ import annotations

import argparse
import concurrent.futures
import sys
import time
from pathlib import Path
from typing import Any

from evaluation.protocols.multi_user_project.run import (
    _env_default,
    _load_helpers,
    _sanitize_error,
    _split_csv,
    fetch_events,
    run_user_job,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run 9 concurrent 5-image project E2E protocol")
    parser.add_argument("--cases", default="evaluation/cases_45.yml")
    parser.add_argument("--gateway", default=_env_default("GATEWAY_URL", "http://gateway:8080"))
    parser.add_argument("--keycloak", default=_env_default("KEYCLOAK_URL", "http://keycloak:8080"))
    parser.add_argument("--realm", default=_env_default("KEYCLOAK_REALM", "pds4cloud"))
    parser.add_argument("--client-id", default=_env_default("KEYCLOAK_CLIENT_ID", "react-client-certedu-api"))
    parser.add_argument("--users", default=_env_default("EVAL_USERS", "researcher,researcher-2,researcher-3"))
    parser.add_argument("--admin-username", default="")
    parser.add_argument("--model", default=_env_default("OPENAI_MODEL", "gpt-4o"))
    parser.add_argument("--timeout-s", type=int, default=3600)
    parser.add_argument("--poll-s", type=float, default=5.0)
    parser.add_argument("--max-concurrent-jobs", type=int, default=5)
    parser.add_argument("--out", default="evaluation/protocols/multi_user_project_45/results")
    return parser


def _validate_groups(groups: dict[str, list[dict[str, Any]]]) -> list[tuple[str, list[dict[str, Any]]]]:
    selected = list(groups.items())
    if len(selected) != 9:
        raise SystemExit("multi-user 45 protocol requires exactly nine case groups")
    if any(len(cases) != 5 for _name, cases in selected):
        raise SystemExit("multi-user 45 protocol requires exactly five images in each case group")
    return selected


def _job_batch_size(users: list[str], max_concurrent_jobs: int) -> int:
    if not users:
        raise SystemExit("multi-user 45 protocol requires at least one eval user with a matching password")
    return max(1, min(len(users), max_concurrent_jobs))


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        helpers = _load_helpers()
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc

    selected = _validate_groups(helpers.load_case_groups(args.cases))
    if hasattr(helpers, "resolve_eval_users"):
        users, passwords = helpers.resolve_eval_users(args.users)
    else:
        users = _split_csv(args.users)
        passwords = _split_csv(helpers.env("EVAL_PASSWORDS", ""))
    if len(users) != len(passwords):
        raise SystemExit("multi-user 45 protocol requires matching eval users and passwords")
    if hasattr(helpers, "ensure_keycloak_eval_users"):
        helpers.ensure_keycloak_eval_users(args.keycloak, args.realm, args.client_id, users, passwords)
    if hasattr(helpers, "resolve_admin_credentials"):
        resolved_admin_username, admin_password = helpers.resolve_admin_credentials()
    else:
        resolved_admin_username, admin_password = _env_default("EVAL_ADMIN_USERNAME", "admin-user"), helpers.env("EVAL_ADMIN_PASSWORD", "")
    admin_username = args.admin_username or resolved_admin_username

    batch_size = _job_batch_size(users, args.max_concurrent_jobs)
    rows = []
    for offset in range(0, len(selected), batch_size):
        batch = selected[offset: offset + batch_size]
        with concurrent.futures.ThreadPoolExecutor(max_workers=batch_size) as pool:
            futures = [
                pool.submit(run_user_job, args, users[i], passwords[i], group_name, images)
                for i, (group_name, images) in enumerate(batch)
            ]
            rows.extend(future.result() for future in futures)

    parsed_events = []
    try:
        admin_token = helpers.keycloak_token(args.keycloak, args.realm, admin_username, admin_password, args.client_id)
    except Exception as exc:
        error = f"admin event token fetch failed: {_sanitize_error(exc)}"
        for row in rows:
            if row["job_id"]:
                row["event_fetch_error"] = error
    else:
        for row in rows:
            if row["job_id"]:
                try:
                    events = fetch_events(args.gateway, admin_token, row["job_id"])
                except Exception as exc:
                    row["event_fetch_error"] = _sanitize_error(exc)
                    continue
                parsed_events.append(helpers.parse_job_events(row["job_id"], events))

    worker_timeline = helpers.summarize_worker_timeline(parsed_events)
    summary = helpers.summarize_records(rows)
    summary["accepted_jobs"] = sum(1 for row in rows if row["job_id"])
    summary["completed_jobs"] = sum(1 for row in rows if row["status"] == "COMPLETED")
    summary["event_fetch_errors"] = sum(1 for row in rows if row.get("event_fetch_error"))
    summary["event_parse_errors"] = sum(len(job.get("parse_errors") or []) for job in parsed_events)
    summary["distinct_worker_count"] = worker_timeline["distinct_worker_count"]
    summary["max_concurrent_workers_observed"] = worker_timeline["max_concurrent_workers_observed"]
    summary["images_per_worker"] = worker_timeline["images_per_worker"]
    summary["submission_batch_size"] = batch_size

    out = Path(args.out)
    helpers.write_json(out / "records.json", rows)
    helpers.write_csv(out / "records.csv", rows)
    helpers.write_json(out / "summary.json", summary)
    helpers.write_json(out / "events.json", parsed_events)
    helpers.write_json(out / "worker_timeline.json", worker_timeline)
    print(summary)
    return 0 if summary["completed_jobs"] == 9 else 1


if __name__ == "__main__":
    sys.exit(main())
