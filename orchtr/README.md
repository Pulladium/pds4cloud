# Minimal LangGraph Example — Mars2020 Mastcam-Z Pipeline (Graph API)

 runnable LangGraph project using the **Graph API**, structured around a real Mars2020 Mastcam-Z ingestion workflow.



## How to run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Graph structure

```
START → ingest → prepare → finalize → END
```

## Shared state (`main.py`)

```python
class State(TypedDict):
    from_n:    int        # 1-based start index in product stream
    to_n:      int        # 1-based end index (inclusive)
    status:    str        # current pipeline status
    processed: int        # number of products processed by ingest
    summary:   str        # human-readable summary (set by prepare)
    messages:  list[str]  # trace log across all nodes
```

## Storage architecture

The ingestion node uses a **storage adapter** abstraction (`nodes/ingest/storage/base.py`) so that `core.py` is decoupled from any specific backend.

### Adapter interface

```python
class StorageAdapter(Protocol):
    def exists(self, path: str) -> bool: ...
    def upload_bytes(self, path: str, data: bytes, content_type: str) -> bool: ...
```

### Backend selection

Set `STORAGE_BACKEND` before running:

| Value | Backend |
|-------|---------|
| `gcs` (default) | Google Cloud Storage |
| `minio` | MinIO |

### Running with GCS

```bash
export STORAGE_BACKEND=gcs
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json
export GCS_PROJECT_ID=your-project-id   # optional, has default
export GCS_BUCKET=mars2020              # optional, has default
python main.py
```

### Running with MinIO

```bash
export STORAGE_BACKEND=minio
export MINIO_ENDPOINT=localhost:9000
export MINIO_ACCESS_KEY=minioadmin
export MINIO_SECRET_KEY=minioadmin
export MINIO_BUCKET=mars2020            # optional, default: mars2020
export MINIO_SECURE=false               # optional, default: false
python main.py
```

## Demo mode

When the configured storage backend is unreachable (missing credentials, network issue, etc.), `core.py` catches the error and falls back to demo mode — it prints what it *would* upload without making any real network calls.

## Standalone CLI

```bash
python -m nodes.ingest.cli --from 1 --to 5
```

## Expected output (demo mode, `from_n=1`, `to_n=3`)

```
STORAGE_BACKEND= gcs
RANGE: from=1 to=3
Storage: unavailable (ModuleNotFoundError), running in demo mode

[1] sol=00011 | urn:nasa:pds:mars2020_mast_z:data_raw::demo_0001 [DEMO]
  Would upload: mastcamz/sol=00011/...
...

=== FINAL STATE ===
  status:    complete
  processed: 3
  summary:   Mastcam-Z ingest complete: 3 products processed from index 1 to 3.
  messages:
    - ingest: processed=3 sols=3 range=[1,3]
    - prepare: summary built (66 chars)
    - finalize: pipeline complete
```
