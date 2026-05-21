from __future__ import annotations

import argparse
import time
from pathlib import Path

from evaluation.eval_lib import assert_protocol_condition, ensure_keycloak_eval_users, env, http_json, keycloak_token, load_cases, summarize_records, write_csv, write_json


def main() -> None:
    parser = argparse.ArgumentParser(description="Submit more jobs than platform limits allow and estimate avoided cost")
    parser.add_argument("--cases", default="evaluation/cases.yml")
    parser.add_argument("--gateway", default=env("GATEWAY_URL", "http://gateway:8080"))
    parser.add_argument("--keycloak", default=env("KEYCLOAK_URL", "http://keycloak:8080"))
    parser.add_argument("--realm", default=env("KEYCLOAK_REALM", "pds4cloud"))
    parser.add_argument("--client-id", default=env("KEYCLOAK_CLIENT_ID", "react-client-certedu-api"))
    parser.add_argument("--username", default=env("EVAL_USERNAME", "researcher"))
    parser.add_argument("--password", default=env("EVAL_PASSWORD", "researcher"))
    parser.add_argument("--attempts", type=int, default=6)
    parser.add_argument("--avg-cost-per-image", type=float, default=0.0)
    parser.add_argument("--out", default="evaluation/protocols/limits/results")
    args = parser.parse_args()

    ensure_keycloak_eval_users(args.keycloak, args.realm, args.client_id, [args.username], [args.password])
    token = keycloak_token(args.keycloak, args.realm, args.username, args.password, args.client_id)
    headers = {"Authorization": f"Bearer {token}"}
    first_case = load_cases(args.cases)[0]
    rows = []
    for i in range(args.attempts):
        started = time.time()
        status = "ACCEPTED"
        error = None
        try:
            response = http_json("POST", f"{args.gateway.rstrip('/')}/api/jobs", {
                "projectId": f"eval-limit-project-{i}",
                "images": [{"lid": first_case["lid"], "thumbUrl": first_case.get("thumb_url", "")}],
            }, headers=headers)
            job_id = response.get("job_id", f"accepted-{i}")
        except Exception as exc:
            status = "REJECTED"
            error = str(exc)
            job_id = f"rejected-{i}"
        rows.append({
            "protocol": "limits",
            "job_id": job_id,
            "image_count": 1,
            "status": "FAILED" if status == "REJECTED" else "COMPLETED",
            "limit_status": status,
            "started_at": started,
            "finished_at": time.time(),
            "cost_usd": 0,
            "error": error,
        })
    summary = summarize_records(rows)
    rejected_images = sum(r["image_count"] for r in rows if r["limit_status"] == "REJECTED")
    summary["rejected_images"] = rejected_images
    summary["estimated_avoided_cost_usd"] = round(rejected_images * args.avg_cost_per_image, 6)
    assert_protocol_condition(args.attempts >= 6, "limits protocol should attempt enough jobs to exceed MAX_CONCURRENT_JOBS=5")
    assert_protocol_condition("rejected_images" in summary, "limits protocol must report rejected_images")
    assert_protocol_condition(rejected_images > 0, "limits protocol must observe at least one rejected image when attempts exceed the limit")
    assert_protocol_condition(
        any(row["limit_status"] == "REJECTED" for row in rows),
        "limits protocol must observe at least one REJECTED limit_status when attempts exceed the limit",
    )
    assert_protocol_condition("estimated_avoided_cost_usd" in summary, "limits protocol must report estimated avoided cost")
    out = Path(args.out)
    write_json(out / "records.json", rows)
    write_json(out / "summary.json", summary)
    write_csv(out / "records.csv", rows)
    print(summary)


if __name__ == "__main__":
    main()
