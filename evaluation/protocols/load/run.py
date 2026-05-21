from __future__ import annotations

import argparse
import concurrent.futures
import time
from pathlib import Path

from evaluation.eval_lib import env, http_json, load_cases, summarize_records, write_csv, write_json


def run_one(orchtr: str, lid: str, case_id: str) -> dict:
    started = time.time()
    status = "COMPLETED"
    error = None
    try:
        http_json("POST", f"{orchtr.rstrip('/')}/api/process", {"lid": lid}, timeout=1200)
    except Exception as exc:
        status = "FAILED"
        error = str(exc)
    finished = time.time()
    return {"protocol": "load_direct", "job_id": case_id, "image_count": 1, "status": status, "started_at": started, "finished_at": finished, "duration_seconds": round(finished - started, 4), "cost_usd": 0, "error": error}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run simple concurrent load protocol against Orchestrator")
    parser.add_argument("--cases", default="evaluation/cases.yml")
    parser.add_argument("--orchtr", default=env("ORCHTR_URL", "http://orchtr:8000"))
    parser.add_argument("--concurrency", type=int, default=2)
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--max-cases", type=int, default=2)
    parser.add_argument("--out", default="evaluation/protocols/load/results")
    args = parser.parse_args()
    base_cases = load_cases(args.cases)[: args.max_cases]
    jobs = []
    for rep in range(args.repetitions):
        for case in base_cases:
            jobs.append((args.orchtr, case["lid"], f"{case.get('id')}-r{rep}"))
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        rows = list(pool.map(lambda x: run_one(*x), jobs))
    summary = summarize_records(rows)
    out = Path(args.out)
    write_json(out / "records.json", rows)
    write_json(out / "summary.json", summary)
    write_csv(out / "records.csv", rows)
    print(summary)


if __name__ == "__main__":
    main()
