"""
nodes/transform/logic.py — process_one_task: download, transform, upload one photo.
"""

import io
import json
import os

import numpy as np
from PIL import Image

from nodes.ingest.storage.base import StorageAdapter
from utils.eval_faults import get_eval_fault_registry
from utils.retry import retry_call
from . import db
from .image_ops import normalize_2d, read_imgdata

SRC_PREFIX = "mastcamz/"
OUTPUT_PREFIX = "transformed/mastcamz/"


def _maybe_raise_eval_fault(stage: str, lid: str) -> None:
    fault = get_eval_fault_registry().should_fail(stage, "", lid)
    if fault:
        print(f"EVAL_FAULT injected {json.dumps(fault, sort_keys=True)}", flush=True)
        raise TimeoutError(f"eval fault injected: {fault['fault_id']}")


def process_one_task(
    photo_id: str,
    sol: int | None,
    source_path: str,
    storage: StorageAdapter,
) -> dict:
    """
    Download source_path from storage, transform to gray/rgb JPEGs, upload results.
    Returns a status dict.
    """
    # --- derive output paths ---
    rel = source_path[len(SRC_PREFIX):]          # sol=00045/XXX.IMG
    rel_parent = os.path.dirname(rel)            # sol=00045
    stem = os.path.splitext(os.path.basename(rel))[0]

    out_dir  = f"{OUTPUT_PREFIX}{rel_parent}/{stem}/"
    out_gray = out_dir + "gray.jpg"
    out_rgb  = out_dir + "rgb.jpg"

    # --- pre-check: gray.jpg exists → already processed, skip ---
    if storage.exists(out_gray):
        db.pg_mark_done(photo_id, out_gray, out_rgb if storage.exists(out_rgb) else None)
        print(f"  SKIP (already in storage) photo_id={photo_id}")
        return {"status": "skip_all", "photo_id": photo_id, "file": source_path}

    # --- download ---
    try:
        def download_source():
            _maybe_raise_eval_fault("transform_storage_download", photo_id)
            return storage.download_bytes(source_path)

        raw_bytes = retry_call(
            download_source,
            attempts=3,
            delays=(0.0, 2.0),
        )
    except Exception as e:
        db.pg_mark_failed(photo_id, f"download:{type(e).__name__}")
        return {"status": "error_download", "photo_id": photo_id, "file": source_path, "err": str(e)}

    # --- decode ---
    try:
        img_data = read_imgdata(raw_bytes)
    except Exception as e:
        db.pg_mark_failed(photo_id, f"read:{type(e).__name__}")
        return {"status": "error_read", "photo_id": photo_id, "file": source_path, "err": str(e)}

    # --- transform ---
    gray_img = None
    rgb_img  = None
    selected_rgb_bands = []

    if img_data.ndim == 2:
        gray_img = Image.fromarray(normalize_2d(img_data))

    elif img_data.ndim == 3:
        bands = img_data.shape[0]
        gray_img = Image.fromarray(normalize_2d(img_data[0]))

        if bands == 3:
            r = normalize_2d(img_data[0])
            g = normalize_2d(img_data[1])
            b = normalize_2d(img_data[2])
            rgb_img = Image.fromarray(np.stack([r, g, b], axis=-1))
            selected_rgb_bands = [1, 2, 3]
        elif bands >= 14:
            r = normalize_2d(img_data[0])
            g = normalize_2d(img_data[12])
            b = normalize_2d(img_data[13])
            rgb_img = Image.fromarray(np.stack([r, g, b], axis=-1))
            selected_rgb_bands = [1, 13, 14]
    else:
        db.pg_mark_failed(photo_id, "unsupported_ndim")
        return {"status": "unsupported_ndim", "photo_id": photo_id, "file": source_path}

    array_summary_path = out_dir + "array_summary.json"
    array_summary = {
        "ndim": int(img_data.ndim),
        "shape": [int(x) for x in img_data.shape],
        "dtype": str(img_data.dtype),
        "bands": int(img_data.shape[0]) if img_data.ndim == 3 else 1,
        "selected_rgb_bands": selected_rgb_bands,
    }
    storage.upload_bytes(
        array_summary_path,
        json.dumps(array_summary, indent=2).encode("utf-8"),
        "application/json",
    )

    # --- upload gray ---
    res = {
        "status": "ok",
        "photo_id": photo_id,
        "file": source_path,
        "gray": None,
        "rgb": None,
        "array_summary_path": array_summary_path,
        "array_summary": array_summary,
    }

    if gray_img is not None:
        buf = io.BytesIO()
        gray_img.save(buf, format="JPEG", quality=92, optimize=True)

        def upload_gray():
            _maybe_raise_eval_fault("transform_gray_upload", photo_id)
            return storage.upload_bytes(out_gray, buf.getvalue(), "image/jpeg")

        uploaded = retry_call(
            upload_gray,
            attempts=3,
            delays=(0.0, 2.0),
        )
        res["gray"] = "uploaded" if uploaded else "exists"
    else:
        res["gray"] = "none"

    # --- upload rgb (only when available) ---
    if rgb_img is not None:
        buf = io.BytesIO()
        rgb_img.save(buf, format="JPEG", quality=92, optimize=True)

        def upload_rgb():
            _maybe_raise_eval_fault("transform_rgb_upload", photo_id)
            return storage.upload_bytes(out_rgb, buf.getvalue(), "image/jpeg")

        uploaded = retry_call(
            upload_rgb,
            attempts=3,
            delays=(0.0, 2.0),
        )
        res["rgb"] = "uploaded" if uploaded else "exists"
    else:
        res["rgb"] = "none"

    # --- mark done ---
    db.pg_mark_done(photo_id, out_gray, out_rgb if rgb_img is not None else None)
    print(f"  OK photo_id={photo_id} gray={res['gray']} rgb={res['rgb']}")

    return res
