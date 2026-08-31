from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np


sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools" / "remote"))


class TestM2ValidationErrorAudit(unittest.TestCase):
    def test_development_split_guard_rejects_internal_test_and_unknown_names(self):
        from audit_m2_validation_errors import validate_development_split_name

        self.assertEqual(validate_development_split_name("train"), "train")
        self.assertEqual(validate_development_split_name("validation"), "validation")
        for split in ("internal_test", "test", "locked", ""):
            with self.subTest(split=split), self.assertRaisesRegex(ValueError, "train or validation"):
                validate_development_split_name(split)

    def test_taxonomy_has_exact_counts_groups_and_deterministic_error_rows(self):
        from audit_m2_validation_errors import summarize_validation_errors

        arrays = {
            "labels": np.array([0, 0, 1, 1, 0, 1], dtype=np.int64),
            "patient_ids": np.array(["p1", "p1", "p2", "p2", "p3", "p3"]),
            "record_ids": np.array(["r1", "r1", "r2", "r2", "r3", "r3"]),
            "sample_indices": np.array([10, 20, 30, 40, 50, 60], dtype=np.int64),
            "native_symbols": np.array(["S", "N", "V", "V", "N", "V"]),
            "source_file_sha256": np.array(["a" * 64] * 6),
            "features": np.arange(24, dtype=np.int8).reshape(6, 4),
        }
        report, rows = summarize_validation_errors(
            arrays,
            np.array([0.9, 0.4, 0.95, 0.2, 0.9995, 0.85], dtype=np.float64),
            thresholds=[0.8, 0.99],
        )

        at_080 = report["thresholds"]["0.800"]
        self.assertEqual(at_080["counts"], {"vtp": 2, "vfn": 1, "vfp": 2, "vtn": 1})
        self.assertEqual(at_080["false_positive_native_symbols"], {"N": 1, "S": 1})
        self.assertEqual(at_080["false_positive_patients"], {"p1": 1, "p3": 1})
        self.assertEqual(at_080["false_negative_records"], {"r2": 1})

        at_099 = report["thresholds"]["0.990"]
        self.assertEqual(at_099["counts"], {"vtp": 0, "vfn": 3, "vfp": 1, "vtn": 2})
        self.assertEqual(at_099["false_positive_native_symbols"], {"N": 1})
        self.assertEqual([row["cache_index"] for row in rows], [0, 2, 3, 4, 5])
        self.assertEqual(rows[0]["error_at_0.800"], "VFP")
        self.assertEqual(rows[0]["error_at_0.990"], "")
        self.assertEqual(rows[2]["error_at_0.800"], "VFN")
        self.assertEqual(rows[2]["error_at_0.990"], "VFN")

    def test_taxonomy_rejects_misaligned_or_non_validation_native_labels(self):
        from audit_m2_validation_errors import summarize_validation_errors

        base = {
            "labels": np.array([0, 1], dtype=np.int64),
            "patient_ids": np.array(["p1", "p2"]),
            "record_ids": np.array(["r1", "r2"]),
            "sample_indices": np.array([10, 20], dtype=np.int64),
            "native_symbols": np.array(["N", "V"]),
            "source_file_sha256": np.array(["a" * 64, "b" * 64]),
            "features": np.zeros((2, 4), dtype=np.int8),
        }
        with self.assertRaisesRegex(ValueError, "aligned"):
            summarize_validation_errors(base, np.array([0.5]), thresholds=[0.5])
        invalid = dict(base)
        invalid["native_symbols"] = np.array(["Q", "V"])
        with self.assertRaisesRegex(ValueError, "native symbols"):
            summarize_validation_errors(invalid, np.array([0.5, 0.5]), thresholds=[0.5])


if __name__ == "__main__":
    unittest.main()
