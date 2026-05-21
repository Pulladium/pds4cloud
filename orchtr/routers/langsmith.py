import os
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException
from langsmith import Client

router = APIRouter(prefix="/api/langsmith", tags=["langsmith"])


def _latency_ms(run) -> float:
    if run.start_time and run.end_time:
        return (run.end_time - run.start_time).total_seconds() * 1000
    return 0.0


def _cost_value(value) -> float:
    return float(value or 0)


@router.get("/stats")
def stats():
    api_key = os.environ.get("LANGSMITH_API_KEY") or os.environ.get("LANGCHAIN_API_KEY")
    api_url = os.environ.get("LANGSMITH_ENDPOINT") or os.environ.get("LANGCHAIN_ENDPOINT")
    project = os.environ.get("LANGSMITH_PROJECT") or os.environ.get("LANGCHAIN_PROJECT", "mars2020")
    try:
        client = Client(api_key=api_key, api_url=api_url)
        since = datetime.now(timezone.utc) - timedelta(days=7)
        runs = list(client.list_runs(project_name=project, start_time=since, limit=100))
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"LangSmith unavailable: {exc}")

    total = len(runs)
    success = sum(1 for r in runs if r.status == "success")
    errors  = sum(1 for r in runs if r.status == "error")

    latencies = [_latency_ms(r) for r in runs if r.start_time and r.end_time]
    avg_latency = sum(latencies) / len(latencies) if latencies else 0.0

    prompt_tokens     = sum(r.prompt_tokens or 0 for r in runs)
    completion_tokens = sum(r.completion_tokens or 0 for r in runs)
    observed_cost     = sum(_cost_value(getattr(r, "total_cost", None)) for r in runs)
    prompt_cost       = sum(_cost_value(getattr(r, "prompt_cost", None)) for r in runs)
    completion_cost   = sum(_cost_value(getattr(r, "completion_cost", None)) for r in runs)

    recent = sorted(
        runs,
        key=lambda r: r.start_time or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )[:10]
    recent_runs = [
        {
            "id":         str(r.id),
            "name":       r.name or "",
            "status":     r.status or "unknown",
            "latency_ms": round(_latency_ms(r)),
            "start_time": r.start_time.isoformat() if r.start_time else None,
        }
        for r in recent
    ]

    return {
        "total_runs":              total,
        "success_count":           success,
        "error_count":             errors,
        "success_rate":            round(success / total * 100, 1) if total else 0.0,
        "avg_latency_ms":          round(avg_latency),
        "total_prompt_tokens":     prompt_tokens,
        "total_completion_tokens": completion_tokens,
        "total_observed_cost_usd": round(observed_cost, 8),
        "prompt_observed_cost_usd": round(prompt_cost, 8),
        "completion_observed_cost_usd": round(completion_cost, 8),
        "recent_runs":             recent_runs,
    }
