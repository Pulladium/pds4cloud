"""
graph_single.py — Single-product on-demand LangGraph pipeline.

Triggered by the frontend when a user selects a NASA PDS product.

State flow:
    product_lid + optional hints
        → ingest_one   (download .IMG → MinIO temp)
        → transform_one (pdr decode → gray.jpg + rgb.jpg, delete raw)
        → analyze_one  (OpenAI vision → result.json)
"""

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from typing_extensions import TypedDict
from langgraph.graph import StateGraph, START, END
from langsmith import tracing_context

from nodes.ingest.one   import run_ingest_one
from nodes.transform.one import run_transform_one
from nodes.analyze.one  import run_analyze_one


class SingleState(TypedDict):
    # ── input ─────────────────────────────────────────────────────────────
    product_lid:  str           # NASA PDS LID (only required field)
    job_id:       str | None
    project_id:   str | None
    user_id:      str | None

    # ── filled by pipeline ────────────────────────────────────────────────
    photo_id:     str           # img filename stem
    sol:          str           # zero-padded sol, e.g. "00045"
    img_path:     str | None    # MinIO path of raw .IMG (temp, deleted after transform)
    gray_path:    str | None    # MinIO path of gray.jpg
    rgb_path:     str | None    # MinIO path of rgb.jpg (or None)
    metadata_path: str | None   # MinIO path of full PDS registry properties
    array_summary_path: str | None
    array_summary: dict
    result_path:  str | None    # MinIO path of analysis JSON
    analysis_id:  str | None
    analysis:     dict          # OpenAI analysis result dict

    # ── token / cost fields (filled by analyze_one) ───────────────────────
    prompt_tokens:     int
    completion_tokens: int
    model:             str | None
    cost_usd:          float

    # ── meta ──────────────────────────────────────────────────────────────
    status:       str
    messages:     list[str]
    error:        str | None


def build_single_graph():
    builder = StateGraph(SingleState)
    builder.add_node("ingest_one",        run_ingest_one)
    builder.add_node("transform_one",     run_transform_one)
    builder.add_node("analyze_one",       run_analyze_one)

    builder.add_edge(START,               "ingest_one")
    builder.add_edge("ingest_one",        "transform_one")
    builder.add_edge("transform_one",     "analyze_one")
    builder.add_edge("analyze_one",       END)

    return builder.compile()


single_graph = build_single_graph()


def initial_state(
    lid: str,
    model: str | None = None,
    job_id: str | None = None,
    project_id: str | None = None,
    user_id: str | None = None,
) -> SingleState:
    return {
        "product_lid": lid,
        "job_id":      job_id,
        "project_id":  project_id,
        "user_id":     user_id,
        "photo_id":    "",
        "sol":         "",
        "img_path":    None,
        "gray_path":   None,
        "rgb_path":    None,
        "metadata_path": None,
        "array_summary_path": None,
        "array_summary": {},
        "result_path": None,
        "analysis_id": None,
        "analysis":    {},
        "prompt_tokens":     0,
        "completion_tokens": 0,
        "model":             model,
        "cost_usd":          None,
        "status":      "",
        "messages":    [],
        "error":       None,
    }


def process_product(
    lid: str,
    model: str | None = None,
    job_id: str | None = None,
    project_id: str | None = None,
    user_id: str | None = None,
) -> dict:
    """
    Run the full pipeline for one NASA PDS product by LID.

    Example:
        result = process_product("urn:nasa:pds:mars2020_mastcamz_ops_raw:data_raw:zl0_0001_...")
        print(result["analysis"])
    """
    initial = initial_state(
        lid,
        model=model,
        job_id=job_id,
        project_id=project_id,
        user_id=user_id,
    )
    if not job_id:
        return single_graph.invoke(initial)

    with tracing_context(
        tags=[f"job:{job_id}"],
        metadata={
            "job_id": job_id,
            "project_id": project_id,
            "user_id": user_id,
            "lid": lid,
        },
    ):
        return single_graph.invoke(initial)
