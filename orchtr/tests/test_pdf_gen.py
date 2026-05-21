import io
from unittest.mock import MagicMock, patch


def _make_results():
    return [
        {
            "lid": "urn:nasa:pds:mars2020:img001",
            "thumb_url": "https://example.com/thumb1.jpg",
            "sol": "00042",
            "photo_id": "ZL0_0042_001",
            "analysis": {
                "description": "Rocky terrain with basaltic outcrops.",
                "features": ["rocks", "dust"],
            },
            "status": "analyze_ok",
        },
        {
            "lid": "urn:nasa:pds:mars2020:img002",
            "thumb_url": "https://example.com/thumb2.jpg",
            "sol": "00042",
            "photo_id": "ZL0_0042_002",
            "analysis": {"description": "Sand dunes visible.", "features": ["sand"]},
            "status": "analyze_ok",
        },
    ]


def test_generate_pdf_returns_bytes():
    from jobs.pdf_gen import generate_pdf_bytes
    pdf_bytes = generate_pdf_bytes("job-abc", "proj-xyz", _make_results())
    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 100
    assert pdf_bytes[:4] == b"%PDF"


def test_generate_pdf_single_image():
    from jobs.pdf_gen import generate_pdf_bytes
    results = _make_results()[:1]
    pdf_bytes = generate_pdf_bytes("job-abc", "proj-xyz", results)
    assert pdf_bytes[:4] == b"%PDF"


def test_analysis_sections_format_mastcamz_json_without_raw_dict():
    from jobs.pdf_format import analysis_sections

    analysis = {
        "geological_features": "Layered sedimentary rocks.",
        "spectral_interpretation": "RGB bands highlight iron-rich minerals.",
        "scientific_significance": "Useful for habitability analysis.",
        "data_quality": "Well calibrated.",
        "hypotheses": ["Ancient water altered the rocks.", "Volcanic material is present."],
        "recommended_followup": "Compare with previous sols.",
        "metadata_loaded": True,
        "metadata_summary": {"location": "Jezero Crater"},
        "array_summary": {"shape": [3, 1200, 1648]},
    }

    sections = analysis_sections(analysis)

    assert sections == [
        ("Geological Features", "Layered sedimentary rocks."),
        ("Spectral Interpretation", "RGB bands highlight iron-rich minerals."),
        ("Scientific Significance", "Useful for habitability analysis."),
        ("Data Quality", "Well calibrated."),
        ("Hypotheses", "- Ancient water altered the rocks.\n- Volcanic material is present."),
        ("Recommended Follow-up", "Compare with previous sols."),
    ]
    rendered = "\n".join(f"{title}\n{text}" for title, text in sections)
    assert "{'geological_features'" not in rendered


def test_generate_pdf_handles_unicode_punctuation_with_unicode_font():
    from jobs.pdf_gen import _make_pdf, generate_pdf_bytes

    results = [
        {
            "lid": "urn:nasa:pds:mars2020:unicode",
            "sol": "00042",
            "photo_id": "ZL0_0042_unicode",
            "analysis": {
                "description": "Perseverance’s Mastcam-Z shows fine-grained sediment—likely water-altered…",
                "features": ["dust’s edge"],
            },
            "status": "analyze_ok",
        }
    ]

    pdf = _make_pdf()

    assert pdf._unicode_font in {"NotoSans", "DejaVu"}
    assert pdf._unicode_font != "Helvetica"
    assert generate_pdf_bytes("job-abc", "proj-xyz", results)[:4] == b"%PDF"


def test_pdf_font_resolver_uses_noto_before_dejavu(monkeypatch):
    import jobs.pdf_gen as pdf_gen

    def exists(path):
        return path.endswith("/NotoSans-Regular.ttf") or path.endswith("/NotoSans-Bold.ttf")

    monkeypatch.setattr(pdf_gen.os.path, "exists", exists)

    assert pdf_gen._resolve_unicode_font() == (
        "NotoSans",
        "/usr/share/fonts/noto/NotoSans-Regular.ttf",
        "/usr/share/fonts/noto/NotoSans-Bold.ttf",
    )


def test_upload_pdf_returns_minio_path():
    from jobs.pdf_gen import generate_pdf_bytes, upload_pdf

    mock_storage = MagicMock()
    mock_storage.presigned_url.return_value = "http://minio/reports/job-abc/report.pdf"

    with patch("jobs.pdf_gen.get_storage_adapter", return_value=mock_storage):
        pdf_bytes = generate_pdf_bytes("job-abc", "proj-xyz", _make_results())
        url = upload_pdf("job-abc", pdf_bytes)

    mock_storage.upload_bytes.assert_called_once()
    call_args = mock_storage.upload_bytes.call_args
    assert call_args[0][0] == "reports/job-abc/report.pdf"
    assert call_args[0][2] == "application/pdf"
    assert url == "http://minio/reports/job-abc/report.pdf"
