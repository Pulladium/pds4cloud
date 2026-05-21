"""
Unit tests for nodes/transform/image_ops.py — pure functions, no I/O.
"""

import numpy as np
import pytest

from nodes.transform.image_ops import normalize_2d, img_key_from_pdr


# ---------------------------------------------------------------------------
# normalize_2d
# ---------------------------------------------------------------------------

class TestNormalize2d:
    def test_normal_range(self):
        arr = np.array([[0.0, 127.5, 255.0]])
        out = normalize_2d(arr)
        assert out.dtype == np.uint8
        assert out[0, 0] == 0
        assert out[0, 2] == 255

    def test_all_zeros(self):
        arr = np.zeros((4, 4))
        out = normalize_2d(arr)
        # min == max → constant 128
        assert (out == 128).all()

    def test_constant_value(self):
        arr = np.full((3, 3), 42.0)
        out = normalize_2d(arr)
        assert (out == 128).all()

    def test_all_nan(self):
        arr = np.full((2, 2), np.nan)
        out = normalize_2d(arr)
        assert out.dtype == np.uint8
        assert (out == 0).all()

    def test_with_inf_ignored(self):
        arr = np.array([[0.0, 1.0, np.inf, -np.inf]])
        out = normalize_2d(arr)
        # finite values span 0..1 → out[0,0]=0, out[0,1]=255
        assert out[0, 0] == 0
        assert out[0, 1] == 255

    def test_output_clipped_to_uint8(self):
        arr = np.linspace(0, 1, 100).reshape(10, 10)
        out = normalize_2d(arr)
        assert out.min() >= 0
        assert out.max() <= 255

    def test_shape_preserved(self):
        arr = np.random.rand(7, 13)
        out = normalize_2d(arr)
        assert out.shape == (7, 13)


# ---------------------------------------------------------------------------
# img_key_from_pdr
# ---------------------------------------------------------------------------

class TestImgKeyFromPdr:
    def test_image_key(self):
        assert img_key_from_pdr({"IMAGE": ..., "LABEL": ...}) == "IMAGE"

    def test_product_image_key(self):
        assert img_key_from_pdr({"PRODUCT_IMAGE": ..., "LABEL": ...}) == "PRODUCT_IMAGE"

    def test_science_image_key(self):
        assert img_key_from_pdr({"SCIENCE_IMAGE": ...}) == "SCIENCE_IMAGE"

    def test_image_takes_priority(self):
        # IMAGE is checked first
        assert img_key_from_pdr({"IMAGE": ..., "PRODUCT_IMAGE": ...}) == "IMAGE"

    def test_no_matching_key(self):
        assert img_key_from_pdr({"LABEL": ..., "HEADER": ...}) is None

    def test_empty_dict(self):
        assert img_key_from_pdr({}) is None
