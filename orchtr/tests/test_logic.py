"""
Unit tests for nodes/transform/logic.py — process_one_task.

Uses a FakeStorage (in-memory) and monkeypatches read_imgdata / pg helpers
so no real storage, pdr, or Postgres is needed.
"""

import io
import numpy as np
import pytest
from PIL import Image
from unittest.mock import patch, MagicMock

from nodes.transform.logic import process_one_task


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class FakeStorage:
    """In-memory storage adapter."""

    def __init__(self, existing=None):
        self._store: dict[str, bytes] = {}
        for path in (existing or []):
            self._store[path] = b""

    def exists(self, path: str) -> bool:
        return path in self._store

    def upload_bytes(self, path: str, data: bytes, content_type: str) -> bool:
        if path in self._store:
            return False
        self._store[path] = data
        return True

    def download_bytes(self, path: str) -> bytes:
        if path not in self._store:
            raise FileNotFoundError(path)
        return self._store[path]


SOURCE = "mastcamz/sol=00045/ZL0_0045_0670322004_123ECM_N0031416ZCAM08006_1100LUJ.IMG"
GRAY   = "transformed/mastcamz/sol=00045/ZL0_0045_0670322004_123ECM_N0031416ZCAM08006_1100LUJ/gray.jpg"
RGB    = "transformed/mastcamz/sol=00045/ZL0_0045_0670322004_123ECM_N0031416ZCAM08006_1100LUJ/rgb.jpg"

FAKE_2D   = np.random.randint(0, 1000, (32, 32), dtype=np.uint16).astype(float)
FAKE_3D_3 = np.random.randint(0, 1000, (3, 32, 32), dtype=np.uint16).astype(float)
FAKE_3D_14 = np.random.randint(0, 1000, (14, 32, 32), dtype=np.uint16).astype(float)


def _no_pg(*args, **kwargs):
    pass


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@patch("nodes.transform.logic.db.pg_mark_done", _no_pg)
@patch("nodes.transform.logic.db.pg_mark_failed", _no_pg)
class TestProcessOneTask:

    # --- skip path ---

    def test_skip_when_gray_exists(self):
        """gray.jpg alone is enough to mark as already processed."""
        storage = FakeStorage(existing=[GRAY])
        result = process_one_task("pid1", 45, SOURCE, storage)
        assert result["status"] == "skip_all"
        assert result["photo_id"] == "pid1"

    def test_skip_when_gray_and_rgb_exist(self):
        storage = FakeStorage(existing=[GRAY, RGB])
        result = process_one_task("pid1", 45, SOURCE, storage)
        assert result["status"] == "skip_all"

    # --- download error ---

    def test_download_error(self):
        storage = FakeStorage()  # source not in store
        result = process_one_task("pid1", 45, SOURCE, storage)
        assert result["status"] == "error_download"
        assert "err" in result

    # --- read error (bad bytes) ---

    def test_read_error_bad_bytes(self):
        storage = FakeStorage()
        storage._store[SOURCE] = b"not an IMG file"
        result = process_one_task("pid1", 45, SOURCE, storage)
        assert result["status"] == "error_read"

    # --- 2D grayscale success ---

    @patch("nodes.transform.logic.read_imgdata", return_value=FAKE_2D)
    def test_2d_grayscale(self, mock_read):
        storage = FakeStorage()
        storage._store[SOURCE] = b"fake"
        result = process_one_task("pid1", 45, SOURCE, storage)
        assert result["status"] == "ok"
        assert result["gray"] in ("uploaded", "exists")
        assert result["rgb"] == "none"
        assert storage.exists(GRAY)
        assert not storage.exists(RGB)

    # --- 3D 3-band → gray + rgb ---

    @patch("nodes.transform.logic.read_imgdata", return_value=FAKE_3D_3)
    def test_3d_3band(self, mock_read):
        storage = FakeStorage()
        storage._store[SOURCE] = b"fake"
        result = process_one_task("pid1", 45, SOURCE, storage)
        assert result["status"] == "ok"
        assert result["gray"] in ("uploaded", "exists")
        assert result["rgb"] in ("uploaded", "exists")
        assert storage.exists(GRAY)
        assert storage.exists(RGB)

    # --- 3D 14-band → gray + rgb ---

    @patch("nodes.transform.logic.read_imgdata", return_value=FAKE_3D_14)
    def test_3d_14band(self, mock_read):
        storage = FakeStorage()
        storage._store[SOURCE] = b"fake"
        result = process_one_task("pid1", 45, SOURCE, storage)
        assert result["status"] == "ok"
        assert result["rgb"] in ("uploaded", "exists")
        assert storage.exists(RGB)

    # --- unsupported ndim ---

    @patch("nodes.transform.logic.read_imgdata", return_value=np.zeros((2, 3, 4, 5)))
    def test_unsupported_ndim(self, mock_read):
        storage = FakeStorage()
        storage._store[SOURCE] = b"fake"
        result = process_one_task("pid1", 45, SOURCE, storage)
        assert result["status"] == "unsupported_ndim"

    # --- idempotency: re-running uploads nothing new ---

    @patch("nodes.transform.logic.read_imgdata", return_value=FAKE_2D)
    def test_idempotent_on_rerun(self, mock_read):
        storage = FakeStorage()
        storage._store[SOURCE] = b"fake"
        r1 = process_one_task("pid1", 45, SOURCE, storage)
        assert r1["status"] == "ok"

        # Second run: gray.jpg already there → skip
        r2 = process_one_task("pid1", 45, SOURCE, storage)
        assert r2["status"] == "skip_all"

    # --- output path construction ---

    @patch("nodes.transform.logic.read_imgdata", return_value=FAKE_2D)
    def test_output_paths(self, mock_read):
        storage = FakeStorage()
        storage._store[SOURCE] = b"fake"
        process_one_task("pid1", 45, SOURCE, storage)
        assert storage.exists(GRAY)
        assert not storage.exists(GRAY.replace("gray.jpg", "rgb.none"))

    # --- gray output is valid JPEG ---

    @patch("nodes.transform.logic.read_imgdata", return_value=FAKE_2D)
    def test_gray_is_valid_jpeg(self, mock_read):
        storage = FakeStorage()
        storage._store[SOURCE] = b"fake"
        process_one_task("pid1", 45, SOURCE, storage)
        jpeg_bytes = storage._store[GRAY]
        img = Image.open(io.BytesIO(jpeg_bytes))
        assert img.format == "JPEG"

    # --- rgb output is valid JPEG ---

    @patch("nodes.transform.logic.read_imgdata", return_value=FAKE_3D_3)
    def test_rgb_is_valid_jpeg(self, mock_read):
        storage = FakeStorage()
        storage._store[SOURCE] = b"fake"
        process_one_task("pid1", 45, SOURCE, storage)
        jpeg_bytes = storage._store[RGB]
        img = Image.open(io.BytesIO(jpeg_bytes))
        assert img.format == "JPEG"
        assert img.mode == "RGB"


# ---------------------------------------------------------------------------
# Tests for nodes/analyze/logic.py — _call_openai token usage
# ---------------------------------------------------------------------------

def _mock_openai_response(content: str, prompt_tokens=100, completion_tokens=50):
    usage = MagicMock()
    usage.prompt_tokens = prompt_tokens
    usage.completion_tokens = completion_tokens

    choice = MagicMock()
    choice.message.content = content

    resp = MagicMock()
    resp.choices = [choice]
    resp.usage = usage
    resp.model = "gpt-4o"
    return resp


def test_call_openai_returns_token_fields():
    fake_analysis = '{"geological_features": "rocks"}'
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = _mock_openai_response(
        fake_analysis, prompt_tokens=200, completion_tokens=80
    )

    from nodes.analyze.logic import _call_openai
    result = _call_openai(b"fakeimg", {"sol": "00001"}, mock_client, model="gpt-4o")

    assert result["prompt_tokens"] == 200
    assert result["completion_tokens"] == 80
    assert result["model"] == "gpt-4o"
    assert result["cost_usd"] is None


def test_call_openai_does_not_calculate_local_cost():
    fake_analysis = '{"geological_features": "dust"}'
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = _mock_openai_response(
        fake_analysis, prompt_tokens=1_000_000, completion_tokens=1_000_000
    )

    from nodes.analyze.logic import _call_openai
    result = _call_openai(b"fakeimg", {}, mock_client, model="gpt-4o")

    assert result["cost_usd"] is None


def test_call_openai_usage_none_defaults_to_zero():
    fake_analysis = '{"geological_features": "sand"}'
    mock_client = MagicMock()
    resp = _mock_openai_response(fake_analysis)
    resp.usage = None
    mock_client.chat.completions.create.return_value = resp

    from nodes.analyze.logic import _call_openai
    result = _call_openai(b"fakeimg", {}, mock_client, model="gpt-4o")

    assert result["prompt_tokens"] == 0
    assert result["completion_tokens"] == 0
    assert result["cost_usd"] is None
