"""
nodes/transform/image_ops.py — Pure image utility functions.
"""

import os
import tempfile
import warnings

import numpy as np

warnings.filterwarnings("ignore", category=UserWarning, module="pdr")


def normalize_2d(arr: np.ndarray) -> np.ndarray:
    valid = np.isfinite(arr)
    if not np.any(valid):
        return np.zeros(arr.shape, dtype=np.uint8)
    mn = np.nanmin(arr[valid])
    mx = np.nanmax(arr[valid])
    if mn == mx:
        return np.full(arr.shape, 128, dtype=np.uint8)
    x = (arr - mn) / (mx - mn)
    return np.clip(x * 255, 0, 255).astype(np.uint8)


def img_key_from_pdr(data) -> str | None:
    for k in ("IMAGE", "PRODUCT_IMAGE", "SCIENCE_IMAGE"):
        if k in data:
            return k
    return None


_NUMPY_MAGIC = b"\x93NUMPY"


def read_imgdata(raw_bytes: bytes) -> np.ndarray:
    """
    Parse raw_bytes into a numpy array.

    - Numpy format (magic b'\\x93NUMPY'): used by demo/test files — loaded directly.
    - Everything else: written to a tmpfile and parsed by pdr (real PDS3 .IMG files).
    """
    import io

    if raw_bytes[:6] == _NUMPY_MAGIC:
        return np.load(io.BytesIO(raw_bytes))

    import pdr

    shm_dir = "/dev/shm" if os.path.isdir("/dev/shm") else None

    with tempfile.NamedTemporaryFile(dir=shm_dir, suffix=".IMG", delete=True) as tmp:
        tmp.write(raw_bytes)
        tmp.flush()

        data = pdr.read(tmp.name)
        k = img_key_from_pdr(data)
        if not k:
            raise ValueError(f"No IMAGE key in pdr data. keys={list(data.keys())}")

        obj = data[k]

        if hasattr(obj, "data") and isinstance(obj.data, np.ndarray):
            return np.asarray(obj.data)

        if isinstance(obj, np.ndarray):
            return obj

        try:
            return np.asarray(obj)
        except Exception:
            raise TypeError(f"Unexpected IMAGE type: {type(obj)}")
