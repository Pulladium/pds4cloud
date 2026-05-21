from __future__ import annotations

import argparse
import time
from pathlib import Path

from evaluation.eval_lib import ensure_keycloak_eval_users, env, http_json, keycloak_token, load_cases, summarize_records, write_csv, write_json

TERMINAL = {"COMPLETED", "FAILED"}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run proposed Gateway/Kafka job protocol")
    parser.add_argument("--cases", default="evaluation/cases.yml")
    parser.add_argument("--gateway", default=env("GATEWAY_URL", "http://gateway:8080"))
    parser.add_argument("--keycloak", default=env("KEYCLOAK_URL", "http://keycloak:8080"))
    parser.add_argument("--realm", default=env("KEYCLOAK_REALM", "pds4cloud"))
    parser.add_argument("--client-id", default=env("KEYCLOAK_CLIENT_ID", "react-client-certedu-api"))
    parser.add_argument("--username", default=env("EVAL_USERNAME", "researcher"))
    parser.add_argument("--password", default=env("EVAL_PASSWORD", "researcher"))
    parser.add_argument("--model", default=env("OPENAI_MODEL", "gpt-4o"))
    parser.add_argument("--timeout-s", type=int, default=1800)
    parser.add_argument("--out", default="evaluation/protocols/job_e2e/results")
    args = parser.parse_args()

    ensure_keycloak_eval_users(args.keycloak, args.realm, args.client_id, [args.username], [args.password])
    token = keycloak_token(args.keycloak, args.realm, args.username, args.password, args.client_id)
    headers = {"Authorization": f"Bearer {token}"}
    cases = load_cases(args.cases)
    images = [{"lid": c["lid"], "thumbUrl": c.get("thumb_url", "")} for c in cases]
    started = time.time()
    submit = http_json("POST", f"{args.gateway.rstrip('/')}/api/jobs", {"projectId": "eval-project", "images": images, "model": args.model}, headers=headers)
    job_id = submit["job_id"]
    status = submit.get("status", "PENDING")
    last = {}
    while time.time() - started < args.timeout_s:
        last = http_json("GET", f"{args.gateway.rstrip('/')}/api/jobs/{job_id}", headers=headers)
        status = last.get("status", status)
        if status in TERMINAL:
            break
        time.sleep(5)
    finished = time.time()
    row = {
        "protocol": "proposed_gateway_kafka",
        "job_id": job_id,
        "image_count": len(images),
        "status": status,
        "started_at": started,
        "finished_at": finished,
        "duration_seconds": round(finished - started, 4),
        "cost_usd": last.get("cost_usd") or 0,
        "prompt_tokens": last.get("prompt_tokens") or 0,
        "completion_tokens": last.get("completion_tokens") or 0,
        "pdf_url": last.get("pdf_url"),
        "error": last.get("error"),
    }
    out = Path(args.out)
    write_json(out / "records.json", [row])
    write_json(out / "summary.json", summarize_records([row]))
    write_csv(out / "records.csv", [row])
    print(row)


if __name__ == "__main__":
    main()
