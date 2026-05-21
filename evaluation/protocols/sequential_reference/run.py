from __future__ import annotations

import argparse
import json
from pathlib import Path

from evaluation.eval_lib import (
    compare_protocol_summaries,
    ensure_keycloak_eval_users,
    env,
    load_case_groups,
    resolve_eval_users,
    summarize_records,
    write_csv,
    write_json,
)
from evaluation.protocols.multi_user_project.run import run_user_job


def main() -> None:
    parser = argparse.ArgumentParser(description="Run direct sequential reference processing and compare with proposed results")
    parser.add_argument("--cases", default="evaluation/cases.yml")
    parser.add_argument("--out", default="evaluation/protocols/sequential_reference/results")
    parser.add_argument("--proposed-summary", default="evaluation/protocols/multi_user_project/results/summary.json")
    parser.add_argument("--gateway", default=env("GATEWAY_URL", "http://gateway:8080"))
    parser.add_argument("--keycloak", default=env("KEYCLOAK_URL", "http://keycloak:8080"))
    parser.add_argument("--realm", default=env("KEYCLOAK_REALM", "pds4cloud"))
    parser.add_argument("--client-id", default=env("KEYCLOAK_CLIENT_ID", "react-client-certedu-api"))
    parser.add_argument("--users", default=env("EVAL_USERS", "researcher,researcher-2,researcher-3"))
    parser.add_argument("--model", default=env("OPENAI_MODEL", "gpt-4o"))
    parser.add_argument("--timeout-s", type=int, default=2400)
    parser.add_argument("--poll-s", type=float, default=5.0)
    args = parser.parse_args()

    groups = list(load_case_groups(args.cases).items())
    if len(groups) != 3 or any(len(cases) != 5 for _name, cases in groups):
        raise SystemExit("sequential reference protocol requires exactly three case groups with five images each")
    users, passwords = resolve_eval_users(args.users)
    if len(users) != 3 or len(passwords) != 3:
        raise SystemExit("sequential reference protocol requires exactly three eval users")
    ensure_keycloak_eval_users(args.keycloak, args.realm, args.client_id, users, passwords)

    rows = [
        run_user_job(args, users[i], passwords[i], group_name, images)
        for i, (group_name, images) in enumerate(groups)
    ]
    reference = summarize_records(rows)
    reference["accepted_jobs"] = sum(1 for row in rows if row["job_id"])
    reference["completed_jobs"] = sum(1 for row in rows if row["status"] == "COMPLETED")
    reference["distinct_worker_count"] = 1 if reference["completed_jobs"] else 0
    reference["max_concurrent_workers_observed"] = 1 if reference["completed_jobs"] else 0

    out = Path(args.out)
    write_json(out / "records.json", rows)
    write_csv(out / "records.csv", rows)
    write_json(out / "summary.json", reference)

    proposed_path = Path(args.proposed_summary)
    if not proposed_path.exists():
        raise SystemExit(f"proposed summary not found: {proposed_path}. Run the proposed protocol first or pass --proposed-summary.")
    proposed = json.loads(proposed_path.read_text(encoding="utf-8"))
    comparison = compare_protocol_summaries(reference, proposed)
    write_json(out / "comparison.json", comparison)
    print(comparison)


if __name__ == "__main__":
    main()
