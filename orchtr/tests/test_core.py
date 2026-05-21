"""
Unit tests for nodes/transform/core.py — run_transform.

Patches DB and storage so no real infrastructure needed.
"""

import pytest
import numpy as np
from unittest.mock import patch, MagicMock

from nodes.transform.core import run_transform


BASE_STATE = {
    "transform_limit": None,
    "messages": [],
}


class FakeStorage:
    def __init__(self):
        self._store: dict[str, bytes] = {}

    def exists(self, path):
        return path in self._store

    def upload_bytes(self, path, data, content_type):
        if path in self._store:
            return False
        self._store[path] = data
        return True

    def download_bytes(self, path):
        return self._store.get(path, b"fake")

    def list_objects(self, prefix):
        for path in self._store:
            if path.startswith(prefix):
                yield path


FAKE_2D = np.random.rand(32, 32).astype(float)


class TestRunTransform:

    def test_storage_unavailable_returns_skipped(self):
        """When storage fails to initialise, node should skip gracefully."""
        with patch("nodes.transform.core.get_storage_adapter",
                   side_effect=Exception("no storage")):
            result = run_transform(BASE_STATE)

        assert result["transformed"] == 0
        assert result["status"] == "transform_skipped"

    def test_nothing_pending_from_postgres(self):
        """PG returns empty list → transform_done with zero count."""
        storage = FakeStorage()
        with patch("nodes.transform.core.pg_fetch_pending", return_value=[]):
            with patch("nodes.transform.core.get_storage_adapter", return_value=storage):
                result = run_transform(BASE_STATE)

        assert result["transformed"] == 0
        assert result["status"] == "transform_done"

    def test_nothing_pending_from_scan(self):
        """No PG, no .IMG in storage → transform_done with zero count."""
        storage = FakeStorage()
        storage._store["mastcamz/sol=00001/metadata.json"] = b"{}"  # non-IMG file

        with patch("nodes.transform.core.pg_fetch_pending",
                   side_effect=RuntimeError("Postgres not configured")):
            with patch("nodes.transform.core.get_storage_adapter", return_value=storage):
                result = run_transform(BASE_STATE)

        assert result["transformed"] == 0
        assert result["status"] == "transform_done"

    def test_transform_limit_passed_to_db(self):
        """transform_limit in state is forwarded to pg_fetch_pending."""
        state = {**BASE_STATE, "transform_limit": 5}
        storage = FakeStorage()
        mock_fetch = MagicMock(return_value=[])
        with patch("nodes.transform.core.pg_fetch_pending", mock_fetch):
            with patch("nodes.transform.core.get_storage_adapter", return_value=storage):
                run_transform(state)

        mock_fetch.assert_called_once_with(5)

    @patch("nodes.transform.logic.db.pg_mark_done", lambda *a, **k: None)
    @patch("nodes.transform.logic.db.pg_mark_failed", lambda *a, **k: None)
    @patch("nodes.transform.logic.read_imgdata", return_value=FAKE_2D)
    def test_successful_transform_counted(self, mock_read):
        storage = FakeStorage()
        src = "mastcamz/sol=00001/A.IMG"
        storage._store[src] = b"fake"
        rows = [("pid1", 1, src)]

        with patch("nodes.transform.core.pg_fetch_pending", return_value=rows):
            with patch("nodes.transform.core.get_storage_adapter", return_value=storage):
                result = run_transform(BASE_STATE)

        assert result["transformed"] == 1
        assert result["status"] == "transform_done"
        assert any("transformed=1" in m for m in result["messages"])

    @patch("nodes.transform.logic.db.pg_mark_done", lambda *a, **k: None)
    @patch("nodes.transform.logic.db.pg_mark_failed", lambda *a, **k: None)
    @patch("nodes.transform.logic.read_imgdata", return_value=FAKE_2D)
    def test_messages_appended_not_replaced(self, mock_read):
        storage = FakeStorage()
        src = "mastcamz/sol=00001/A.IMG"
        storage._store[src] = b"fake"
        state = {**BASE_STATE, "messages": ["prior message"]}
        rows = [("pid1", 1, src)]

        with patch("nodes.transform.core.pg_fetch_pending", return_value=rows):
            with patch("nodes.transform.core.get_storage_adapter", return_value=storage):
                result = run_transform(state)

        assert "prior message" in result["messages"]
        assert len(result["messages"]) == 2

    # --- scan fallback tests ---

    @patch("nodes.transform.logic.db.pg_mark_done", lambda *a, **k: None)
    @patch("nodes.transform.logic.db.pg_mark_failed", lambda *a, **k: None)
    @patch("nodes.transform.logic.read_imgdata", return_value=FAKE_2D)
    def test_scan_fallback_finds_img_files(self, mock_read):
        """No PG → scan MinIO → .IMG found → transform runs."""
        storage = FakeStorage()
        storage._store["mastcamz/sol=00001/A.IMG"] = b"fake"

        with patch("nodes.transform.core.pg_fetch_pending",
                   side_effect=RuntimeError("Postgres not configured")):
            with patch("nodes.transform.core.get_storage_adapter", return_value=storage):
                result = run_transform(BASE_STATE)

        assert result["transformed"] == 1
        assert result["status"] == "transform_done"

    @patch("nodes.transform.logic.db.pg_mark_done", lambda *a, **k: None)
    @patch("nodes.transform.logic.db.pg_mark_failed", lambda *a, **k: None)
    @patch("nodes.transform.logic.read_imgdata", return_value=FAKE_2D)
    def test_scan_fallback_skips_non_img(self, mock_read):
        """Scan ignores JSON and other non-.IMG objects."""
        storage = FakeStorage()
        storage._store["mastcamz/sol=00001/meta.json"] = b"{}"
        storage._store["mastcamz/sol=00001/label.lbl"] = b"LABEL"

        with patch("nodes.transform.core.pg_fetch_pending",
                   side_effect=RuntimeError("Postgres not configured")):
            with patch("nodes.transform.core.get_storage_adapter", return_value=storage):
                result = run_transform(BASE_STATE)

        assert result["transformed"] == 0

    @patch("nodes.transform.logic.db.pg_mark_done", lambda *a, **k: None)
    @patch("nodes.transform.logic.db.pg_mark_failed", lambda *a, **k: None)
    @patch("nodes.transform.logic.read_imgdata", return_value=FAKE_2D)
    def test_scan_fallback_respects_limit(self, mock_read):
        """transform_limit=1 with multiple .IMG files → only 1 processed."""
        storage = FakeStorage()
        for i in range(3):
            storage._store[f"mastcamz/sol=00001/FILE{i:02d}.IMG"] = b"fake"

        state = {**BASE_STATE, "transform_limit": 1}

        with patch("nodes.transform.core.pg_fetch_pending",
                   side_effect=RuntimeError("Postgres not configured")):
            with patch("nodes.transform.core.get_storage_adapter", return_value=storage):
                result = run_transform(state)

        assert result["transformed"] == 1

    @patch("nodes.transform.logic.db.pg_mark_done", lambda *a, **k: None)
    @patch("nodes.transform.logic.db.pg_mark_failed", lambda *a, **k: None)
    @patch("nodes.transform.logic.read_imgdata", return_value=FAKE_2D)
    def test_scan_source_logged_in_message(self, mock_read):
        """Message includes 'source=scan' when fallback is used."""
        storage = FakeStorage()
        storage._store["mastcamz/sol=00001/A.IMG"] = b"fake"

        with patch("nodes.transform.core.pg_fetch_pending",
                   side_effect=RuntimeError("Postgres not configured")):
            with patch("nodes.transform.core.get_storage_adapter", return_value=storage):
                result = run_transform(BASE_STATE)

        assert any("source=scan" in m for m in result["messages"])
