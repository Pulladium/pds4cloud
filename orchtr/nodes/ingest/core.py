"""
nodes/ingest/core.py — Mars2020 Mastcam-Z ingestion.

Real mode : fetches products from NASA PDS via pds.peppi, downloads .IMG files.
Demo mode : falls back to synthetic 32x32 numpy arrays when pds.peppi is absent.
"""

import json
import os
import time
from collections import Counter

import requests

from .db import ensure_photo_row_if_missing
from .demo import build_demo_products, make_demo_img_bytes
from .storage import get_storage_adapter

SOL_KEY      = "mars2020:Observation_Information.mars2020:sol_number"
FILENAME_KEY = "pds:File.pds:file_name"
BASE_URL     = "https://pds-imaging.jpl.nasa.gov/data/mars2020/"


def _get_sol(product) -> str:
    if hasattr(product, "properties") and SOL_KEY in product.properties:
        return str(product.properties[SOL_KEY][0]).zfill(5)
    parts = [p for p in product.id.split("_") if p.isdigit() and len(p) == 4]
    return (parts[0] if parts else "unknown").zfill(5)


def _has_img(product) -> bool:
    return (
        hasattr(product, "metadata")
        and getattr(product.metadata, "label_url", None)
        and hasattr(product, "properties")
        and FILENAME_KEY in product.properties
        and product.properties[FILENAME_KEY]
    )


def _with_retries(fn, *, tries=5, base_sleep=2.0, what="op"):
    last = None
    for attempt in range(1, tries + 1):
        try:
            return fn()
        except Exception as e:
            last = e
            sleep = base_sleep * (2 ** (attempt - 1))
            print(f"  WARN: {what} attempt {attempt}/{tries}: {e}", flush=True)
            time.sleep(sleep)
    raise last


def _download_img(url: str) -> bytes:
    def _get():
        with requests.get(url, stream=True, timeout=(10, 300)) as r:
            r.raise_for_status()
            chunks = []
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    chunks.append(chunk)
            return b"".join(chunks)
    return _with_retries(_get, what=f"download {url}")


def _ingest_real(storage, from_n: int, to_n: int) -> dict:
    from pds.peppi import PDSRegistryClient, Products
    from datetime import datetime

    client       = PDSRegistryClient()
    landing_date = datetime.fromisoformat("2021-02-18")
    products_q   = (
        Products(client)
        .has_target("urn:nasa:pds:context:target:planet.mars")
        .has_investigation("urn:nasa:pds:context:investigation:mission.mars2020")
        .has_instrument("urn:nasa:pds:context:instrument:mars2020.mastcamz")
        .after(landing_date)
        .observationals()
    )

    sol_counts    = Counter()
    processed     = 0
    uploaded_json = 0
    uploaded_img  = 0
    skipped_all   = 0
    no_img        = 0
    seen          = 0

    for product in products_q:
        seen += 1
        if seen < from_n:
            continue
        if seen > to_n:
            break
        processed += 1

        sol     = _get_sol(product)
        safe_id = product.id.replace(":", "_")
        prefix  = f"mastcamz/sol={sol}/"
        sol_counts[sol] += 1

        json_name    = prefix + f"{safe_id}_metadata.json"
        img_name     = None
        img_url      = None
        img_filename = None
        photo_id     = safe_id

        if _has_img(product):
            label_url    = product.metadata.label_url.lstrip("/")
            img_filename = product.properties[FILENAME_KEY][0]
            img_url      = BASE_URL + label_url.replace(".xml", ".IMG")
            img_name     = prefix + img_filename
            photo_id     = os.path.splitext(img_filename)[0]

        source_path   = img_name
        metadata_path = json_name

        print(f"\n[{seen}] sol={sol} | {product.id}", flush=True)

        json_exists = storage.exists(json_name)
        img_exists  = storage.exists(img_name) if img_name else True

        if json_exists and img_exists:
            skipped_all += 1
            print("  SKIP: already in storage")
            ensure_photo_row_if_missing(
                photo_id=photo_id, sol=sol,
                source_path=source_path, metadata_path=metadata_path,
            )
            continue

        # --- JSON ---
        if not json_exists:
            metadata = product.properties if hasattr(product, "properties") else {}
            ok = storage.upload_bytes(
                json_name,
                json.dumps(metadata, indent=2).encode(),
                "application/json",
            )
            if ok:
                uploaded_json += 1
                print(f"  JSON uploaded: {json_name}")
        else:
            print(f"  JSON exists: {json_name}")

        # --- IMG ---
        if img_name is None:
            no_img += 1
            print("  No IMG fields — metadata only")
            ensure_photo_row_if_missing(
                photo_id=photo_id, sol=sol,
                source_path=source_path, metadata_path=metadata_path,
            )
            continue

        if not img_exists:
            try:
                img_bytes = _download_img(img_url)
                print(f"  IMG downloaded: {len(img_bytes):,} bytes from {img_url}")
                ok = storage.upload_bytes(img_name, img_bytes, "application/octet-stream")
                if ok:
                    uploaded_img += 1
                    print(f"  IMG uploaded: {img_name}")
                else:
                    print(f"  IMG exists (race): {img_name}")
            except Exception as e:
                print(f"  IMG FAILED: {e}")
                continue
        else:
            print(f"  IMG exists: {img_name}")

        ensure_photo_row_if_missing(
            photo_id=photo_id, sol=sol,
            source_path=source_path, metadata_path=metadata_path,
        )

    return {
        "processed": processed, "sol_counts": sol_counts,
        "uploaded_json": uploaded_json, "uploaded_img": uploaded_img,
        "skipped_all": skipped_all, "no_img": no_img, "mode": "real",
    }


def _ingest_demo(storage, from_n: int, to_n: int) -> dict:
    products      = build_demo_products(from_n, to_n)
    sol_counts    = Counter()
    processed     = 0
    uploaded_json = 0
    uploaded_img  = 0
    skipped_all   = 0

    for product in products:
        processed += 1
        sol          = product["sol"]
        safe_id      = product["id"].replace(":", "_")
        prefix       = f"mastcamz/sol={sol}/"
        sol_counts[sol] += 1

        json_name    = prefix + f"{safe_id}_metadata.json"
        img_filename = product["filename"]
        img_name     = prefix + img_filename
        photo_id     = os.path.splitext(img_filename)[0]
        source_path  = img_name
        metadata_path = json_name

        json_exists = storage.exists(json_name)
        img_exists  = storage.exists(img_name)

        if json_exists and img_exists:
            skipped_all += 1
            ensure_photo_row_if_missing(
                photo_id=photo_id, sol=sol,
                source_path=source_path, metadata_path=metadata_path,
            )
            continue

        if not json_exists:
            storage.upload_bytes(
                json_name,
                json.dumps(product["metadata"], indent=2).encode(),
                "application/json",
            )
            uploaded_json += 1

        if not img_exists:
            product_index = product.get("metadata", {}).get("product_index", 0)
            storage.upload_bytes(
                img_name, make_demo_img_bytes(product_index), "application/octet-stream",
            )
            uploaded_img += 1

        ensure_photo_row_if_missing(
            photo_id=photo_id, sol=sol,
            source_path=source_path, metadata_path=metadata_path,
        )

    return {
        "processed": processed, "sol_counts": sol_counts,
        "uploaded_json": uploaded_json, "uploaded_img": uploaded_img,
        "skipped_all": skipped_all, "no_img": 0, "mode": "demo",
    }


def run_ingest(state) -> dict:
    from_n = state["from_n"]
    to_n   = state["to_n"]

    print(f"STORAGE_BACKEND= {os.environ.get('STORAGE_BACKEND', 'gcs')}", flush=True)
    print(f"RANGE: from={from_n} to={to_n}", flush=True)

    try:
        storage = get_storage_adapter()
    except Exception as e:
        msg = f"ingest: storage unavailable ({type(e).__name__}), skipped"
        print(msg)
        return {
            "processed": 0,
            "status":    "ingest_skipped",
            "messages":  list(state.get("messages", [])) + [msg],
        }

    try:
        import pds.peppi  # noqa: F401
        stats = _ingest_real(storage, from_n, to_n)
    except ImportError:
        print("pds.peppi not installed — using demo data", flush=True)
        stats = _ingest_demo(storage, from_n, to_n)

    processed  = stats["processed"]
    sol_counts = stats["sol_counts"]
    mode       = stats["mode"]

    print(f"\n=== INGEST SUMMARY (mode={mode}) ===")
    print(f"  Processed:     {processed}")
    print(f"  Unique SOLs:   {len(sol_counts)}")
    print(f"  JSON uploaded: {stats['uploaded_json']}")
    print(f"  IMG  uploaded: {stats['uploaded_img']}")
    print(f"  Skipped:       {stats['skipped_all']}")
    if stats.get("no_img"):
        print(f"  No-IMG:        {stats['no_img']}")

    return {
        "processed": processed,
        "status":    "ingested",
        "messages":  list(state.get("messages", [])) + [
            f"ingest: processed={processed} sols={len(sol_counts)} "
            f"mode={mode} range=[{from_n},{to_n}]"
        ],
    }
