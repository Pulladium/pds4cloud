from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

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


def _validate_groups(groups: dict[str, list[dict[str, Any]]]) -> list[tuple[str, list[dict[str, Any]]]]:
    selected = list(groups.items())
    if len(selected) != 9:
        raise SystemExit("sequential 45 protocol requires exactly nine case groups")
    if any(len(cases) != 5 for _name, cases in selected):
        raise SystemExit("sequential 45 protocol requires exactly five images in each case group")
    return selected


def main() -> None:
    parser = argparse.ArgumentParser(description="Run 9-job sequential reference processing and compare with 45-image proposed results")
    parser.add_argument("--cases", default="evaluation/cases_45.yml")
    parser.add_argument("--out", default="evaluation/protocols/sequential_reference_45/results")
    parser.add_argument("--proposed-summary", default="evaluation/protocols/multi_user_project_45/results/summary.json")
    parser.add_argument("--gateway", default=env("GATEWAY_URL", "http://gateway:8080"))
    parser.add_argument("--keycloak", default=env("KEYCLOAK_URL", "http://keycloak:8080"))
    parser.add_argument("--realm", default=env("KEYCLOAK_REALM", "pds4cloud"))
    parser.add_argument("--client-id", default=env("KEYCLOAK_CLIENT_ID", "react-client-certedu-api"))
    parser.add_argument("--users", default=env("EVAL_USERS", "researcher,researcher-2,researcher-3"))
    parser.add_argument("--model", default=env("OPENAI_MODEL", "gpt-4o"))
    parser.add_argument("--timeout-s", type=int, default=3600)
    parser.add_argument("--poll-s", type=float, default=5.0)
    args = parser.parse_args()

    groups = _validate_groups(load_case_groups(args.cases))
    users, passwords = resolve_eval_users(args.users)
    if not users or len(users) != len(passwords):
        raise SystemExit("sequential 45 protocol requires at least one eval user with a matching password")
    ensure_keycloak_eval_users(args.keycloak, args.realm, args.client_id, users, passwords)

    rows = [
        run_user_job(args, users[i % len(users)], passwords[i % len(passwords)], group_name, images)
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
        raise SystemExit(f"proposed summary not found: {proposed_path}. Run the 45-image proposed protocol first or pass --proposed-summary.")
    proposed = json.loads(proposed_path.read_text(encoding="utf-8"))
    comparison = compare_protocol_summaries(reference, proposed)
    write_json(out / "comparison.json", comparison)
    print(comparison)


if __name__ == "__main__":
    main()
