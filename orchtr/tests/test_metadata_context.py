import io
import json
from unittest.mock import MagicMock, patch

import numpy as np


def test_ingest_writes_full_metadata_json():
    from nodes.ingest.one import run_ingest_one

    storage = MagicMock()
    storage.exists.return_value = False
    uploaded = {}
    storage.upload_bytes.side_effect = lambda path, data, _ct: uploaded.setdefault(path, data) or True

    props = {
        "mars2020:Observation_Information.mars2020:sol_number": ["1224"],
        "pds:File.pds:file_name": ["ZRF_1224_TEST.IMG"],
        "pds:Axis_Array.pds:axis_name": ["Band", "Line", "Sample"],
    }

    with (
        patch("nodes.ingest.one._pds_lookup", return_value=("01224", "http://example/ZRF_1224_TEST.xml", "ZRF_1224_TEST.IMG", props)),
        patch("nodes.ingest.one._download", return_value=b"img"),
        patch("nodes.ingest.storage.get_storage_adapter", return_value=storage),
    ):
        result = run_ingest_one({"product_lid": "urn:test", "messages": []})

    assert result["metadata_path"] == "mastcamz/sol=01224/ZRF_1224_TEST_metadata.json"
    payload = json.loads(uploaded[result["metadata_path"]].decode("utf-8"))
    assert payload["properties"]["pds:Axis_Array.pds:axis_name"] == ["Band", "Line", "Sample"]


def test_transform_writes_array_summary_json():
    from nodes.transform.logic import process_one_task

    arr = np.zeros((3, 4, 5), dtype=np.int16)
    buf = io.BytesIO()
    np.save(buf, arr)

    storage = MagicMock()
    stored = {"mastcamz/sol=01224/ZRF_TEST.IMG": buf.getvalue()}
    storage.exists.side_effect = lambda path: path in stored
    storage.download_bytes.side_effect = lambda path: stored[path]
    storage.upload_bytes.side_effect = lambda path, data, _ct: stored.setdefault(path, data) or True

    with patch("nodes.transform.db.pg_mark_done"):
        result = process_one_task("ZRF_TEST", 1224, "mastcamz/sol=01224/ZRF_TEST.IMG", storage)

    summary_path = result["array_summary_path"]
    summary = json.loads(stored[summary_path].decode("utf-8"))
    assert summary["ndim"] == 3
    assert summary["shape"] == [3, 4, 5]
    assert summary["bands"] == 3
    assert summary["selected_rgb_bands"] == [1, 2, 3]


def test_analyze_prompt_includes_metadata_and_array_summary():
    from nodes.analyze.logic import _analysis_context_text

    text = _analysis_context_text(
        {
            "properties": {
                "mars2020:Observation_Information.mars2020:sol_number": [1224],
                "img_surface:Instrument_Information.img_surface:image_type": ["THUMBNAIL"],
                "pds:Primary_Result_Summary.pds:processing_level": ["Calibrated"],
                "test:raw_metadata_field": "full metadata value",
            },
        },
        {
            "shape": [3, 144, 192],
            "dtype": "int16",
            "bands": 3,
            "selected_rgb_bands": [1, 2, 3],
        },
        metadata_loaded=True,
    )

    assert "Full raw metadata loaded: yes" in text
    assert "Image Type: THUMBNAIL" in text
    assert "Sol:        1224" in text
    assert "Array shape: [3, 144, 192]" in text
    assert "Selected RGB bands: [1, 2, 3]" in text
    assert "FULL RAW PDS METADATA JSON:" in text
    assert '"test:raw_metadata_field": "full metadata value"' in text
