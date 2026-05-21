"""
Tests for nodes/ingest/demo.make_demo_img_bytes and the read_imgdata roundtrip.
"""

import io
import numpy as np
import pytest

from nodes.ingest.demo import make_demo_img_bytes
from nodes.transform.image_ops import read_imgdata


class TestMakeDemoImgBytes:

    def test_starts_with_numpy_magic(self):
        raw = make_demo_img_bytes(0)
        assert raw[:6] == b"\x93NUMPY"

    def test_different_products_differ(self):
        assert make_demo_img_bytes(0) != make_demo_img_bytes(1)

    def test_same_seed_is_deterministic(self):
        assert make_demo_img_bytes(5) == make_demo_img_bytes(5)

    def test_roundtrip_shape_valid(self):
        """Each product produces one of the three expected shapes."""
        valid = {(32, 32), (3, 32, 32), (14, 32, 32)}
        for i in range(6):
            arr = read_imgdata(make_demo_img_bytes(product_index=i))
            assert arr.shape in valid, f"index={i} unexpected shape {arr.shape}"

    def test_roundtrip_shape_cycles(self):
        """Shapes cycle deterministically by product_index % 3."""
        assert read_imgdata(make_demo_img_bytes(0)).shape == (32, 32)
        assert read_imgdata(make_demo_img_bytes(1)).shape == (3, 32, 32)
        assert read_imgdata(make_demo_img_bytes(2)).shape == (14, 32, 32)
        assert read_imgdata(make_demo_img_bytes(3)).shape == (32, 32)   # repeats

    def test_roundtrip_dtype_numeric(self):
        arr = read_imgdata(make_demo_img_bytes(0))
        assert np.issubdtype(arr.dtype, np.number)

    def test_roundtrip_values_nonzero(self):
        arr = read_imgdata(make_demo_img_bytes(0))
        assert arr.max() > 0

    def test_roundtrip_products_differ(self):
        a0 = read_imgdata(make_demo_img_bytes(0))
        a1 = read_imgdata(make_demo_img_bytes(1))
        assert not np.array_equal(a0, a1)
