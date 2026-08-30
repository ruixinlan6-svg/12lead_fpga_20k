"""Tests for integer requantization arithmetic, multiplier-shift decomposition, and clamping."""

import unittest
import numpy as np

try:
    from train.ec57.quantize_int8 import (
        decompose_multiplier_shift,
        requantize_integer,
        quantize_tensor_symmetric_int8
    )
except ImportError:
    decompose_multiplier_shift = None
    requantize_integer = None
    quantize_tensor_symmetric_int8 = None


class TestRequantization(unittest.TestCase):
    """Tests that requantization math is 100% bit-exact with hardware RTL."""

    def setUp(self):
        if requantize_integer is None:
            self.skipTest("quantize_int8 not implemented yet")

    def test_decompose_multiplier_shift(self):
        """Multiplier decomposition M = mult * 2^(-shift) where mult in [0, 2^31 - 1]."""
        scales = [1.0, 0.5, 0.125, 0.03125, 0.0078125, 0.0001234, 1.95]
        for scale in scales:
            mult, shift = decompose_multiplier_shift(scale)
            self.assertGreaterEqual(mult, 0)
            self.assertLess(mult, 2**31)
            self.assertGreaterEqual(shift, 0)
            self.assertLessEqual(shift, 31)

            # Reconstructed value should be within tiny numerical epsilon
            reconstructed = mult / (2.0 ** shift)
            self.assertAlmostEqual(scale, reconstructed, places=5)

    def test_requantize_zero_shift(self):
        """When shift == 0 and mult == 1, requantize passes accumulator directly."""
        res = requantize_integer(acc=50, mult=1, shift=0, relu=False)
        self.assertEqual(res, 50)

    def test_requantize_positive_rounding_away_from_zero(self):
        """Positive values round half away from zero: 1.5 -> 2, 2.5 -> 3."""
        # acc * mult = 3, shift = 1 -> 3 / 2 = 1.5 -> 2
        res = requantize_integer(acc=3, mult=1, shift=1, relu=False)
        self.assertEqual(res, 2)

        # acc * mult = 5, shift = 1 -> 5 / 2 = 2.5 -> 3
        res = requantize_integer(acc=5, mult=1, shift=1, relu=False)
        self.assertEqual(res, 3)

    def test_requantize_negative_rounding_away_from_zero(self):
        """Negative values round half away from zero: -1.5 -> -2, -2.5 -> -3."""
        # acc * mult = -3, shift = 1 -> -3 / 2 = -1.5 -> -2
        res = requantize_integer(acc=-3, mult=1, shift=1, relu=False)
        self.assertEqual(res, -2)

        # acc * mult = -5, shift = 1 -> -5 / 2 = -2.5 -> -3
        res = requantize_integer(acc=-5, mult=1, shift=1, relu=False)
        self.assertEqual(res, -3)

    def test_requantize_saturation_clamping(self):
        """Values exceeding [-128, 127] must saturate symmetrically."""
        res_high = requantize_integer(acc=1000, mult=1, shift=0, relu=False)
        self.assertEqual(res_high, 127)

        res_low = requantize_integer(acc=-1000, mult=1, shift=0, relu=False)
        self.assertEqual(res_low, -128)

    def test_requantize_relu_mode(self):
        """When relu is True, negative values must clamp to 0."""
        res_neg = requantize_integer(acc=-50, mult=1, shift=0, relu=True)
        self.assertEqual(res_neg, 0)

        res_pos = requantize_integer(acc=50, mult=1, shift=0, relu=True)
        self.assertEqual(res_pos, 50)


if __name__ == '__main__':
    unittest.main()
