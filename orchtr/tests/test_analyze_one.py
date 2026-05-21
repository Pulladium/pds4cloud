import json
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient


def _fake_storage(existing_bytes: bytes | None = None):
    store = {}
    s = MagicMock()
    s.exists.side_effect = lambda p: p in store
    s.download_bytes.side_effect = lambda p: store[p]

    def upload(path, data, ct):
        store[path] = data
        return True

    s.upload_bytes.side_effect = upload
    return s, store


def _mock_openai_client(prompt_tokens=120, completion_tokens=60):
    analysis_json = json.dumps({
        "geological_features": "basalt",
        "spectral_interpretation": "iron oxide",
        "scientific_significance": "high",
        "data_quality": "good",
        "hypotheses": ["volcanic origin"],
        "recommended_followup": "none",
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "model": "gpt-4o",
        "cost_usd": None,
    })

    choice = MagicMock()
    choice.message.content = analysis_json

    usage = MagicMock()
    usage.prompt_tokens = prompt_tokens
    usage.completion_tokens = completion_tokens

    resp = MagicMock()
    resp.choices = [choice]
    resp.usage = usage
    resp.model = "gpt-4o"

    client = MagicMock()
    client.chat.completions.create.return_value = resp
    return client


def _reset_db():
    from database import Base, engine

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def _state():
    return {
        "product_lid": "urn:test:pid1",
        "photo_id": "pid1",
        "sol": "00001",
        "project_id": "project-1",
        "job_id": "job-1",
        "user_id": "user-1",
        "messages": [],
    }


def _artifact_rows():
    from database import SessionLocal
    from models import AnalysisArtifact

    db = SessionLocal()
    try:
        return db.query(AnalysisArtifact).all()
    finally:
        db.close()


def test_run_analyze_one_returns_token_fields():
    storage, store = _fake_storage()
    store["transformed/mastcamz/sol=00001/pid1/gray.jpg"] = b"fakeimg"

    state = _state()

    with (
        patch("nodes.analyze.one.get_storage_adapter", return_value=storage),
        patch("nodes.analyze.one.OpenAI", return_value=_mock_openai_client(120, 60)),
        patch.dict("os.environ", {"OPENAI_API_KEY": "fake-key"}, clear=False),
        patch("nodes.analyze.db.pg_mark_analysis_running"),
        patch("nodes.analyze.db.pg_mark_analysis_done"),
    ):
        _reset_db()
        from nodes.analyze.one import run_analyze_one
        result = run_analyze_one(state)

    assert result["prompt_tokens"] == 120
    assert result["completion_tokens"] == 60
    assert result["model"] == "gpt-4o"
    assert result["cost_usd"] is None


def test_run_analyze_one_creates_versioned_artifact_and_returns_analysis_id():
    storage, store = _fake_storage()
    store["transformed/mastcamz/sol=00001/pid1/gray.jpg"] = b"fakeimg"
    state = {
        "product_lid": "urn:test:pid1",
        "photo_id": "pid1",
        "sol": "00001",
        "project_id": "project-1",
        "job_id": "job-1",
        "user_id": "user-1",
        "model": "gpt-4o",
        "messages": [],
    }

    with (
        patch("nodes.analyze.one.get_storage_adapter", return_value=storage),
        patch("nodes.analyze.one.OpenAI", return_value=_mock_openai_client(120, 60)),
        patch.dict("os.environ", {"OPENAI_API_KEY": "fake-key"}, clear=False),
        patch("nodes.analyze.db.pg_mark_analysis_running"),
        patch("nodes.analyze.db.pg_mark_analysis_done"),
    ):
        from database import Base, engine
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        from nodes.analyze.one import run_analyze_one
        result = run_analyze_one(state)

    assert result["analysis_id"]
    assert result["result_path"] == f"analysis/mastcamz/sol=00001/pid1/{result['analysis_id']}/result.json"
    assert result["result_path"] in store
    artifacts = _artifact_rows()
    assert len(artifacts) == 1
    artifact = artifacts[0]
    assert artifact.id == result["analysis_id"]
    assert artifact.status == "READY"
    assert artifact.result_path == result["result_path"]
    assert artifact.product_lid == "urn:test:pid1"
    assert artifact.project_id == "project-1"
    assert artifact.job_id == "job-1"
    assert artifact.user_id == "user-1"
    assert artifact.model == "gpt-4o"


def test_run_analyze_one_defaults_missing_project_and_job_ids_to_empty_strings():
    storage, store = _fake_storage()
    store["transformed/mastcamz/sol=00001/pid1/gray.jpg"] = b"fakeimg"
    state = {
        "product_lid": "urn:test:pid1",
        "photo_id": "pid1",
        "sol": "00001",
        "model": "gpt-4o",
        "messages": [],
    }

    with (
        patch("nodes.analyze.one.get_storage_adapter", return_value=storage),
        patch("nodes.analyze.one.OpenAI", return_value=_mock_openai_client(120, 60)),
        patch.dict("os.environ", {"OPENAI_API_KEY": "fake-key"}, clear=False),
        patch("nodes.analyze.db.pg_mark_analysis_running"),
        patch("nodes.analyze.db.pg_mark_analysis_done"),
    ):
        _reset_db()
        from nodes.analyze.one import run_analyze_one
        result = run_analyze_one(state)

    assert result["status"] == "analyze_ok"
    assert result["analysis_id"]
    assert result["result_path"] == f"analysis/mastcamz/sol=00001/pid1/{result['analysis_id']}/result.json"
    assert result["result_path"] in store
    artifacts = _artifact_rows()
    assert len(artifacts) == 1
    artifact = artifacts[0]
    assert artifact.id == result["analysis_id"]
    assert artifact.project_id == ""
    assert artifact.job_id == ""


def test_run_analyze_one_reuses_existing_completed_artifact_for_same_scope():
    storage, store = _fake_storage()
    existing_payload = {
        "analysis": {
            "data_quality": "good",
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "model": "gpt-4o",
            "cost_usd": 0.01,
        }
    }
    state = _state()

    with (
        patch("nodes.analyze.one.get_storage_adapter", return_value=storage),
        patch.dict("os.environ", {"OPENAI_API_KEY": "fake-key"}, clear=False),
    ):
        _reset_db()
        from database import SessionLocal
        from services.analysis_artifacts import mark_ready, reserve_analysis
        from nodes.analyze.one import run_analyze_one

        db = SessionLocal()
        artifact = reserve_analysis(db, "urn:test:pid1", "pid1", "00001", "project-1", "job-1", "user-1", "gpt-4o")
        mark_ready(db, artifact.id)
        db.close()
        store[artifact.result_path] = json.dumps(existing_payload).encode("utf-8")

        with patch("nodes.analyze.one.OpenAI") as openai:
            result = run_analyze_one(state)

    assert result["status"] == "analyze_skip"
    assert result["analysis_id"] == artifact.id
    assert result["result_path"] == artifact.result_path
    assert result["prompt_tokens"] == 10
    openai.assert_not_called()
    assert len(_artifact_rows()) == 1


def test_run_analyze_one_reuses_older_ready_artifact_when_latest_path_is_missing():
    storage, store = _fake_storage()
    state = _state()

    with (
        patch("nodes.analyze.one.get_storage_adapter", return_value=storage),
        patch.dict("os.environ", {"OPENAI_API_KEY": "fake-key"}, clear=False),
    ):
        _reset_db()
        from database import SessionLocal
        from services.analysis_artifacts import mark_ready, reserve_analysis
        from nodes.analyze.one import run_analyze_one

        db = SessionLocal()
        older = reserve_analysis(db, "urn:test:pid1", "pid1", "00001", "project-1", "job-old", "user-1", "gpt-4o")
        newer = reserve_analysis(db, "urn:test:pid1", "pid1", "00001", "project-1", "job-new", "user-1", "gpt-4o")
        mark_ready(db, older.id)
        mark_ready(db, newer.id)
        older_id = older.id
        older_path = older.result_path
        db.close()
        store[older_path] = json.dumps({"analysis": {"data_quality": "older"}}).encode("utf-8")

        with patch("nodes.analyze.one.OpenAI") as openai:
            result = run_analyze_one(state)

    assert result["status"] == "analyze_skip"
    assert result["analysis_id"] == older_id
    assert result["result_path"] == older_path
    openai.assert_not_called()
    assert len(_artifact_rows()) == 2


def test_run_analyze_one_wraps_openai_client_for_langsmith():
    storage, store = _fake_storage()
    store["transformed/mastcamz/sol=00001/pid1/gray.jpg"] = b"fakeimg"
    openai_client = _mock_openai_client(120, 60)

    state = _state()

    with (
        patch("nodes.analyze.one.get_storage_adapter", return_value=storage),
        patch("nodes.analyze.one.OpenAI", return_value=openai_client),
        patch("nodes.analyze.one.wrap_openai", return_value=openai_client) as wrap_openai,
        patch.dict("os.environ", {"OPENAI_API_KEY": "fake-key"}, clear=False),
        patch("nodes.analyze.db.pg_mark_analysis_running"),
        patch("nodes.analyze.db.pg_mark_analysis_done"),
    ):
        _reset_db()
        from nodes.analyze.one import run_analyze_one
        run_analyze_one(state)

    wrap_openai.assert_called_once_with(openai_client)


def test_run_analyze_one_skips_without_openai_api_key_and_no_analysis_id():
    storage, store = _fake_storage()
    store["transformed/mastcamz/sol=00001/pid1/gray.jpg"] = b"fakeimg"
    state = _state()

    with (
        patch("nodes.analyze.one.get_storage_adapter", return_value=storage),
        patch.dict("os.environ", {}, clear=True),
        patch("nodes.analyze.db.pg_mark_analysis_done"),
    ):
        from nodes.analyze.one import run_analyze_one
        result = run_analyze_one(state)

    assert result["status"] == "analyze_skipped"
    assert result["analysis_id"] is None
    assert result["result_path"] is None


def test_run_analyze_one_propagates_analysis_errors():
    storage, store = _fake_storage()
    store["transformed/mastcamz/sol=00001/pid1/gray.jpg"] = b"fakeimg"

    state = _state()

    with (
        patch("nodes.analyze.one.get_storage_adapter", return_value=storage),
        patch("nodes.analyze.one.OpenAI", return_value=MagicMock()),
        patch("nodes.analyze.one.wrap_openai", return_value=MagicMock()),
        patch.dict("os.environ", {"OPENAI_API_KEY": "fake-key"}, clear=False),
        patch("nodes.analyze.one.analyze_one_task", return_value={
            "status": "error",
            "photo_id": "pid1",
            "error": "Unsupported parameter: max_tokens",
        }),
    ):
        _reset_db()
        from nodes.analyze.one import run_analyze_one
        result = run_analyze_one(state)

    assert result["status"] == "error_analyze"
    assert result["error"] == "Unsupported parameter: max_tokens"
    assert result["analysis"] == {}


def test_run_analyze_one_marks_artifact_failed_when_task_raises_after_reservation():
    storage, store = _fake_storage()
    store["transformed/mastcamz/sol=00001/pid1/gray.jpg"] = b"fakeimg"
    state = _state()

    with (
        patch("nodes.analyze.one.get_storage_adapter", return_value=storage),
        patch("nodes.analyze.one.OpenAI", return_value=MagicMock()),
        patch("nodes.analyze.one.wrap_openai", return_value=MagicMock()),
        patch.dict("os.environ", {"OPENAI_API_KEY": "fake-key"}, clear=False),
        patch("nodes.analyze.one.analyze_one_task", side_effect=RuntimeError("boom")),
    ):
        _reset_db()
        from nodes.analyze.one import run_analyze_one
        result = run_analyze_one(state)

    from database import SessionLocal
    from models import AnalysisArtifact

    db = SessionLocal()
    try:
        artifacts = db.query(AnalysisArtifact).all()
        assert len(artifacts) == 1
        artifact = artifacts[0]
        assert artifact.status == "FAILED"
        assert "boom" in artifact.error
    finally:
        db.close()

    assert result["status"] == "error_analyze"
    assert "boom" in result["error"]


def test_process_api_passes_user_id_and_returns_analysis_id():
    from server import app

    process_result = {
        "photo_id": "pid1",
        "sol": "00001",
        "status": "ok",
        "gray_path": "gray.jpg",
        "rgb_path": "rgb.jpg",
        "result_path": "analysis/result.json",
        "analysis_id": "analysis-1",
        "analysis": {"data_quality": "good"},
        "messages": [],
    }
    storage = MagicMock()
    storage.exists.return_value = False

    with (
        patch("server.process_product", return_value=process_result) as process_product,
        patch("server.get_storage_adapter", return_value=storage),
        TestClient(app) as client,
    ):
        response = client.post(
            "/api/process",
            json={"lid": "urn:test:pid1"},
            headers={"X-User-Id": "user-1"},
        )

    assert response.status_code == 200
    assert response.json()["analysis_id"] == "analysis-1"
    process_product.assert_called_once_with("urn:test:pid1", user_id="user-1")


def test_result_api_reads_latest_versioned_analysis_artifact():
    from server import app
    from database import Base, engine, SessionLocal
    from services.analysis_artifacts import mark_ready, reserve_analysis

    storage, store = _fake_storage()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    artifact = reserve_analysis(db, "urn:test:pid1", "pid1", "00001", "project-1", "job-1", "user-1", "gpt-4o")
    mark_ready(db, artifact.id)
    db.close()
    store[artifact.result_path] = json.dumps({"analysis": {"data_quality": "good"}}).encode("utf-8")

    with (
        patch("server.get_storage_adapter", return_value=storage),
        TestClient(app) as client,
    ):
        response = client.get("/api/result/00001/pid1")

    assert response.status_code == 200
    assert response.json()["analysis"] == {"data_quality": "good"}


def test_result_api_falls_back_when_latest_versioned_artifact_is_missing():
    from server import app
    from database import Base, engine, SessionLocal
    from services.analysis_artifacts import mark_ready, reserve_analysis

    storage, store = _fake_storage()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    artifact = reserve_analysis(db, "urn:test:pid1", "pid1", "00001", "project-1", "job-1", "user-1", "gpt-4o")
    mark_ready(db, artifact.id)
    db.close()
    legacy_path = "analysis/mastcamz/sol=00001/pid1/result.json"
    store[legacy_path] = json.dumps({"analysis": {"data_quality": "legacy"}}).encode("utf-8")

    with (
        patch("server.get_storage_adapter", return_value=storage),
        TestClient(app) as client,
    ):
        response = client.get("/api/result/00001/pid1")

    assert response.status_code == 200
    assert response.json()["analysis"] == {"data_quality": "legacy"}


def test_result_api_reads_older_versioned_artifact_when_latest_path_is_missing():
    from server import app
    from database import Base, engine, SessionLocal
    from services.analysis_artifacts import mark_ready, reserve_analysis

    storage, store = _fake_storage()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    older = reserve_analysis(db, "urn:test:pid1", "pid1", "00001", "project-1", "job-old", "user-1", "gpt-4o")
    newer = reserve_analysis(db, "urn:test:pid1", "pid1", "00001", "project-1", "job-new", "user-1", "gpt-4o")
    mark_ready(db, older.id)
    mark_ready(db, newer.id)
    older_path = older.result_path
    db.close()
    store[older_path] = json.dumps({"analysis": {"data_quality": "older"}}).encode("utf-8")

    with (
        patch("server.get_storage_adapter", return_value=storage),
        TestClient(app) as client,
    ):
        response = client.get("/api/result/00001/pid1")

    assert response.status_code == 200
    assert response.json()["analysis"] == {"data_quality": "older"}
