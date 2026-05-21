from __future__ import annotations

import argparse
import time
from pathlib import Path

from evaluation.eval_lib import assert_protocol_condition, env, http_json, load_cases, write_csv, write_json


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the same product twice and record artifact reuse/idempotency evidence")
    parser.add_argument("--cases", default="evaluation/cases.yml")
    parser.add_argument("--orchtr", default=env("ORCHTR_URL", "http://orchtr:8000"))
    parser.add_argument("--out", default="evaluation/protocols/idempotency/results")
    args = parser.parse_args()
    case = load_cases(args.cases)[0]
    rows = []
    previous = None
    artifact_keys = ("gray_path", "rgb_path", "result_path", "analysis_id")
    for run in (1, 2):
        started = time.time()
        status = "COMPLETED"
        error = None
        response = {}
        try:
            response = http_json("POST", f"{args.orchtr.rstrip('/')}/api/process", {"lid": case["lid"]}, timeout=1200)
        except Exception as exc:
            status = "FAILED"
            error = str(exc)
        finished = time.time()
        same_paths = bool(previous and response and all(response.get(k) and response.get(k) == previous.get(k) for k in artifact_keys))
        rows.append({
            "protocol": "idempotency",
            "job_id": f"{case.get('id')}-run-{run}",
            "image_count": 1,
            "status": status,
            "started_at": started,
            "finished_at": finished,
            "duration_seconds": round(finished - started, 4),
            "same_artifact_paths_as_previous": same_paths,
            "gray_path": response.get("gray_path"),
            "rgb_path": response.get("rgb_path"),
            "result_path": response.get("result_path"),
            "analysis_id": response.get("analysis_id"),
            "cost_usd": response.get("cost_usd") or 0,
            "error": error,
        })
        if response:
            previous = response
    out = Path(args.out)
    summary = {
        "jobs": len(rows),
        "images": len(rows),
        "successful_runs": sum(1 for row in rows if row["status"] == "COMPLETED"),
        "same_artifact_paths_on_second_run": rows[-1].get("same_artifact_paths_as_previous", False),
        "first_duration_seconds": rows[0]["duration_seconds"],
        "second_duration_seconds": rows[1]["duration_seconds"],
    }
    write_json(out / "records.json", rows)
    write_csv(out / "records.csv", rows)
    write_json(out / "summary.json", summary)
    assert_protocol_condition(len(rows) == 2, "idempotency protocol must run exactly twice")
    assert_protocol_condition(rows[0]["status"] == "COMPLETED", "first idempotency run must complete successfully")
    assert_protocol_condition(rows[1]["status"] == "COMPLETED", "second idempotency run must complete successfully")
    for row in rows:
        assert_protocol_condition(
            all(row.get(key) for key in artifact_keys),
            f"{row['job_id']} must report gray_path, rgb_path, result_path, and analysis_id",
        )
    assert_protocol_condition(
        rows[1].get("same_artifact_paths_as_previous") is True,
        "idempotency protocol must reuse artifact paths on the second successful run",
    )
    print(rows[-1])


if __name__ == "__main__":
    main()
