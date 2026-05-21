"""
nodes/ingest/cli.py — Standalone CLI entry point for the ingestion node.

Usage: python -m nodes.ingest.cli --from 1 --to 5
"""

import argparse

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from .core import run_ingest


def main():
    parser = argparse.ArgumentParser(
        description="Ingest Mars2020 Mastcam-Z products into GCS + (optional) Postgres index")
    parser.add_argument("--from", dest="from_n", type=int, default=1,
                        help="1-based index in products stream to start from")
    parser.add_argument("--to", dest="to_n", type=int, default=3,
                        help="1-based index in products stream to stop at (inclusive)")
    args = parser.parse_args()

    if args.from_n < 1:
        args.from_n = 1
    if args.to_n < args.from_n:
        raise SystemExit(f"--to ({args.to_n}) must be >= --from ({args.from_n})")

    state = {
        "from_n": args.from_n, "to_n": args.to_n,
        "status": "", "processed": 0, "summary": "", "messages": [],
    }
    run_ingest(state)


if __name__ == "__main__":
    main()
