from decimal import Decimal
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone, timedelta
from fastapi import HTTPException


def _make_run(name="analyze_one", status="success", latency_s=2.8,
              prompt=100, completion=50, run_id="run-abc",
              total_cost=None, prompt_cost=None, completion_cost=None):
    run = MagicMock()
    run.id = run_id
    run.name = name
    run.status = status
    run.prompt_tokens = prompt
    run.completion_tokens = completion
    run.total_cost = total_cost
    run.prompt_cost = prompt_cost
    run.completion_cost = completion_cost
    run.error = None if status == "success" else "timeout"
    now = datetime.now(timezone.utc)
    run.start_time = now - timedelta(seconds=latency_s)
    run.end_time = now
    return run


@patch("routers.langsmith.Client")
def test_stats_returns_aggregated_metrics(mock_client_cls):
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_client.list_runs.return_value = [
        _make_run(status="success", latency_s=10.0, prompt=100, completion=50, run_id="run-1", name="old_run",
                  total_cost=Decimal("0.01"), prompt_cost=Decimal("0.003"), completion_cost=Decimal("0.007")),
        _make_run(status="success", latency_s=2.0,  prompt=200, completion=80, run_id="run-2", name="recent_run",
                  total_cost=Decimal("0.02"), prompt_cost=Decimal("0.008"), completion_cost=Decimal("0.012")),
        _make_run(status="error",   latency_s=5.0,  prompt=0,   completion=0,  run_id="run-3", name="mid_run"),
    ]

    from routers.langsmith import stats
    data = stats()
    assert data["total_runs"] == 3
    assert data["success_count"] == 2
    assert data["error_count"] == 1
    assert data["success_rate"] == 66.7
    assert data["avg_latency_ms"] == 5667
    assert data["total_prompt_tokens"] == 300
    assert data["total_completion_tokens"] == 130
    assert data["total_observed_cost_usd"] == 0.03
    assert data["prompt_observed_cost_usd"] == 0.011
    assert data["completion_observed_cost_usd"] == 0.019
    assert len(data["recent_runs"]) == 3
    assert data["recent_runs"][0]["name"] == "recent_run"
    assert mock_client.list_runs.call_args.kwargs["limit"] == 100


@patch("routers.langsmith.Client")
def test_stats_no_runs_returns_zeros(mock_client_cls):
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_client.list_runs.return_value = []

    from routers.langsmith import stats
    data = stats()
    assert data["total_runs"] == 0
    assert data["success_rate"] == 0.0
    assert data["avg_latency_ms"] == 0
    assert data["recent_runs"] == []


@patch("routers.langsmith.Client")
def test_stats_missing_api_key_returns_503(mock_client_cls, monkeypatch):
    monkeypatch.delenv("LANGCHAIN_API_KEY", raising=False)
    mock_client_cls.side_effect = Exception("No API key")

    from routers.langsmith import stats
    try:
        stats()
    except HTTPException as exc:
        assert exc.status_code == 503
        assert "LangSmith unavailable" in exc.detail
    else:
        raise AssertionError("Expected HTTPException")
