from __future__ import annotations

import sys
import math
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "train" / "ec57"))

from resample import (
    ResampleError,
    ResampledEvent,
    design_polyphase,
    map_event_sample,
    resample_signal,
    validate_event_mapping,
)


class TestResampleTimestamps(unittest.TestCase):
    def test_rational_polyphase_ratio_is_reduced(self):
        half_rate = design_polyphase(500, 250)
        self.assertEqual((half_rate.up, half_rate.down), (1, 2))
        incart = design_polyphase(257, 250)
        self.assertEqual((incart.up, incart.down), (250, 257))
        self.assertEqual(incart.target_rate_hz, 250)

    def test_event_mapping_preserves_source_time_and_target_index(self):
        mapping = map_event_sample("r-1", source_sample_index=257, source_rate_hz=257, target_rate_hz=250)
        self.assertEqual(mapping.source_sample_index, 257)
        self.assertAlmostEqual(mapping.event_time_s, 1.0, places=12)
        self.assertEqual(mapping.target_sample_index, 250)
        self.assertAlmostEqual(mapping.target_time_s, 1.0, places=12)
        self.assertAlmostEqual(mapping.error_ms, 0.0, places=12)
        validate_event_mapping(mapping)

    def test_timestamp_error_over_two_ms_is_rejected(self):
        mapping = ResampledEvent(
            event_id="bad-time",
            source_sample_index=1,
            source_rate_hz=360,
            target_rate_hz=250,
            event_time_s=1 / 360,
            target_sample_index=2,
            target_time_s=2 / 250,
            error_ms=(2 / 250 - 1 / 360) * 1000,
        )
        with self.assertRaises(ResampleError):
            validate_event_mapping(mapping)

    def test_annotation_drift_over_one_target_sample_is_rejected(self):
        mapping = ResampledEvent(
            event_id="bad-drift",
            source_sample_index=10,
            source_rate_hz=250,
            target_rate_hz=250,
            event_time_s=10 / 250,
            target_sample_index=12,
            target_time_s=12 / 250,
            error_ms=8.0,
        )
        with self.assertRaises(ResampleError):
            validate_event_mapping(mapping)

    def test_polyphase_constant_signal_is_stable(self):
        output = resample_signal([17.0] * 32, source_rate_hz=500, target_rate_hz=250)
        self.assertGreaterEqual(len(output), 15)
        self.assertLessEqual(max(abs(value - 17.0) for value in output[2:-2]), 1e-6)

    def test_polyphase_preserves_ecg_passband_against_analytic_reference(self):
        source_rate = 257
        target_rate = 250
        duration_s = 8
        for frequency_hz in (5, 10, 25, 40):
            with self.subTest(frequency_hz=frequency_hz):
                source = [
                    math.sin(2.0 * math.pi * frequency_hz * index / source_rate)
                    for index in range(source_rate * duration_s)
                ]
                actual = resample_signal(source, source_rate, target_rate)
                trim = target_rate
                actual = actual[trim:-trim]
                expected = [
                    math.sin(2.0 * math.pi * frequency_hz * index / target_rate)
                    for index in range(trim, target_rate * duration_s - trim)
                ]
                count = len(actual)
                sin_projection = 2.0 * sum(a * e for a, e in zip(actual, expected)) / count
                cosine = [
                    math.cos(2.0 * math.pi * frequency_hz * index / target_rate)
                    for index in range(trim, target_rate * duration_s - trim)
                ]
                cos_projection = 2.0 * sum(a * e for a, e in zip(actual, cosine)) / count
                amplitude = math.hypot(sin_projection, cos_projection)
                phase_error = abs(math.atan2(cos_projection, sin_projection))
                rms_error = math.sqrt(sum((a - e) ** 2 for a, e in zip(actual, expected)) / count)
                self.assertGreaterEqual(amplitude, 0.98)
                self.assertLessEqual(amplitude, 1.02)
                self.assertLessEqual(phase_error, 0.02)
                self.assertLessEqual(rms_error, 0.02)


if __name__ == "__main__":
    unittest.main(verbosity=2)
