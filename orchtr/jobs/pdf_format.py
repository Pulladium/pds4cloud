_ANALYSIS_FIELDS = [
    ("geological_features", "Geological Features"),
    ("spectral_interpretation", "Spectral Interpretation"),
    ("scientific_significance", "Scientific Significance"),
    ("data_quality", "Data Quality"),
    ("hypotheses", "Hypotheses"),
    ("recommended_followup", "Recommended Follow-up"),
]

_METADATA_FIELDS = {"metadata_loaded", "metadata_summary", "array_summary"}
_TOKEN_FIELDS = {"prompt_tokens", "completion_tokens", "model", "cost_usd"}


def _section_text(value) -> str:
    if isinstance(value, list):
        return "\n".join(f"- {item}" for item in value if item)
    if value is None:
        return ""
    return str(value).strip()


def analysis_sections(analysis: dict) -> list[tuple[str, str]]:
    sections = []
    for key, title in _ANALYSIS_FIELDS:
        text = _section_text(analysis.get(key))
        if text:
            sections.append((title, text))

    if sections:
        return sections

    description = _section_text(analysis.get("description"))
    if description:
        return [("Analysis", description)]

    fallback_items = [
        (key, value)
        for key, value in analysis.items()
        if key not in _METADATA_FIELDS
        and key not in _TOKEN_FIELDS
        and _section_text(value)
    ]
    return [(key.replace("_", " ").title(), _section_text(value)) for key, value in fallback_items]
