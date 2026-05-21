from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from evaluation.eval_lib import (
    auth_headers,
    ensure_keycloak_eval_users,
    env,
    http_json,
    keycloak_token,
    parse_job_events,
    resolve_admin_credentials,
    summarize_worker_timeline,
    write_json,
)

TERMINAL = {"COMPLETED", "FAILED"}

CASES = [
    {"id": "single_new_1", "lid": "urn:nasa:pds:mars2020_mastcamz_ops_calibrated:data:zlf_0047_0671110966_007rad_t0031416zcam05001_110300j", "thumb_url": ""},
    {"id": "single_new_2", "lid": "urn:nasa:pds:mars2020_mastcamz_ops_calibrated:data:zlf_0048_0671201721_937rzs_n0031708zcam05008_110050j", "thumb_url": ""},
    {"id": "single_new_3", "lid": "urn:nasa:pds:mars2020_mastcamz_ops_calibrated:data:zlf_0049_0671290479_898raf_n0031850zcam05009_110050j", "thumb_url": ""},
    {"id": "single_new_4", "lid": "urn:nasa:pds:mars2020_mastcamz_ops_calibrated:data:zl3_0080_0674039113_113ras_n0032430zcam03129_1100luj", "thumb_url": ""},
    {"id": "single_new_5", "lid": "urn:nasa:pds:mars2020_mastcamz_ops_calibrated:data:zlf_0055_0671823652_716ras_n0032046zcam05009_110050j", "thumb_url": ""},
]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a single-user 5-image worker-concurrency probe")
    parser.add_argument("--gateway", default=env("GATEWAY_URL", "http://gateway:8080"))
    parser.add_argument("--keycloak", default=env("KEYCLOAK_URL", "http://keycloak:8080"))
    parser.add_argument("--realm", default=env("KEYCLOAK_REALM", "pds4cloud"))
    parser.add_argument("--client-id", default=env("KEYCLOAK_CLIENT_ID", "react-client-certedu-api"))
    parser.add_argument("--username", default=env("EVAL_SINGLE_USERNAME", "researcher"))
    parser.add_argument("--admin-username", default="")
    parser.add_argument("--model", default=env("OPENAI_MODEL", "gpt-4o"))
    parser.add_argument("--timeout-s", type=int, default=2400)
    parser.add_argument("--poll-s", type=float, default=5.0)
    parser.add_argument("--out", default="evaluation/protocols/single_user_5_image_probe/results")
    return parser


def _poll_job(gateway: str, token: str, job_id: str, timeout_s: int, poll_s: float) -> dict[str, Any]:
    started = time.time()
    last: dict[str, Any] = {}
    while time.time() - started < timeout_s:
        last = http_json("GET", f"{gateway.rstrip('/')}/api/jobs/{job_id}", headers=auth_headers(token), timeout=120)
        status = str(last.get("status", "")).upper()
        print("poll", status, last.get("stage_info", ""), flush=True)
        if status in TERMINAL:
            return last
        time.sleep(poll_s)
    last["status"] = "FAILED"
    last["error"] = f"Timed out after {timeout_s}s before terminal status"
    return last


def main() -> int:
    args = build_parser().parse_args()
    password = env("EVAL_SINGLE_PASSWORD", "") or env("EVAL_PASSWORD", "")
    if not password:
        raise SystemExit("Provide EVAL_PASSWORD or EVAL_SINGLE_PASSWORD")
    ensure_keycloak_eval_users(args.keycloak, args.realm, args.client_id, [args.username], [password])
    resolved_admin_username, admin_password = resolve_admin_credentials()
    admin_username = args.admin_username or resolved_admin_username

    user_token = keycloak_token(args.keycloak, args.realm, args.username, password, args.client_id)
    project_id = f"eval-single-user-{int(time.time())}"
    payload = {
        "projectId": project_id,
        "images": [{"lid": case["lid"], "thumbUrl": case["thumb_url"]} for case in CASES],
        "model": args.model,
    }

    started = time.time()
    submit = http_json("POST", f"{args.gateway.rstrip('/')}/api/jobs", payload, headers=auth_headers(user_token), timeout=120)
    job_id = submit["job_id"]
    print("submitted", job_id, project_id, flush=True)
    final = _poll_job(args.gateway, user_token, job_id, args.timeout_s, args.poll_s)
    finished = time.time()

    admin_token = keycloak_token(args.keycloak, args.realm, admin_username, admin_password, args.client_id)
    events = http_json("GET", f"{args.gateway.rstrip('/')}/api/admin/jobs/{job_id}/events", headers=auth_headers(admin_token), timeout=120)
    parsed = parse_job_events(job_id, events)
    timeline = summarize_worker_timeline([parsed])
    record = {
        "protocol": "single_user_5_image_probe",
        "username": args.username,
        "project_id": project_id,
        "job_id": job_id,
        "image_count": len(CASES),
        "status": final.get("status"),
        "started_at": started,
        "finished_at": finished,
        "duration_seconds": round(finished - started, 4),
        "worker_count": final.get("worker_count"),
        "cost_usd": final.get("cost_usd") or 0,
        "error": final.get("error"),
        "pdf_url_present": bool(final.get("pdf_url")),
    }
    out = Path(args.out)
    write_json(out / "cases.json", CASES)
    write_json(out / "record.json", record)
    write_json(out / "events.json", [parsed])
    write_json(out / "worker_timeline.json", timeline)
    print("record", json.dumps(record, sort_keys=True), flush=True)
    print("timeline", json.dumps({k: timeline.get(k) for k in ["distinct_worker_count", "workers", "images_per_worker", "max_concurrent_workers_observed"]}, sort_keys=True), flush=True)
    return 0 if str(final.get("status", "")).upper() == "COMPLETED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
