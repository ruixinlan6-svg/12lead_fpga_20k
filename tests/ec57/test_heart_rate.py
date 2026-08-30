from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "train" / "ec57"))

from heart_rate import HeartRateReference, compute_hr_fixed, compute_hr_float


class TestHeartRateReference(unittest.TestCase):
    def test_only_valid_rr_and_recent_five_median_are_used(self):
        self.assertEqual(compute_hr_float([200, 1000, 1100, 900, 1000, 2000, 2100]), 60.0)
        self.assertAlmostEqual(compute_hr_fixed([200, 1000, 1100, 900, 1000, 2000, 2100]), 60.0, places=4)

        reference = HeartRateReference(sample_rate_hz=250)
        updates = []
        for sample_index in (0, 250, 525, 750, 1000, 1250):
            updates.append(reference.add_qrs(sample_index))
        self.assertTrue(updates[-1].valid)
        self.assertEqual(updates[-1].rr_history_ms, [1000, 1100, 900, 1000, 1000])
        self.assertEqual(updates[-1].heart_rate_bpm, 60.0)

    def test_invalid_rr_does_not_enter_history(self):
        reference = HeartRateReference(sample_rate_hz=250)
        reference.add_qrs(0)
        reference.add_qrs(50)  # 200 ms: below the frozen valid range
        update = reference.add_qrs(300)  # 1000 ms from the previous QRS
        self.assertTrue(update.valid)
        self.assertEqual(update.rr_history_ms, [1000])
        self.assertEqual(update.heart_rate_bpm, 60.0)

    def test_three_seconds_without_valid_qrs_invalidates_hr_and_does_not_hold_old_value(self):
        reference = HeartRateReference(sample_rate_hz=250)
        reference.add_qrs(0)
        reference.add_qrs(250)
        stale = reference.advance_to(1000)
        self.assertFalse(stale.valid)
        self.assertIsNone(stale.heart_rate_bpm)
        self.assertEqual(stale.state, "HR_INVALID_NO_QRS")

    def test_float_and_fixed_hr_are_equivalent_for_integer_sample_intervals(self):
        rr_ms = [997, 1001, 1005, 999, 1003]
        self.assertAlmostEqual(compute_hr_fixed(rr_ms), compute_hr_float(rr_ms), places=4)


if __name__ == "__main__":
    unittest.main(verbosity=2)
