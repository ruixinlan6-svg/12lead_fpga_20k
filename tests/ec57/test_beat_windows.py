"""Tests for M2/M3 beat window extraction, normalization, and auxiliary feature packaging."""

import unittest
import numpy as np

try:
    from train.ec57.beat_dataset import (
        extract_beat_window,
        normalize_waveform_int8,
        normalize_scalar_features_int8,
        round_half_away_from_zero,
        BeatWindowSpec
    )
except ImportError:
    extract_beat_window = None
    normalize_waveform_int8 = None
    normalize_scalar_features_int8 = None
    round_half_away_from_zero = None
    BeatWindowSpec = None


class TestBeatWindows(unittest.TestCase):
    """Verifies that beat window extraction and normalization strictly obey Section 1.3."""

    def setUp(self):
        if extract_beat_window is None:
            self.skipTest("beat_dataset not implemented yet")

    def test_window_geometry(self):
        """Window must be 160 points with R peak exactly at index 64."""
        signal = np.arange(1000, dtype=np.int16)
        r_index = 200

        window = extract_beat_window(signal, r_index=r_index)
        self.assertEqual(len(window), 160)
        # Signal at index 200 must be placed at window index 64
        self.assertEqual(window[64], signal[200])
        self.assertEqual(window[0], signal[200 - 64])
        self.assertEqual(window[159], signal[200 + 95])

    def test_window_boundary_padding(self):
        """Window near signal start/end must zero-pad or edge-pad deterministically."""
        signal = np.arange(100, dtype=np.int16)
        # R peak at index 10 (needs 64 points before, so 54 points before start)
        window = extract_beat_window(signal, r_index=10)
        self.assertEqual(len(window), 160)
        self.assertEqual(window[64], signal[10])
        # Points before start should be 0
        self.assertEqual(window[0], 0)
        self.assertEqual(window[53], 0)
        self.assertEqual(window[54], signal[0])

    def test_waveform_normalization_int8(self):
        """Waveform normalization removes median, scales to 127 with 100 uV floor, and clamps to [-128, 127]."""
        # Create a synthetic QRS pulse with median 50
        raw = np.full(160, 50, dtype=np.int16)
        raw[64] = 50 + 500  # Peak of 500 LSB (2500 uV)
        raw[60] = 50 - 200  # Q valley

        norm_int8 = normalize_waveform_int8(raw, scale_ref=500.0)
        self.assertEqual(len(norm_int8), 160)
        self.assertEqual(norm_int8.dtype, np.int8)

        # Base should be 0 since median is 50
        self.assertEqual(norm_int8[0], 0)
        # Peak at 500 / 500 * 127 = 127
        self.assertEqual(norm_int8[64], 127)
        # Valley at -200 / 500 * 127 = -50.8 -> -51
        self.assertEqual(norm_int8[60], -51)

    def test_scale_ref_minimum_floor(self):
        """If scale_ref is < 20 LSB (100 uV), floor at 20 LSB."""
        raw = np.zeros(160, dtype=np.int16)
        raw[64] = 10  # 10 LSB (50 uV)
        norm_int8 = normalize_waveform_int8(raw, scale_ref=5.0)  # less than 100 uV floor (20 LSB)
        # Saturated with floor 20: 10 / 20 * 127 = 63.5 -> 64
        self.assertEqual(norm_int8[64], 64)

    def test_scalar_features_normalization_int8(self):
        """4 scalar features normalized via median and IQR: round(32 * (x - median) / (IQR / 2))."""
        medians = np.array([1.0, 80.0, 1.0, 0.95], dtype=np.float64)
        iqrs    = np.array([0.2, 20.0, 0.4, 0.10], dtype=np.float64)

        raw_feat = np.array([1.1, 90.0, 1.2, 0.90], dtype=np.float64)
        # Feat 0: 32 * (1.1 - 1.0) / 0.1 = 32
        # Feat 1: 32 * (90.0 - 80.0) / 10.0 = 32
        # Feat 2: 32 * (1.2 - 1.0) / 0.2 = 32
        # Feat 3: 32 * (0.90 - 0.95) / 0.05 = -32
        feat_int8 = normalize_scalar_features_int8(raw_feat, medians=medians, iqrs=iqrs)
        self.assertEqual(feat_int8.dtype, np.int8)
        np.testing.assert_array_equal(feat_int8, np.array([32, 32, 32, -32], dtype=np.int8))

    def test_zero_iqr_fails_closed(self):
        """If IQR is 0 for any feature, normalization must raise ValueError."""
        medians = np.array([1.0, 80.0, 1.0, 0.95])
        iqrs    = np.array([0.2, 0.0, 0.4, 0.10])  # Zero IQR on feat 1
        raw_feat = np.array([1.1, 80.0, 1.2, 0.90])

        with self.assertRaises(ValueError):
            normalize_scalar_features_int8(raw_feat, medians=medians, iqrs=iqrs)

    def test_round_half_away_from_zero(self):
        """Check symmetric round-half-away-from-zero rounding behavior."""
        self.assertEqual(round_half_away_from_zero(0.5), 1)
        self.assertEqual(round_half_away_from_zero(-0.5), -1)
        self.assertEqual(round_half_away_from_zero(1.5), 2)
        self.assertEqual(round_half_away_from_zero(-1.5), -2)
        self.assertEqual(round_half_away_from_zero(0.4), 0)
        self.assertEqual(round_half_away_from_zero(-0.4), 0)


if __name__ == '__main__':
    unittest.main()
