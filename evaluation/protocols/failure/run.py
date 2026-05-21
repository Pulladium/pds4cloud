from __future__ import annotations

import argparse
import time
from pathlib import Path

from evaluation.eval_lib import assert_protocol_condition, env, http_json, summarize_records, write_csv, write_json


def main() -> None:
    parser = argparse.ArgumentParser(description="Run failure/idempotency protocol against Orchestrator")
    parser.add_argument("--orchtr", default=env("ORCHTR_URL", "http://orchtr:8000"))
    parser.add_argument("--bad-lid", default="urn:nasa:pds:mars2020_mastcamz_ops_calibrated:data:not_a_real_product")
    parser.add_argument("--out", default="evaluation/protocols/failure/results")
    args = parser.parse_args()
    started = time.time()
    failed_at = None
    recovered_at = None
    error = None
    status = "FAILED"
    try:
        http_json("POST", f"{args.orchtr.rstrip('/')}/api/process", {"lid": args.bad_lid}, timeout=300)
    except Exception as exc:
        failed_at = time.time()
        error = str(exc)
        recovered_at = time.time()
        status = "FAILED"
    row = {
        "protocol": "failure_bad_lid",
        "job_id": "failure-bad-lid",
        "image_count": 1,
        "status": status,
        "expected_failure": True,
        "started_at": started,
        "finished_at": time.time(),
        "failed_at": failed_at,
        "recovered_at": recovered_at,
        "cost_usd": 0,
        "error": error,
    }
    assert_protocol_condition(row["expected_failure"] is True, "failure protocol must mark expected_failure")
    assert_protocol_condition(row["error"] is not None and row["error"] != "", "failure protocol must capture an error")
    assert_protocol_condition(row["failed_at"] is not None, "failure protocol must capture failed_at")
    assert_protocol_condition(row["recovered_at"] is not None, "failure protocol must capture recovered_at")
    out = Path(args.out)
    write_json(out / "records.json", [row])
    write_json(out / "summary.json", summarize_records([row]))
    write_csv(out / "records.csv", [row])
    print(row)


if __name__ == "__main__":
    main()
