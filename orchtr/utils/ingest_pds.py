"""
utils/ingest_pds.py — Real NASA PDS ingest into MinIO (or GCS).

Fetches Mastcam-Z observational products via pds.peppi, downloads the
raw .IMG files from the PDS imaging server, and uploads them together
with their JSON metadata to the configured storage backend.

Usage:
    .venv/bin/python utils/ingest_pds.py --from 1 --to 50
    .venv/bin/python utils/ingest_pds.py --from 1 --to 10 --dry-run
"""

import argparse
import os
import sys
import time
import tempfile
from collections import Counter
from datetime import datetime

import requests

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from nodes.ingest.storage import get_storage_adapter
from nodes.ingest.db import ensure_photo_row_if_missing

SOL_KEY      = "mars2020:Observation_Information.mars2020:sol_number"
FILENAME_KEY = "pds:File.pds:file_name"
BASE_URL     = "https://pds-imaging.jpl.nasa.gov/data/mars2020/"


def build_products(client):
    from pds.peppi import Products
    landing_date = datetime.fromisoformat("2021-02-18")
    return (
        Products(client)
        .has_target("urn:nasa:pds:context:target:planet.mars")
        .has_investigation("urn:nasa:pds:context:investigation:mission.mars2020")
        .has_instrument("urn:nasa:pds:context:instrument:mars2020.mastcamz")
        .after(landing_date)
        .observationals()
    )


def get_sol(product) -> str:
    if hasattr(product, "properties") and SOL_KEY in product.properties:
        return str(product.properties[SOL_KEY][0]).zfill(5)
    parts = [p for p in product.id.split("_") if p.isdigit() and len(p) == 4]
    return (parts[0] if parts else "unknown").zfill(5)


def has_img(product) -> bool:
    return (
        hasattr(product, "metadata")
        and getattr(product.metadata, "label_url", None)
        and hasattr(product, "properties")
        and FILENAME_KEY in product.properties
        and product.properties[FILENAME_KEY]
    )


def with_retries(fn, *, tries=6, base_sleep=2.0, what="op"):
    last = None
    for attempt in range(1, tries + 1):
        try:
            return fn()
        except Exception as e:
            last = e
            sleep = base_sleep * (2 ** (attempt - 1))
            print(f"  WARN: {what} failed (attempt {attempt}/{tries}): {e}")
            time.sleep(sleep)
    raise last


def download_img_bytes(url: str) -> bytes:
    def _get():
        with requests.get(url, stream=True, timeout=(10, 180)) as r:
            r.raise_for_status()
            buf = b""
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    buf += chunk
            return buf
    return with_retries(_get, what=f"IMG download {url}")


def main():
    parser = argparse.ArgumentParser(description="Ingest real NASA PDS Mastcam-Z products into MinIO")
    parser.add_argument("--from", dest="from_n", type=int, default=1,
                        help="1-based index in product stream to start from")
    parser.add_argument("--to", dest="to_n", type=int, default=None,
                        help="1-based index in product stream to stop at (inclusive)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would be uploaded without actually uploading")
    args = parser.parse_args()

    if args.from_n < 1:
        args.from_n = 1
    if args.to_n is not None and args.to_n < args.from_n:
        raise SystemExit(f"--to ({args.to_n}) must be >= --from ({args.from_n})")

    try:
        from pds.peppi import PDSRegistryClient
    except ImportError:
        print("ERROR: pds.peppi not installed. Run: pip install pds.peppi")
        sys.exit(1)

    storage = get_storage_adapter()
    print(f"Storage backend: {os.environ.get('STORAGE_BACKEND', 'gcs')}", flush=True)
    print(f"Range: from={args.from_n} to={args.to_n}", flush=True)
    if args.dry_run:
        print("DRY RUN — nothing will be uploaded", flush=True)

    client = PDSRegistryClient()
    products = build_products(client)

    sol_counts         = Counter()
    processed          = 0
    uploaded_json      = 0
    uploaded_img       = 0
    skipped_all        = 0
    skipped_json       = 0
    skipped_img        = 0
    no_img_fields      = 0

    seen = 0

    for product in products:
        seen += 1
        if seen < args.from_n:
            continue
        if args.to_n is not None and seen > args.to_n:
            break
        processed += 1

        sol      = get_sol(product)
        safe_id  = product.id.replace(":", "_")
        prefix   = f"mastcamz/sol={sol}/"
        sol_counts[sol] += 1

        json_name = prefix + f"{safe_id}_metadata.json"

        img_name     = None
        img_filename = None
        img_url      = None
        photo_id     = safe_id

        if has_img(product):
            label_url    = product.metadata.label_url.lstrip("/")
            img_filename = product.properties[FILENAME_KEY][0]
            img_url      = BASE_URL + label_url.replace(".xml", ".IMG")
            img_name     = prefix + img_filename
            photo_id     = os.path.splitext(img_filename)[0]

        source_path   = img_name
        metadata_path = json_name

        print(f"\n[{seen}] sol={sol} | {product.id}")

        json_exists = storage.exists(json_name)
        img_exists  = storage.exists(img_name) if img_name else True

        if json_exists and img_exists:
            skipped_all += 1
            print(f"  SKIP: both already in storage")
            ensure_photo_row_if_missing(
                photo_id=photo_id, sol=sol,
                source_path=source_path, metadata_path=metadata_path,
            )
            continue

        print(f"  exists? json={json_exists}, img={img_exists}")

        # --- JSON ---
        if not json_exists:
            metadata = product.properties if hasattr(product, "properties") else {}
            if not args.dry_run:
                import json
                ok = storage.upload_bytes(
                    json_name,
                    json.dumps(metadata, indent=2).encode(),
                    "application/json",
                )
                if ok:
                    uploaded_json += 1
                    print(f"  JSON uploaded: {json_name}")
                else:
                    skipped_json += 1
                    print(f"  JSON exists (race), skip: {json_name}")
            else:
                print(f"  [DRY] would upload JSON: {json_name}")
                uploaded_json += 1
        else:
            skipped_json += 1
            print(f"  JSON exists, skip: {json_name}")

        # --- IMG ---
        if img_name is None:
            no_img_fields += 1
            print(f"  No IMG fields in product, skipping IMG")
            ensure_photo_row_if_missing(
                photo_id=photo_id, sol=sol,
                source_path=source_path, metadata_path=metadata_path,
            )
            continue

        if img_exists:
            skipped_img += 1
            print(f"  IMG exists, skip: {img_name}")
        else:
            if args.dry_run:
                print(f"  [DRY] would download {img_url}")
                print(f"  [DRY] would upload IMG: {img_name}")
                uploaded_img += 1
            else:
                try:
                    img_bytes = download_img_bytes(img_url)
                    print(f"  IMG downloaded: {len(img_bytes):,} bytes from {img_url}")
                except Exception as e:
                    print(f"  IMG download FAILED: {e}")
                    continue

                ok = storage.upload_bytes(img_name, img_bytes, "application/octet-stream")
                if ok:
                    uploaded_img += 1
                    print(f"  IMG uploaded: {img_name}")
                else:
                    skipped_img += 1
                    print(f"  IMG exists (race), skip: {img_name}")

        ensure_photo_row_if_missing(
            photo_id=photo_id, sol=sol,
            source_path=source_path, metadata_path=metadata_path,
        )

    print("\n=== RUN SUMMARY ===")
    print(f"Range: from={args.from_n} to={args.to_n}")
    print(f"Seen in stream: {seen}")
    print(f"Processed (in range): {processed}")
    print(f"Unique SOLs: {len(sol_counts)}")
    print(f"SKIP all-exists: {skipped_all}")
    print(f"JSON uploaded: {uploaded_json}, skipped: {skipped_json}")
    print(f"IMG  uploaded: {uploaded_img}, skipped: {skipped_img}")
    print(f"No IMG fields: {no_img_fields}")
    print("\nPhotos per SOL (top 30):")
    for sol, cnt in sol_counts.most_common(30):
        print(f"  sol={sol}: {cnt}")


if __name__ == "__main__":
    main()
