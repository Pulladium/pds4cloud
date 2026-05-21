# Orchestrator

FastAPI and LangGraph service for the Mars 2020 Mastcam-Z processing pipeline. It resolves PDS products, downloads and transforms images, runs analysis, stores artifacts, serves project/search APIs, and participates in the Kafka job pipeline.

## Run locally

The normal project path is Docker Compose from the repository root:

```bash
docker compose --profile eval up -d --build
```

For local development inside this directory:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
.venv/bin/uvicorn server:app --host 0.0.0.0 --port 8000 --reload
```

## Main API

- `GET /health`
- `POST /api/process`
- project routes under `/api/projects`
- chat routes under `/api/chat`
- model and LangSmith helper routes
- Qdrant/vector-search routes

## Single-product graph

`graph_single.py` processes one product through the on-demand pipeline:

```text
START -> ingest_one -> transform_one -> analyze_one -> finalize -> END
```

The Kafka worker path in `messaging/image_worker.py` uses the same product-processing function.

## Storage

The ingestion code uses a storage adapter abstraction in `nodes/ingest/storage/`.

```python
class StorageAdapter(Protocol):
    def exists(self, path: str) -> bool: ...
    def upload_bytes(self, path: str, data: bytes, content_type: str) -> bool: ...
```

Set `STORAGE_BACKEND` before running:

| Value | Backend |
|-------|---------|
| `minio` | MinIO, used by the Compose deployment |
| `gcs` | Google Cloud Storage |

### MinIO

```bash
export STORAGE_BACKEND=minio
export MINIO_ENDPOINT=localhost:9000
export MINIO_ACCESS_KEY=minioadmin
export MINIO_SECRET_KEY=minioadmin
export MINIO_BUCKET=mars2020
export MINIO_SECURE=false
```

### GCS

```bash
export STORAGE_BACKEND=gcs
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json
export GCS_PROJECT_ID=your-project-id
export GCS_BUCKET=mars2020
```

## Standalone ingest CLI

```bash
python -m nodes.ingest.cli --from 1 --to 5
```

This CLI is useful for direct PDS ingest checks outside the full job pipeline.
