"""
nodes/ingest/one.py — Ingest a single NASA PDS product by LID.

Accepts either:
  • lid + sol + label_url + img_filename  (fast path — no PDS API call needed)
  • lid only                              (fetches metadata from PDS registry)

Downloads the raw .IMG into MinIO as a temporary file.
The transform node will delete it after processing.
"""

import json
import os
import time
from urllib.parse import urlparse

import requests
from utils.retry import retry_call
from utils.eval_faults import get_eval_fault_registry

SOL_KEY      = "mars2020:Observation_Information.mars2020:sol_number"
FILENAME_KEY = "pds:File.pds:file_name"
BASE_URL     = "https://pds-imaging.jpl.nasa.gov/data/mars2020/"


def _maybe_raise_eval_fault(stage: str, lid: str) -> None:
    fault = get_eval_fault_registry().should_fail(stage, "", lid)
    if fault:
        print(f"EVAL_FAULT injected {json.dumps(fault, sort_keys=True)}", flush=True)
        raise TimeoutError(f"eval fault injected: {fault['fault_id']}")


def _img_url_from_label(label_url: str) -> str:
    img_label = label_url.strip().replace(".xml", ".IMG")
    if urlparse(img_label).scheme in ("http", "https"):
        return img_label
    return BASE_URL + img_label.lstrip("/")


def _resolve_full_lid(api, short_id: str) -> str:
    """Resolve a short file-based ID to a full urn:nasa:pds:... LID via filename search."""
    results = api.product_list(
        q=f'pds:File.pds:file_name like "{short_id}%"',
        fields="lid",
        limit=1,
    )
    data = getattr(results, "data", None) or []
    if not data:
        raise ValueError(f"No PDS product found for short ID: {short_id!r}")
    props = getattr(data[0], "properties", {}) or {}
    full_lid = (props.get("lid") or [None])[0]
    if not full_lid:
        raise ValueError(f"PDS returned product but no lid field for: {short_id!r}")
    return full_lid


def _pds_lookup(lid: str) -> tuple[str, str, str, dict]:
    """
    Fetch (sol_str, label_url, img_filename) from the PDS search API by LID.
    Accepts either a full urn:nasa:pds:... LID or a short filename-based ID.
    """
    from pds.peppi import PDSRegistryClient
    from pds.api_client import AllProductsApi

    client = PDSRegistryClient()
    api    = AllProductsApi(client.api_client)

    if not lid.startswith("urn:"):
        lid = _resolve_full_lid(api, lid)

    item  = api.select_by_lidvid_latest(identifier=lid)
    props = getattr(item, "properties", {}) or {}

    sol_val = (props.get(SOL_KEY) or [None])[0]
    sol_str = str(sol_val).zfill(5) if sol_val else "00000"

    filename  = (props.get(FILENAME_KEY) or [None])[0]
    label_url = getattr(getattr(item, "metadata", None), "label_url", "") or ""

    return sol_str, label_url, filename, props


def _download(url: str, tries: int = 5) -> bytes:
    last = None
    for attempt in range(1, tries + 1):
        try:
            with requests.get(url, stream=True, timeout=(10, 300)) as r:
                r.raise_for_status()
                chunks = []
                for chunk in r.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        chunks.append(chunk)
                return b"".join(chunks)
        except Exception as e:
            last = e
            sleep = 2.0 * (2 ** (attempt - 1))
            print(f"  WARN: download attempt {attempt}/{tries}: {e} — retry in {sleep:.0f}s", flush=True)
            time.sleep(sleep)
    raise last


def run_ingest_one(state: dict) -> dict:
    from .storage import get_storage_adapter

    lid      = state["product_lid"]
    messages = list(state.get("messages", []))

    # --- resolve metadata from PDS ---
    print(f"ingest_one: fetching metadata for {lid} ...", flush=True)
    try:
        sol, label_url, img_filename, raw_props = retry_call(
            lambda: (_maybe_raise_eval_fault("pds_lookup", lid), _pds_lookup(lid))[1],
            attempts=3,
            delays=(0.0, 2.0),
            sleep_fn=time.sleep,
            on_retry=lambda attempt, exc, delay: print(
                f"  WARN: PDS lookup attempt {attempt}/3: {exc}"
                + (f" — retry in {delay:.0f}s" if delay > 0 else ""),
                flush=True,
            ),
        )
    except Exception as e:
        msg = f"ingest_one: PDS lookup failed — {e}"
        print(msg, flush=True)
        return {"status": "error_lookup", "error": str(e), "messages": messages + [msg]}

    if not img_filename:
        msg = f"ingest_one: product has no IMG file ({lid})"
        print(msg, flush=True)
        return {"status": "error_no_img", "error": msg, "messages": messages + [msg]}

    sol_str  = str(sol).zfill(5) if str(sol).isdigit() else str(sol)
    photo_id = os.path.splitext(img_filename)[0]
    img_path = f"mastcamz/sol={sol_str}/{img_filename}"
    metadata_path = f"mastcamz/sol={sol_str}/{photo_id}_metadata.json"
    img_url  = _img_url_from_label(label_url)

    print(f"ingest_one: sol={sol_str} photo_id={photo_id}", flush=True)

    storage = get_storage_adapter()

    # --- idempotency: if gray.jpg already exists, skip download ---
    gray_path = f"transformed/mastcamz/sol={sol_str}/{photo_id}/gray.jpg"
    if storage.exists(gray_path):
        print(f"  SKIP: already transformed", flush=True)
        return {
            "photo_id":     photo_id,
            "sol":          sol_str,
            "img_path":     img_path,
            "metadata_path": metadata_path,
            "status":       "already_transformed",
            "messages":     messages + [f"ingest_one: skip (already transformed) photo_id={photo_id}"],
        }

    # --- download & upload IMG (skip if already in MinIO) ---
    if storage.exists(img_path):
        print(f"  IMG already in storage: {img_path}", flush=True)
    else:
        print(f"  Downloading: {img_url}", flush=True)
        try:
            img_bytes = retry_call(
                lambda: (_maybe_raise_eval_fault("pds_img_download", lid), _download(img_url))[1],
                attempts=3,
                delays=(0.0, 2.0),
                sleep_fn=time.sleep,
            )
            print(f"  Downloaded: {len(img_bytes):,} bytes", flush=True)
        except Exception as e:
            msg = f"ingest_one: download failed — {e}"
            print(msg, flush=True)
            return {"status": "error_download", "error": str(e), "messages": messages + [msg]}

        retry_call(
            lambda: (
                _maybe_raise_eval_fault("ingest_img_upload", lid),
                storage.upload_bytes(img_path, img_bytes, "application/octet-stream"),
            )[1],
            attempts=3,
            delays=(0.0, 2.0),
            sleep_fn=time.sleep,
        )
        print(f"  Uploaded: {img_path}", flush=True)

    metadata_payload = {
        "lid": lid,
        "sol": sol_str,
        "label_url": label_url,
        "img_filename": img_filename,
        "properties": raw_props,
    }
    retry_call(
        lambda: (
            _maybe_raise_eval_fault("ingest_metadata_upload", lid),
            storage.upload_bytes(
                metadata_path,
                json.dumps(metadata_payload, ensure_ascii=False, indent=2).encode("utf-8"),
                "application/json",
            ),
        )[1],
        attempts=3,
        delays=(0.0, 2.0),
        sleep_fn=time.sleep,
    )
    print(f"  Uploaded metadata: {metadata_path}", flush=True)

    return {
        "photo_id":  photo_id,
        "sol":       sol_str,
        "img_path":  img_path,
        "metadata_path": metadata_path,
        "status":    "ingested",
        "messages":  messages + [f"ingest_one: ok photo_id={photo_id} sol={sol_str}"],
    }
