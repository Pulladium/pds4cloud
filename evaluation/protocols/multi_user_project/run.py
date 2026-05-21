from __future__ import annotations

import argparse
import concurrent.futures
import sys
import time
from pathlib import Path
from typing import Any, Callable, NamedTuple

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

TERMINAL = {"COMPLETED", "FAILED"}
REQUIRED_HELPERS = (
    "auth_headers",
    "env",
    "http_json",
    "keycloak_token",
    "load_case_groups",
    "parse_job_events",
    "ensure_keycloak_eval_users",
    "resolve_admin_credentials",
    "resolve_eval_users",
    "summarize_records",
    "summarize_worker_timeline",
    "write_csv",
    "write_json",
)


class Helpers(NamedTuple):
    auth_headers: Callable[[str], dict[str, str]]
    env: Callable[[str, str], str]
    http_json: Callable[..., Any]
    keycloak_token: Callable[[str, str, str, str, str], str]
    load_case_groups: Callable[[str | Path], dict[str, list[dict[str, Any]]]]
    parse_job_events: Callable[[str, list[dict[str, Any]]], dict[str, Any]]
    ensure_keycloak_eval_users: Callable[[str, str, str, list[str], list[str]], None]
    resolve_admin_credentials: Callable[[], tuple[str, str]]
    resolve_eval_users: Callable[[str], tuple[list[str], list[str]]]
    summarize_records: Callable[[list[dict[str, Any]]], dict[str, Any]]
    summarize_worker_timeline: Callable[[list[dict[str, Any]]], dict[str, Any]]
    write_csv: Callable[[str | Path, list[dict[str, Any]]], None]
    write_json: Callable[[str | Path, Any], None]


def _load_helpers() -> Helpers:
    from evaluation import eval_lib

    missing = [name for name in REQUIRED_HELPERS if not hasattr(eval_lib, name)]
    if missing:
        joined = ", ".join(missing)
        raise RuntimeError(
            f"evaluation.eval_lib is missing required helper(s): {joined}. "
            "Land the planned eval_lib helper task before running the real E2E protocol."
        )
    return Helpers(*(getattr(eval_lib, name) for name in REQUIRED_HELPERS))


def _env_default(name: str, default: str) -> str:
    from evaluation.eval_lib import env

    return env(name, default)


def _sanitize_error(exc: Exception) -> str:
    from evaluation.eval_lib import sanitize_error_text

    return sanitize_error_text(str(exc))


def submit_job(gateway: str, token: str, project_id: str, images: list[dict[str, str]], model: str) -> dict[str, Any]:
    helpers = _load_helpers()
    payload = {
        "projectId": project_id,
        "images": [{"lid": item["lid"], "thumbUrl": item.get("thumb_url", "")} for item in images],
        "model": model,
    }
    submitted_at = time.time()
    response = helpers.http_json(
        "POST",
        f"{gateway.rstrip('/')}/api/jobs",
        payload,
        headers=helpers.auth_headers(token),
        timeout=120,
    )
    return {
        "project_id": project_id,
        "job_id": response["job_id"],
        "submit_status": response.get("status"),
        "submitted_at": submitted_at,
    }


def poll_job(gateway: str, token: str, job_id: str, timeout_s: int, poll_s: float) -> dict[str, Any]:
    helpers = _load_helpers()
    started = time.time()
    last: dict[str, Any] = {}
    completed = False
    while time.time() - started < timeout_s:
        last = helpers.http_json(
            "GET",
            f"{gateway.rstrip('/')}/api/jobs/{job_id}",
            headers=helpers.auth_headers(token),
            timeout=120,
        )
        if str(last.get("status", "")).upper() in TERMINAL:
            completed = True
            break
        time.sleep(poll_s)
    last["polled_until"] = time.time()
    if not completed:
        last["timed_out"] = True
    return last


def fetch_events(gateway: str, admin_token: str, job_id: str) -> list[dict[str, Any]]:
    helpers = _load_helpers()
    response = helpers.http_json(
        "GET",
        f"{gateway.rstrip('/')}/api/admin/jobs/{job_id}/events",
        headers=helpers.auth_headers(admin_token),
        timeout=120,
    )
    if isinstance(response, list):
        return response
    if isinstance(response, dict) and isinstance(response.get("events"), list):
        return response["events"]
    raise RuntimeError(f"unexpected admin events response for job {job_id}: {type(response).__name__}")


def run_user_job(args: argparse.Namespace, username: str, password: str, group_name: str, images: list[dict[str, str]]) -> dict[str, Any]:
    helpers = _load_helpers()
    project_id = f"eval-{group_name}-{int(time.time())}"
    started_at = time.time()
    try:
        token = helpers.keycloak_token(args.keycloak, args.realm, username, password, args.client_id)
        submitted = submit_job(args.gateway, token, project_id, images, args.model)
        final = poll_job(args.gateway, token, submitted["job_id"], args.timeout_s, args.poll_s)
        finished_at = float(final.get("polled_until") or time.time())
        final_status = str(final.get("status", "UNKNOWN")).upper()
        error = final.get("error")
        if final_status not in TERMINAL:
            error = (
                f"job did not reach terminal status before timeout: "
                f"non-terminal status {final_status}"
            )
            final_status = "FAILED"
        return {
            "username": username,
            "group": group_name,
            "project_id": project_id,
            "job_id": submitted["job_id"],
            "image_count": len(images),
            "status": final_status,
            "started_at": submitted["submitted_at"],
            "finished_at": finished_at,
            "duration_seconds": round(finished_at - float(submitted["submitted_at"]), 4),
            "pdf_url": final.get("pdf_url"),
            "prompt_tokens": final.get("prompt_tokens") or 0,
            "completion_tokens": final.get("completion_tokens") or 0,
            "cost_usd": final.get("cost_usd") or 0,
            "worker_count": final.get("worker_count") or 0,
            "image_progress": final.get("image_progress") or [],
            "error": error,
        }
    except Exception as exc:
        finished_at = time.time()
        return {
            "username": username,
            "group": group_name,
            "project_id": project_id,
            "job_id": "",
            "image_count": len(images),
            "status": "FAILED",
            "started_at": started_at,
            "finished_at": finished_at,
            "duration_seconds": round(finished_at - started_at, 4),
            "pdf_url": None,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "cost_usd": 0,
            "worker_count": 0,
            "image_progress": [],
            "error": _sanitize_error(exc),
        }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run 3-user concurrent 5-image project E2E protocol")
    parser.add_argument("--cases", default="evaluation/cases.yml")
    parser.add_argument("--gateway", default=_env_default("GATEWAY_URL", "http://gateway:8080"))
    parser.add_argument("--keycloak", default=_env_default("KEYCLOAK_URL", "http://keycloak:8080"))
    parser.add_argument("--realm", default=_env_default("KEYCLOAK_REALM", "pds4cloud"))
    parser.add_argument("--client-id", default=_env_default("KEYCLOAK_CLIENT_ID", "react-client-certedu-api"))
    parser.add_argument("--users", default=_env_default("EVAL_USERS", "researcher,researcher-2,researcher-3"))
    parser.add_argument("--admin-username", default="")
    parser.add_argument("--model", default=_env_default("OPENAI_MODEL", "gpt-4o"))
    parser.add_argument("--timeout-s", type=int, default=2400)
    parser.add_argument("--poll-s", type=float, default=5.0)
    parser.add_argument("--out", default="evaluation/protocols/multi_user_project/results")
    return parser


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _validate_groups(groups: dict[str, list[dict[str, Any]]]) -> list[tuple[str, list[dict[str, Any]]]]:
    selected = list(groups.items())
    if len(selected) != 3:
        raise SystemExit("multi-user protocol requires exactly three case groups")
    if any(len(cases) != 5 for _name, cases in selected):
        raise SystemExit("multi-user protocol requires exactly five images in each case group")
    return selected


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        helpers = _load_helpers()
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc

    groups = helpers.load_case_groups(args.cases)
    selected = _validate_groups(groups)

    if hasattr(helpers, "resolve_eval_users"):
        users, passwords = helpers.resolve_eval_users(args.users)
    else:
        users = _split_csv(args.users)
        passwords = _split_csv(helpers.env("EVAL_PASSWORDS", ""))
    if len(users) != 3 or len(passwords) != 3:
        raise SystemExit("multi-user protocol requires exactly three eval users")
    if hasattr(helpers, "ensure_keycloak_eval_users"):
        helpers.ensure_keycloak_eval_users(args.keycloak, args.realm, args.client_id, users, passwords)
    if hasattr(helpers, "resolve_admin_credentials"):
        resolved_admin_username, admin_password = helpers.resolve_admin_credentials()
    else:
        resolved_admin_username, admin_password = _env_default("EVAL_ADMIN_USERNAME", "admin-user"), helpers.env("EVAL_ADMIN_PASSWORD", "")
    admin_username = args.admin_username or resolved_admin_username

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        futures = [
            pool.submit(run_user_job, args, users[i], passwords[i], group_name, images)
            for i, (group_name, images) in enumerate(selected)
        ]
        rows = [future.result() for future in futures]

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

    out = Path(args.out)
    helpers.write_json(out / "records.json", rows)
    helpers.write_csv(out / "records.csv", rows)
    helpers.write_json(out / "summary.json", summary)
    helpers.write_json(out / "events.json", parsed_events)
    helpers.write_json(out / "worker_timeline.json", worker_timeline)
    print(summary)
    return 0 if summary["completed_jobs"] == 3 else 1


if __name__ == "__main__":
    sys.exit(main())
