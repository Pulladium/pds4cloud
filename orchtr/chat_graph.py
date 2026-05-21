import base64
import os

import requests
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

from nodes.qdrant.nodes import lid_to_point_id
from nodes.qdrant.qdrant_client import COLLECTION_NAME, get_qdrant_client

_SYSTEM_PROMPT = (
    "You are a Mars mission scientist analyzing Mastcam-Z imagery from the Perseverance rover. "
    "You have tools to retrieve project images and analyze them visually. "
    "Always start by calling get_project_images to see what's available. "
    "Provide scientific, evidence-based answers grounded in the actual image data and metadata."
)

DEFAULT_ANALYSIS_PROMPT = (
    "You are a Mars mission scientist. Examine all images in this project using their thumbnails "
    "and scientific metadata. Provide a mission briefing: key geological findings, spectral "
    "observations, anomalies detected, cross-image patterns, and recommended follow-up observations."
)


def build_agent(project_lids: list[str], captured: dict):
    """Return a compiled ReAct agent with project LIDs baked into tools via closure."""

    @tool
    def get_project_images() -> list[dict]:
        """Retrieve all Mars images in this project with their PDS4 scientific metadata and thumbnail URLs."""
        if not project_lids:
            return []
        client = get_qdrant_client()
        point_ids = [lid_to_point_id(lid) for lid in project_lids]
        points = client.retrieve(
            collection_name=COLLECTION_NAME,
            ids=point_ids,
            with_payload=True,
        )
        return [
            {
                "lid": p.payload.get("lid"),
                "photo_id": p.payload.get("photo_id"),
                "sol": p.payload.get("sol"),
                "thumb_url": p.payload.get("thumb_url"),
                "pds_meta": {
                    k: v
                    for k, v in p.payload.items()
                    if k not in ("lid", "photo_id", "sol", "thumb_url")
                },
            }
            for p in points
        ]

    @tool
    def analyze_image(lid: str, thumb_url: str) -> str:
        """Analyze a specific Mars image using GPT-4o vision. Returns a scientific description of what is visible."""
        resp = requests.get(thumb_url, timeout=30)
        resp.raise_for_status()
        img_b64 = base64.b64encode(resp.content).decode()

        from openai import OpenAI
        oa = OpenAI()
        completion = oa.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o"),
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                f"You are analyzing a Mars 2020 Mastcam-Z image (LID: {lid}). "
                                "Describe the visible geological features, terrain characteristics, "
                                "rock types, and any scientifically notable observations."
                            ),
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{img_b64}",
                                "detail": "high",
                            },
                        },
                    ],
                }
            ],
            max_tokens=1000,
        )
        return completion.choices[0].message.content

    @tool
    def find_similar_images(query_text: str, limit: int = 5) -> list[dict]:
        """Search the Mars image database for images matching a text description. Returns ranked similar images."""
        from nodes.qdrant.clip_client import embed_text
        vector = embed_text(query_text)
        client = get_qdrant_client()
        response = client.query_points(
            collection_name=COLLECTION_NAME,
            query=vector,
            limit=limit,
            with_payload=True,
        )
        results = [
            {
                "lid": h.payload.get("lid"),
                "photo_id": h.payload.get("photo_id"),
                "sol": h.payload.get("sol"),
                "thumb_url": h.payload.get("thumb_url"),
                "score": round(h.score, 4),
            }
            for h in response.points
        ]
        captured["image_results"] = results
        return results

    llm = ChatOpenAI(model=os.getenv("OPENAI_MODEL", "gpt-4o"))
    return create_react_agent(llm, tools=[get_project_images, analyze_image, find_similar_images])


def run_chat(project_lids: list[str], history: list[dict]) -> tuple[str, list[dict]]:
    """
    Run the ReAct agent.

    Args:
        project_lids: LID strings for all images in the project.
        history: All messages including the latest user message.
                 Each dict: {"role": "user"|"assistant", "content": str}

    Returns:
        Tuple of (assistant reply text, list of image results from find_similar_images tool).
    """
    captured = {"image_results": []}

    lc_messages = [SystemMessage(content=_SYSTEM_PROMPT)]
    for m in history:
        if m["role"] == "user":
            lc_messages.append(HumanMessage(content=m["content"]))
        elif m["role"] == "assistant":
            lc_messages.append(AIMessage(content=m["content"]))

    agent = build_agent(project_lids, captured)
    result = agent.invoke({"messages": lc_messages})

    reply_text = "No response generated."
    for msg in reversed(result["messages"]):
        if isinstance(msg, AIMessage) and msg.content:
            reply_text = msg.content
            break

    return reply_text, captured["image_results"]
