import os

from fastapi import APIRouter, HTTPException
from openai import OpenAI

router = APIRouter(prefix="/api/models", tags=["models"])


@router.get("")
def list_models():
    api_key = os.environ.get("OPENAI_API_KEY")
    try:
        client = OpenAI(api_key=api_key)
        response = client.models.list()
        gpt_ids = sorted(m.id for m in response.data if m.id.startswith("gpt-"))
        return gpt_ids
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"OpenAI unavailable: {exc}")
