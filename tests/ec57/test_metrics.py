"""Tests for EC57 classification metrics and statistical reporting."""

import unittest
import numpy as np
from train.ec57.metrics import (
    VEBConfusionCounts,
    wilson_score_interval,
    compute_patient_level_metrics,
    patient_bootstrap_ci
)


class TestEC57Metrics(unittest.TestCase):
    """Verifies standard ANSI/AAMI EC57:2012 metrics formulas and statistical bounds."""

    def test_confusion_rates(self):
        """Check VEB Se, +P, and FPR (VFP / (VTN + VFP)) formulas."""
        counts = VEBConfusionCounts(vtp=90, vfn=10, vfp=5, vtn=995)
        rates = counts.compute_rates()

        # VEB Se = 90 / (90 + 10) = 90.0%
        self.assertAlmostEqual(rates["veb_se_percent"], 90.0)
        # VEB +P = 90 / (90 + 5) = 94.7368%
        self.assertAlmostEqual(rates["veb_plus_p_percent"], 90.0 / 95.0 * 100.0)
        # VEB FPR = 5 / (995 + 5) = 0.50%
        self.assertAlmostEqual(rates["veb_fpr_percent"], 0.50)

    def test_zero_denominator_fails_closed_to_none(self):
        """Zero denominators must yield None instead of 0 or crashing."""
        counts = VEBConfusionCounts(vtp=0, vfn=0, vfp=0, vtn=100)
        rates = counts.compute_rates()

        self.assertIsNone(rates["veb_se_percent"])
        self.assertIsNone(rates["veb_plus_p_percent"])
        self.assertAlmostEqual(rates["veb_fpr_percent"], 0.0)

    def test_wilson_confidence_interval(self):
        """Wilson score interval must bound the point estimate symmetrically/asymmetrically."""
        ci = wilson_score_interval(successes=90, total=100, confidence=0.95)
        self.assertIsNotNone(ci)
        lower, upper = ci
        self.assertLess(lower, 90.0)
        self.assertGreater(upper, 90.0)
        self.assertGreaterEqual(lower, 0.0)
        self.assertLessEqual(upper, 100.0)

    def test_patient_level_aggregation(self):
        """Gross and Average rates must be calculated separately across multiple patients."""
        patient_records = {
            "pat_01": VEBConfusionCounts(vtp=80, vfn=20, vfp=10, vtn=900),  # Se=80%, +P=88.89%
            "pat_02": VEBConfusionCounts(vtp=10, vfn=0, vfp=0, vtn=100),    # Se=100%, +P=100%
        }
        res = compute_patient_level_metrics(patient_records)

        # Gross: VTP=90, VFN=20, VFP=10, VTN=1000
        # Gross Se = 90 / 110 = 81.818%
        self.assertAlmostEqual(res["gross_rates"]["veb_se_percent"], 90.0 / 110.0 * 100.0)
        # Average Se = (80% + 100%) / 2 = 90.0%
        self.assertAlmostEqual(res["average_rates"]["veb_se_percent"], 90.0)

    def test_patient_bootstrap_ci_deterministic(self):
        """Bootstrap CI must be reproducible with fixed random seed."""
        patient_records = {
            f"pat_{i}": VEBConfusionCounts(vtp=i * 5, vfn=2, vfp=1, vtn=100)
            for i in range(1, 10)
        }
        ci1 = patient_bootstrap_ci(patient_records, n_resamples=100, seed=20260827)
        ci2 = patient_bootstrap_ci(patient_records, n_resamples=100, seed=20260827)

        self.assertEqual(ci1, ci2)
        self.assertIn("veb_se_bootstrap_ci", ci1)


if __name__ == '__main__':
    unittest.main()
