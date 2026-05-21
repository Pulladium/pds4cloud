import json
from unittest.mock import MagicMock, patch

from nodes.analyze.logic import _call_openai, analyze_one_task


def _make_openai_response(model="gpt-4o-mini"):
    analysis_json = json.dumps({
        "geological_features": "Basalt outcrop",
        "spectral_interpretation": "Iron oxide",
        "scientific_significance": "High",
        "data_quality": "Good",
        "hypotheses": ["Volcanic origin"],
        "recommended_followup": "Closer inspection",
    })
    resp = MagicMock()
    resp.choices[0].message.content = analysis_json
    resp.usage.prompt_tokens = 100
    resp.usage.completion_tokens = 50
    resp.model = model
    return resp


def test_call_openai_uses_provided_model():
    client = MagicMock()
    client.chat.completions.create.return_value = _make_openai_response("gpt-4o-mini")

    result = _call_openai(b"fake-image", {"sol": "42"}, {}, client, model="gpt-4o-mini")

    call_kwargs = client.chat.completions.create.call_args[1]
    assert call_kwargs["model"] == "gpt-4o-mini"
    assert result["model"] == "gpt-4o-mini"
    assert result["prompt_tokens"] == 100
    assert result["completion_tokens"] == 50
    assert result["cost_usd"] is None


def test_call_openai_does_not_send_token_limit_for_gpt5():
    client = MagicMock()
    client.chat.completions.create.return_value = _make_openai_response("gpt-5")

    _call_openai(b"fake-image", {"sol": "42"}, {}, client, model="gpt-5")

    call_kwargs = client.chat.completions.create.call_args[1]
    assert "max_completion_tokens" not in call_kwargs
    assert "max_tokens" not in call_kwargs


def test_call_openai_does_not_send_token_limit_for_older_chat_models():
    client = MagicMock()
    client.chat.completions.create.return_value = _make_openai_response("gpt-4o")

    _call_openai(b"fake-image", {"sol": "42"}, {}, client, model="gpt-4o")

    call_kwargs = client.chat.completions.create.call_args[1]
    assert "max_tokens" not in call_kwargs
    assert "max_completion_tokens" not in call_kwargs


def test_call_openai_puts_full_metadata_json_in_user_prompt():
    client = MagicMock()
    client.chat.completions.create.return_value = _make_openai_response("gpt-4o")
    metadata = {
        "properties": {
            "img_surface:Instrument_Information.img_surface:image_type": ["THUMBNAIL"],
            "mars2020:Observation_Information.mars2020:sol_number": [94],
            "pds:Primary_Result_Summary.pds:processing_level": ["Partially Processed"],
            "test:large_field": "massive metadata text",
        }
    }

    _call_openai(b"fake-image", metadata, {}, client, model="gpt-4o", metadata_loaded=True)

    call_kwargs = client.chat.completions.create.call_args[1]
    prompt = call_kwargs["messages"][0]["content"][0]["text"]
    assert "Full raw metadata loaded: yes" in prompt
    assert "Image Type: THUMBNAIL" in prompt
    assert "Sol:        94" in prompt
    assert "FULL RAW PDS METADATA JSON:" in prompt
    assert '"test:large_field": "massive metadata text"' in prompt


def test_analyze_one_task_passes_model_to_openai():
    storage = MagicMock()
    # First exists() call is for result_path (idempotency check) → False
    # Second exists() call is for rgb_path → True (so we get an image to analyze)
    storage.exists.side_effect = [False, True]
    storage.download_bytes.return_value = b"fake-image-bytes"

    client = MagicMock()
    client.chat.completions.create.return_value = _make_openai_response("gpt-4-turbo")

    import nodes.analyze.logic as logic_mod
    logic_mod.pg_mark_analysis_running = MagicMock()
    logic_mod.pg_mark_analysis_done = MagicMock()
    logic_mod.pg_mark_analysis_failed = MagicMock()

    analyze_one_task("photo1", "00042", storage, client, model="gpt-4-turbo")

    create_kwargs = client.chat.completions.create.call_args[1]
    assert create_kwargs["model"] == "gpt-4-turbo"


def test_analyze_one_task_falls_back_to_env_model(monkeypatch):
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4o")
    storage = MagicMock()
    # First exists() call is for result_path (idempotency check) → False
    # Second exists() call is for rgb_path → True (so we get an image to analyze)
    storage.exists.side_effect = [False, True]
    storage.download_bytes.return_value = b"fake-image"

    client = MagicMock()
    client.chat.completions.create.return_value = _make_openai_response("gpt-4o")

    import nodes.analyze.logic as logic_mod
    logic_mod.pg_mark_analysis_running = MagicMock()
    logic_mod.pg_mark_analysis_done = MagicMock()
    logic_mod.pg_mark_analysis_failed = MagicMock()

    analyze_one_task("photo1", "00042", storage, client, model=None)

    create_kwargs = client.chat.completions.create.call_args[1]
    assert create_kwargs["model"] == "gpt-4o"


def test_analyze_one_task_skips_existing_result_without_openai_call():
    storage = MagicMock()
    storage.exists.return_value = True

    client = MagicMock()
    result_path = "analysis/mastcamz/sol=00042/photo1/analysis-1/result.json"

    import nodes.analyze.logic as logic_mod
    logic_mod.pg_mark_analysis_running = MagicMock()
    logic_mod.pg_mark_analysis_done = MagicMock()
    logic_mod.pg_mark_analysis_failed = MagicMock()

    result = analyze_one_task(
        "photo1",
        "00042",
        storage,
        client,
        model="gpt-4o",
        result_path=result_path,
    )

    assert result["status"] == "skip"
    assert result["result_path"] == result_path
    client.chat.completions.create.assert_not_called()
    logic_mod.pg_mark_analysis_running.assert_not_called()
    logic_mod.pg_mark_analysis_done.assert_called_once_with("photo1", result_path)


def test_analyze_one_task_retries_openai_after_transient_failure():
    storage = MagicMock()
    storage.exists.side_effect = [False, True]
    storage.download_bytes.return_value = b"fake-image"

    client = MagicMock()
    client.chat.completions.create.side_effect = [
        TimeoutError("temporary openai timeout"),
        _make_openai_response("gpt-4o"),
    ]

    import nodes.analyze.logic as logic_mod
    logic_mod.pg_mark_analysis_running = MagicMock()
    logic_mod.pg_mark_analysis_done = MagicMock()
    logic_mod.pg_mark_analysis_failed = MagicMock()

    result = analyze_one_task("photo1", "00042", storage, client, model="gpt-4o")

    assert result["status"] == "ok"
    assert result["result_path"] == "analysis/mastcamz/sol=00042/photo1/result.json"
    assert client.chat.completions.create.call_count == 2
    logic_mod.pg_mark_analysis_done.assert_called_once_with(
        "photo1",
        "analysis/mastcamz/sol=00042/photo1/result.json",
    )


def test_analyze_one_task_does_not_retry_non_json_model_output():
    class FakeMessage:
        content = "plain text without a JSON object"

    class FakeChoice:
        message = FakeMessage()

    class FakeResponse:
        choices = [FakeChoice()]
        usage = None
        model = "gpt-4o"

    class FakeCompletions:
        def __init__(self):
            self.calls = 0

        def create(self, **_kwargs):
            self.calls += 1
            return FakeResponse()

    class FakeChat:
        def __init__(self):
            self.completions = FakeCompletions()

    class FakeClient:
        def __init__(self):
            self.chat = FakeChat()

    storage = MagicMock()
    storage.exists.side_effect = [False, True]
    storage.download_bytes.side_effect = [
        b"fake-image",
        FileNotFoundError("metadata missing"),
        FileNotFoundError("array missing"),
    ]

    import nodes.analyze.logic as logic_mod
    logic_mod.pg_mark_analysis_running = MagicMock()
    logic_mod.pg_mark_analysis_done = MagicMock()
    logic_mod.pg_mark_analysis_failed = MagicMock()

    client = FakeClient()

    result = analyze_one_task("photo1", "00042", storage, client, model="gpt-4o")

    assert result["status"] == "error"
    assert client.chat.completions.calls == 1
    logic_mod.pg_mark_analysis_done.assert_not_called()
    logic_mod.pg_mark_analysis_failed.assert_called_once_with("photo1", "NonRetryableError")


def test_analyze_one_task_retries_image_download_after_transient_failure():
    storage = MagicMock()
    storage.exists.side_effect = [False, True]
    storage.download_bytes.side_effect = [
        TimeoutError("storage timeout"),
        b"fake-image",
        FileNotFoundError("metadata missing"),
        FileNotFoundError("array missing"),
    ]

    client = MagicMock()
    client.chat.completions.create.return_value = _make_openai_response("gpt-4o")

    import nodes.analyze.logic as logic_mod
    logic_mod.pg_mark_analysis_running = MagicMock()
    logic_mod.pg_mark_analysis_done = MagicMock()
    logic_mod.pg_mark_analysis_failed = MagicMock()

    result = analyze_one_task("photo1", "00042", storage, client, model="gpt-4o")

    assert result["status"] == "ok"
    assert storage.download_bytes.call_count == 4


def test_analyze_one_task_recovers_after_result_upload_fault(monkeypatch, capsys):
    import nodes.analyze.logic as logic

    class Registry:
        def __init__(self):
            self.calls = 0
            self.seen = []

        def should_fail(self, stage, job_id, lid=None):
            self.seen.append((stage, job_id, lid))
            if stage == "analyze_result_upload" and self.calls == 0:
                self.calls += 1
                return {
                    "fault_id": "f-result-upload",
                    "stage": stage,
                    "job_id": job_id,
                    "lid": lid,
                }
            return None

    class Storage:
        def __init__(self):
            self.uploads = 0

        def exists(self, path):
            return path.endswith("rgb.jpg")

        def download_bytes(self, path):
            if path.endswith("rgb.jpg"):
                return b"jpeg"
            return b"{}"

        def upload_bytes(self, *_args):
            self.uploads += 1
            return True

    registry = Registry()
    storage = Storage()
    monkeypatch.setattr(logic, "get_eval_fault_registry", lambda: registry, raising=False)
    monkeypatch.setattr(logic, "_call_openai", lambda *_args, **_kwargs: {"geological_features": "ok"})
    monkeypatch.setattr(logic, "pg_mark_analysis_running", lambda *_args: None)
    monkeypatch.setattr(logic, "pg_mark_analysis_done", lambda *_args: None)
    monkeypatch.setattr(logic, "pg_mark_analysis_failed", lambda *_args: None)

    result = logic.analyze_one_task("photo-1", "00001", storage, object())

    assert result["status"] == "ok"
    assert storage.uploads == 1
    assert ("analyze_result_upload", "", "photo-1") in registry.seen
    assert "EVAL_FAULT injected" in capsys.readouterr().out


def test_analyze_one_task_recovers_after_image_download_fault(monkeypatch, capsys):
    import nodes.analyze.logic as logic

    class Registry:
        def __init__(self):
            self.calls = 0
            self.seen = []

        def should_fail(self, stage, job_id, lid=None):
            self.seen.append((stage, job_id, lid))
            if stage == "analyze_image_download" and self.calls == 0:
                self.calls += 1
                return {
                    "fault_id": "f-image-download",
                    "stage": stage,
                    "job_id": job_id,
                    "lid": lid,
                }
            return None

    storage = MagicMock()
    storage.exists.side_effect = [False, True]
    storage.download_bytes.side_effect = [
        b"fake-image",
        FileNotFoundError("metadata missing"),
        FileNotFoundError("array missing"),
    ]

    registry = Registry()
    monkeypatch.setattr(logic, "get_eval_fault_registry", lambda: registry, raising=False)
    monkeypatch.setattr(logic, "pg_mark_analysis_running", MagicMock())
    monkeypatch.setattr(logic, "pg_mark_analysis_done", MagicMock())
    monkeypatch.setattr(logic, "pg_mark_analysis_failed", MagicMock())

    client = MagicMock()
    client.chat.completions.create.return_value = _make_openai_response("gpt-4o")

    result = logic.analyze_one_task("photo1", "00042", storage, client, model="gpt-4o")

    assert result["status"] == "ok"
    assert storage.download_bytes.call_count == 3
    assert ("analyze_image_download", "", "photo1") in registry.seen
    assert "EVAL_FAULT injected" in capsys.readouterr().out


def test_analyze_one_task_recovers_after_openai_fault(monkeypatch, capsys):
    import nodes.analyze.logic as logic

    class Registry:
        def __init__(self):
            self.calls = 0
            self.seen = []

        def should_fail(self, stage, job_id, lid=None):
            self.seen.append((stage, job_id, lid))
            if stage == "analyze_openai_call" and self.calls == 0:
                self.calls += 1
                return {
                    "fault_id": "f-openai",
                    "stage": stage,
                    "job_id": job_id,
                    "lid": lid,
                }
            return None

    storage = MagicMock()
    storage.exists.side_effect = [False, True]
    storage.download_bytes.side_effect = [
        b"fake-image",
        FileNotFoundError("metadata missing"),
        FileNotFoundError("array missing"),
    ]

    registry = Registry()
    monkeypatch.setattr(logic, "get_eval_fault_registry", lambda: registry, raising=False)
    monkeypatch.setattr(logic, "pg_mark_analysis_running", MagicMock())
    monkeypatch.setattr(logic, "pg_mark_analysis_done", MagicMock())
    monkeypatch.setattr(logic, "pg_mark_analysis_failed", MagicMock())

    client = MagicMock()
    client.chat.completions.create.return_value = _make_openai_response("gpt-4o")

    result = logic.analyze_one_task("photo1", "00042", storage, client, model="gpt-4o")

    assert result["status"] == "ok"
    assert client.chat.completions.create.call_count == 1
    assert ("analyze_openai_call", "", "photo1") in registry.seen
    assert "EVAL_FAULT injected" in capsys.readouterr().out
