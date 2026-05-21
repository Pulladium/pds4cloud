"""
nodes/finalize.py — Finalize node.

Marks the pipeline as complete and records a final trace message.
"""


def run_finalize(state) -> dict:
    return {
        "status": "complete",
        "messages": list(state.get("messages", [])) + ["finalize: pipeline complete"],
    }
