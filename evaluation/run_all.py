from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path


PROTOCOLS = Path("evaluation/protocols")
SUMMARY = Path("evaluation/summary.md")


def _run(module: str, *args: str) -> None:
    cmd = [sys.executable, "-m", module, *args]
    print("$ " + " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True)


def _avg_cost_per_image() -> str:
    path = PROTOCOLS / "multi_user_project" / "results" / "summary.json"
    try:
        summary = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return "0"
    images = int(summary.get("images") or 0)
    cost = float(summary.get("total_cost_usd") or 0)
    return str(round(cost / images, 8) if images else 0)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the full reproducible thesis evaluation protocol")
    parser.add_argument("--clean", action="store_true", help="Remove previous protocol result directories before running")
    parser.add_argument("--skip-sequential-reference", action="store_true", help="Skip sequential reference")
    parser.add_argument("--skip-single-user", action="store_true", help="Skip single-user worker probe")
    args = parser.parse_args()

    if args.clean:
        for path in PROTOCOLS.glob("*/results"):
            shutil.rmtree(path, ignore_errors=True)
        SUMMARY.unlink(missing_ok=True)

    _run("evaluation.reset_eval_state")
    _run("evaluation.reset_eval_state", "--apply")
    _run("evaluation.protocols.multi_user_project.run")

    if not args.skip_sequential_reference:
        _run("evaluation.reset_eval_state", "--apply")
        _run("evaluation.protocols.sequential_reference.run")

    if not args.skip_single_user:
        _run("evaluation.protocols.single_user_5_image_probe.run")

    _run("evaluation.protocols.functional.run")
    _run("evaluation.protocols.failure.run")
    _run("evaluation.protocols.idempotency.run")
    _run("evaluation.protocols.limits.run", "--avg-cost-per-image", _avg_cost_per_image())
    _run("evaluation.protocols.load.run")
    _run("evaluation.report")


if __name__ == "__main__":
    main()
