import os

from fpdf import FPDF
from fpdf.enums import XPos, YPos

from nodes.ingest.storage import get_storage_adapter
from jobs.pdf_format import analysis_sections


_UNICODE_FONTS = [
    (
        "NotoSans",
        os.environ.get("NOTO_SANS_FONT_PATH", "/usr/share/fonts/noto/NotoSans-Regular.ttf"),
        os.environ.get("NOTO_SANS_BOLD_FONT_PATH", "/usr/share/fonts/noto/NotoSans-Bold.ttf"),
    ),
    (
        "NotoSans",
        os.environ.get("NOTO_SANS_ALT_FONT_PATH", "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf"),
        os.environ.get("NOTO_SANS_ALT_BOLD_FONT_PATH", "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf"),
    ),
    (
        "DejaVu",
        os.environ.get("DEJAVU_FONT_PATH", "/usr/share/fonts/TTF/DejaVuSans.ttf"),
        os.environ.get("DEJAVU_BOLD_FONT_PATH", "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf"),
    ),
    (
        "DejaVu",
        os.environ.get("DEJAVU_ALT_FONT_PATH", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        os.environ.get("DEJAVU_ALT_BOLD_FONT_PATH", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ),
]


def _resolve_unicode_font() -> tuple[str, str, str | None]:
    for family, regular_path, bold_path in _UNICODE_FONTS:
        if os.path.exists(regular_path):
            return family, regular_path, bold_path if os.path.exists(bold_path) else None

    raise RuntimeError(
        "No Unicode PDF font found. Install Noto Sans or DejaVu Sans, "
        "or set NOTO_SANS_FONT_PATH/DEJAVU_FONT_PATH."
    )


def _make_pdf() -> FPDF:
    family, regular_path, bold_path = _resolve_unicode_font()
    pdf = FPDF()
    pdf.add_font(family, style="", fname=regular_path)
    if bold_path:
        pdf.add_font(family, style="B", fname=bold_path)
    pdf._unicode_font = family
    return pdf


def _font(pdf: FPDF, style: str = "", size: int = 10) -> None:
    pdf.set_font(pdf._unicode_font, style, size)


def generate_pdf_bytes(job_id: str, project_id: str, results: list[dict]) -> bytes:
    pdf = _make_pdf()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    _font(pdf, "B", 20)
    pdf.cell(0, 12, "Mars 2020 Mastcam-Z Analysis Report", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="C")
    _font(pdf, "", 10)
    pdf.cell(0, 8, f"Job: {job_id}  |  Project: {project_id}", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="C")
    pdf.ln(6)

    failed = [r for r in results if r.get("status", "").startswith("error") or not r.get("analysis")]
    succeeded = [r for r in results if r not in failed]

    if failed:
        _font(pdf, "B", 11)
        pdf.set_text_color(200, 0, 0)
        pdf.cell(0, 8, f"Note: {len(failed)} image(s) could not be processed:", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        _font(pdf, "", 9)
        for r in failed:
            pdf.cell(0, 6, f"  - {r.get('lid', '<unknown>')}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_text_color(0, 0, 0)
        pdf.ln(4)

    for i, r in enumerate(succeeded, 1):
        _font(pdf, "B", 13)
        pdf.cell(0, 10, f"Image {i}: {r.get('photo_id', r.get('lid', '<unknown>').split(':')[-1])}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        _font(pdf, "", 9)
        pdf.cell(0, 6, f"LID:  {r.get('lid', '<unknown>')}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        if r.get("sol"):
            pdf.cell(0, 6, f"Sol:  {r['sol']}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        analysis = r.get("analysis") or {}
        metadata_summary = r.get("metadata_summary") or analysis.get("metadata_summary") or {}
        array_summary = r.get("array_summary") or analysis.get("array_summary") or {}
        metadata_loaded = bool(r.get("metadata_loaded") or analysis.get("metadata_loaded"))
        if metadata_summary or array_summary:
            _font(pdf, "B", 10)
            pdf.cell(0, 7, "Input context:", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            _font(pdf, "", 9)
            pdf.multi_cell(
                0,
                5,
                (
                    f"Full raw metadata loaded: {'yes' if metadata_loaded else 'no'}\n"
                    f"Image type: {metadata_summary.get('image_type', 'unknown')}\n"
                    f"Processing: {metadata_summary.get('processing', 'unknown')}\n"
                    f"PDS4 bands: {array_summary.get('bands', 'unknown')}\n"
                    f"Array shape: {array_summary.get('shape', 'unknown')}\n"
                    f"Selected RGB bands: {array_summary.get('selected_rgb_bands', 'unknown')}"
                ),
            )

        pdf.ln(2)
        for title, text in analysis_sections(analysis):
            _font(pdf, "B", 10)
            pdf.cell(0, 7, f"{title}:", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            _font(pdf, "", 10)
            pdf.multi_cell(0, 6, text[:2000])
            pdf.ln(1)

        features = analysis.get("features") or []
        if features:
            _font(pdf, "B", 10)
            pdf.cell(0, 7, "Features detected:", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            _font(pdf, "", 10)
            pdf.multi_cell(0, 6, ", ".join(str(f) for f in features))

        pdf.ln(6)
        if i < len(succeeded):
            pdf.line(pdf.get_x(), pdf.get_y(), pdf.get_x() + 190, pdf.get_y())
            pdf.ln(4)

    return bytes(pdf.output())


def upload_pdf(job_id: str, pdf_bytes: bytes) -> str:
    storage = get_storage_adapter()
    path = f"reports/{job_id}/report.pdf"
    storage.upload_bytes(path, pdf_bytes, "application/pdf")
    return storage.presigned_url(path, expires=86400)
