from __future__ import annotations

import argparse
import time
from pathlib import Path

from evaluation.eval_lib import env, http_json, load_cases, summarize_records, write_json, write_csv


def main() -> None:
    parser = argparse.ArgumentParser(description="Run ingest-transform-analyze-export smoke protocol through Orchestrator /api/process")
    parser.add_argument("--cases", default="evaluation/cases.yml")
    parser.add_argument("--orchtr", default=env("ORCHTR_URL", "http://orchtr:8000"))
    parser.add_argument("--max-cases", type=int, default=2)
    parser.add_argument("--out", default="evaluation/protocols/functional/results")
    args = parser.parse_args()

    rows = []
    for case in load_cases(args.cases)[: args.max_cases]:
        started = time.time()
        status = "COMPLETED"
        error = None
        response = {}
        try:
            response = http_json("POST", f"{args.orchtr.rstrip('/')}/api/process", {"lid": case["lid"]})
            required = ["gray_path", "result_path", "analysis"]
            missing = [k for k in required if not response.get(k)]
            if missing:
                raise RuntimeError(f"missing expected outputs: {missing}")
        except Exception as exc:
            status = "FAILED"
            error = str(exc)
        finished = time.time()
        rows.append({
            "protocol": "functional_e2e",
            "case_id": case.get("id"),
            "job_id": case.get("id"),
            "image_count": 1,
            "status": status,
            "started_at": started,
            "finished_at": finished,
            "duration_seconds": round(finished - started, 4),
            "cost_usd": response.get("analysis", {}).get("cost_usd") or response.get("cost_usd") or 0,
            "photo_id": response.get("photo_id"),
            "sol": response.get("sol"),
            "gray_path": response.get("gray_path"),
            "rgb_path": response.get("rgb_path"),
            "result_path": response.get("result_path"),
            "error": error,
        })
    summary = summarize_records(rows)
    out = Path(args.out)
    write_json(out / "records.json", rows)
    write_json(out / "summary.json", summary)
    write_csv(out / "records.csv", rows)
    print(summary)


if __name__ == "__main__":
    main()
