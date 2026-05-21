from typing_extensions import TypedDict
from langgraph.graph import END, START, StateGraph

from nodes.qdrant.nodes import embed_clip, fetch_image, upsert_qdrant


class QdrantState(TypedDict):
    lid:       str
    thumb_url: str
    photo_id:  str
    sol:       str
    pds_meta:  dict
    img_bytes: bytes
    vector:    list
    status:    str
    error:     str | None
    point_id:  str | None
    messages:  list[str]


_builder = StateGraph(QdrantState)
_builder.add_node("fetch_image",   fetch_image)
_builder.add_node("embed_clip",    embed_clip)
_builder.add_node("upsert_qdrant", upsert_qdrant)

_builder.add_edge(START,           "fetch_image")
_builder.add_edge("fetch_image",   "embed_clip")
_builder.add_edge("embed_clip",    "upsert_qdrant")
_builder.add_edge("upsert_qdrant", END)

qdrant_graph = _builder.compile()


def index_product(lid: str, thumb_url: str) -> dict:
    initial: QdrantState = {
        "lid":       lid,
        "thumb_url": thumb_url,
        "photo_id":  "",
        "sol":       "",
        "pds_meta":  {},
        "img_bytes": b"",
        "vector":    [],
        "status":    "",
        "error":     None,
        "point_id":  None,
        "messages":  [],
    }
    return qdrant_graph.invoke(initial)


def index_product_bytes(
    lid: str,
    img_bytes: bytes,
    photo_id: str,
    sol: str,
    thumb_url: str,
    pds_meta: dict | None = None,
) -> dict:
    state: QdrantState = {
        "lid":       lid,
        "thumb_url": thumb_url,
        "photo_id":  photo_id,
        "sol":       sol,
        "pds_meta":  pds_meta or {},
        "img_bytes": img_bytes,
        "vector":    [],
        "status":    "fetched",
        "error":     None,
        "point_id":  None,
        "messages":  ["fetch_image: using generated preview bytes"],
    }
    embedded = {**state, **embed_clip(state)}
    return {**embedded, **upsert_qdrant(embedded)}
