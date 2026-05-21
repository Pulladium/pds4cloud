import os

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PayloadSchemaType, VectorParams

COLLECTION_NAME = "mars_images"
VECTOR_SIZE = 512

_client: QdrantClient | None = None


def get_qdrant_client() -> QdrantClient:
    global _client
    if _client is None:
        _client = QdrantClient(
            url=os.environ["QDRANT_URL"],
            api_key=os.environ["QDRANT_API_KEY"],
        )
    return _client


def ensure_collection() -> None:
    client = get_qdrant_client()
    existing_names = [c.name for c in client.get_collections().collections]
    if COLLECTION_NAME not in existing_names:
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
        )
        client.create_payload_index(COLLECTION_NAME, "sol", PayloadSchemaType.KEYWORD)
        client.create_payload_index(COLLECTION_NAME, "photo_id", PayloadSchemaType.KEYWORD)
