from __future__ import annotations

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools" / "ec57"))

from analyze_ludb_annotation_support import (
    AnnotationSupportError,
    aggregate_dual_reports,
    annotation_support,
    dual_qrs_counts,
)


class TestAnnotationSupportAnalysis(unittest.TestCase):
    def test_support_is_first_and_last_reference_plus_fixed_tolerance(self):
        self.assertEqual(annotation_support([331, 671, 1000, 1984], tolerance_samples=38), (293, 2022))

    def test_empty_or_invalid_reference_support_fails_closed(self):
        with self.assertRaises(AnnotationSupportError):
            annotation_support([], tolerance_samples=38)
        with self.assertRaises(AnnotationSupportError):
            annotation_support([100], tolerance_samples=-1)

    def test_dual_counts_preserve_full_record_and_separate_unsupported_outputs(self):
        references = [331, 671, 1000, 1321, 1657, 1984]
        detections = [20, 331, 671, 1000, 1321, 1657, 1984, 2314]

        result = dual_qrs_counts(references, detections, sample_rate_hz=250, tolerance_ms=150.0)

        self.assertEqual(result["full"], {"QTP": 6, "QFN": 0, "QFP": 2})
        self.assertEqual(result["annotation_support"], {"QTP": 6, "QFN": 0, "QFP": 0})
        self.assertEqual(result["unsupported_detected_indices"], [20, 2314])
        self.assertEqual(result["support_samples"], [293, 2022])

    def test_support_boundary_is_inclusive_and_does_not_modify_inputs(self):
        references = [100, 300]
        detections = [62, 100, 300, 338]
        references_before = list(references)
        detections_before = list(detections)

        result = dual_qrs_counts(references, detections, sample_rate_hz=250, tolerance_ms=150.0)

        self.assertEqual(result["annotation_support"]["QFP"], 2)
        self.assertEqual(result["unsupported_detected_indices"], [])
        self.assertEqual(references, references_before)
        self.assertEqual(detections, detections_before)

    def test_aggregate_preserves_both_denominators_and_computes_rates(self):
        reports = [
            {
                "full": {"QTP": 6, "QFN": 0, "QFP": 2},
                "annotation_support": {"QTP": 6, "QFN": 0, "QFP": 0},
                "unsupported_detected_indices": [20, 2314],
            },
            {
                "full": {"QTP": 4, "QFN": 1, "QFP": 1},
                "annotation_support": {"QTP": 4, "QFN": 1, "QFP": 0},
                "unsupported_detected_indices": [2400],
            },
        ]

        summary = aggregate_dual_reports(reports)

        self.assertEqual(summary["full"]["counts"], {"QTP": 10, "QFN": 1, "QFP": 3})
        self.assertAlmostEqual(summary["full"]["qrs_se_percent"], 10 / 11 * 100)
        self.assertAlmostEqual(summary["full"]["qrs_plus_p_percent"], 10 / 13 * 100)
        self.assertAlmostEqual(summary["full"]["average_qrs_se_percent"], 90.0)
        self.assertAlmostEqual(summary["full"]["average_qrs_plus_p_percent"], 77.5)
        self.assertEqual(summary["annotation_support"]["counts"], {"QTP": 10, "QFN": 1, "QFP": 0})
        self.assertAlmostEqual(summary["annotation_support"]["average_qrs_se_percent"], 90.0)
        self.assertAlmostEqual(summary["annotation_support"]["average_qrs_plus_p_percent"], 100.0)
        self.assertEqual(summary["unsupported_detection_count"], 3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
