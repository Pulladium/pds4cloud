from __future__ import annotations

import json
import os
from pathlib import Path


PROTOCOLS_ROOT = Path("evaluation/protocols")
SUMMARY_PATH = Path("evaluation/summary.md")


def load_json_object(path: Path, warnings: list[str]) -> dict | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        warnings.append(f"{path}: {exc}")
        return None
    if not isinstance(payload, dict):
        warnings.append(f"{path}: expected JSON object, got {type(payload).__name__}")
        return None
    return payload


def main() -> None:
    root = PROTOCOLS_ROOT
    warnings = []
    summaries = []
    for path in sorted(root.glob("*/results/summary.json")):
        payload = load_json_object(path, warnings)
        if payload is None:
            continue
        payload["protocol"] = path.parent.parent.name
        summaries.append(payload)
    lines = [
        "# Evaluation Summary",
        "",
        "| Protocol | Jobs | Images | Failure rate | Throughput img/min | Workers | Max concurrent workers | Cost USD |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for s in summaries:
        lines.append(
            f"| {s.get('protocol')} | {s.get('jobs', 0)} | {s.get('images', 0)} | "
            f"{s.get('failure_rate', 0)} | {s.get('throughput_images_per_minute', 0)} | "
            f"{s.get('distinct_worker_count', 0)} | {s.get('max_concurrent_workers_observed', 0)} | "
            f"{s.get('total_cost_usd', 0)} |"
        )

    comparisons = []
    for path in sorted(root.glob("*/results/comparison.json")):
        payload = load_json_object(path, warnings)
        if payload is None:
            continue
        payload["protocol"] = path.parent.parent.name
        comparisons.append(payload)
    if comparisons:
        lines.extend([
            "",
            "## Protocol Comparisons",
            "",
            "| Protocol | Reference duration s | Proposed duration s | Saved % | Cost delta USD | Worker delta |",
            "|---|---:|---:|---:|---:|---:|",
        ])
        for c in comparisons:
            lines.append(
                f"| {c.get('protocol')} | {c.get('reference_duration_seconds', 0)} | "
                f"{c.get('proposed_duration_seconds', 0)} | {c.get('duration_saved_percent', 0)} | "
                f"{c.get('cost_delta_usd', 0)} | {c.get('worker_count_delta', 0)} |"
            )

    txt_outputs = sorted(root.glob("*/results/*.txt"))
    if txt_outputs:
        lines.extend([
            "",
            "## Thesis Text Tables",
            "",
        ])
        for path in txt_outputs:
            lines.append(f"- `{path.relative_to(SUMMARY_PATH.parent).as_posix()}`")

    if warnings:
        lines.extend([
            "",
            "## Warnings",
            "",
            "Skipped unreadable or malformed JSON files:",
            "",
        ])
        lines.extend(f"- `{warning}`" for warning in warnings)

    out = SUMMARY_PATH
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(f".{out.name}.{os.getpid()}.tmp")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    tmp.replace(out)
    print(out)


if __name__ == "__main__":
    main()
