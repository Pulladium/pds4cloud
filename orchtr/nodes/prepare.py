"""
nodes/prepare.py — Prepare node.

Receives ingestion results from state and builds a human-readable summary.
"""


def run_prepare(state) -> dict:
    processed   = state["processed"]
    transformed = state.get("transformed", 0)
    analyzed    = state.get("analyzed", 0)
    from_n      = state["from_n"]
    to_n        = state["to_n"]

    summary = (
        f"Mastcam-Z ingest complete: {processed} products processed "
        f"from index {from_n} to {to_n}. "
        f"Transformed: {transformed} photos. "
        f"Analyzed: {analyzed} photos."
    )

    return {
        "summary": summary,
        "status": "prepared",
        "messages": list(state.get("messages", [])) + [
            f"prepare: summary built ({len(summary)} chars)"
        ],
    }
