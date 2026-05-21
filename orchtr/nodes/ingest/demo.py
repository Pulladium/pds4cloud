"""
nodes/ingest/demo.py — Simulated PDS product stream for demo / offline use.
"""


def build_demo_products(from_n: int, to_n: int) -> list[dict]:
    """Return a list of fake Mastcam-Z products covering the [from_n, to_n] range."""
    products = []
    for i in range(from_n, to_n + 1):
        sol = str(10 + i).zfill(5)
        products.append({
            "id": f"urn:nasa:pds:mars2020_mast_z:data_raw::demo_{i:04d}",
            "sol": sol,
            "filename": f"ZL0_{sol}_0000001_{i:04d}EDR_N0010000ZCAM08500_110085J01.IMG",
            "metadata": {"sol_number": [sol], "product_index": i},
        })
    return products


def make_demo_img_bytes(product_index: int = 0) -> bytes:
    """
    Return a numpy array serialised as .npy bytes, cycling through three shapes:
      product_index % 3 == 0 → (32, 32)       2D single-band  → gray only
      product_index % 3 == 1 → (3, 32, 32)    3-band          → gray + rgb
      product_index % 3 == 2 → (14, 32, 32)   14-band         → gray + rgb (bands 0,12,13)

    read_imgdata() detects the numpy magic header and loads it directly,
    bypassing pdr (which requires real PDS3 label+data pairs on disk).
    """
    import io
    import numpy as np

    rng = np.random.default_rng(product_index)
    mode = product_index % 3

    if mode == 0:
        shape = (32, 32)
    elif mode == 1:
        shape = (3, 32, 32)
    else:
        shape = (14, 32, 32)

    pixels = rng.integers(0, 4096, shape, dtype=np.uint16).astype(np.float32)
    buf = io.BytesIO()
    np.save(buf, pixels)
    return buf.getvalue()
