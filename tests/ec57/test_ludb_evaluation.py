from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "train" / "ec57"))

from ludb_io import (
    CANONICAL_LEADS,
    LEAD_ANNOTATION_EXTENSIONS,
    LUDBRecordError,
    build_sha256_inventory,
    cluster_reference_qrs,
    discover_ludb_records,
    physical_mv_to_interface_lsb,
    validate_ludb_record,
    verify_published_sha256s,
)
from evaluate_ludb import _m1_gate_passes, evaluate_loaded_record, select_and_fuse_record
from evaluate_qrs import annotation_support_span, evaluate_record


def synthetic_qrs(peaks: list[int], length: int = 2500, offset: int = 0) -> list[int]:
    signal = [((index + offset) % 31) - 15 for index in range(length)]
    # Keep adjacent changes below the frozen >2 mV impulsive-noise threshold
    # while retaining a narrow, detector-visible QRS morphology.
    pulse = tuple(zip(range(-5, 6), (100, 300, 600, 900, 1100, 1200, 1100, 900, 600, 300, 100)))
    for peak in peaks:
        for delta, value in pulse:
            signal[peak + delta] += value
    return signal


class TestLUDBIO(unittest.TestCase):
    def test_annotation_extensions_cover_canonical_twelve_leads(self):
        self.assertEqual(
            CANONICAL_LEADS,
            ("I", "II", "III", "aVR", "aVL", "aVF", "V1", "V2", "V3", "V4", "V5", "V6"),
        )
        self.assertEqual(set(LEAD_ANNOTATION_EXTENSIONS), set(CANONICAL_LEADS))
        self.assertEqual(LEAD_ANNOTATION_EXTENSIONS["II"], "ii")
        self.assertEqual(LEAD_ANNOTATION_EXTENSIONS["aVR"], "avr")

    def test_physical_millivolts_map_to_five_microvolt_lsb_with_saturation(self):
        self.assertEqual(physical_mv_to_interface_lsb([0.0, 0.005, -0.005, 0.0025, -0.0025]), [0, 1, -1, 1, -1])
        self.assertEqual(physical_mv_to_interface_lsb([1000.0, -1000.0]), [32767, -32768])

    def test_reference_clusters_use_lead_median_and_two_ms_mapping_gate(self):
        peaks = {
            "I": [500, 1000],
            "II": [502, 998],
            "V1": [504, 1002],
        }
        clusters = cluster_reference_qrs(peaks, source_rate_hz=500, target_rate_hz=250)
        self.assertEqual([cluster.target_sample_index for cluster in clusters], [251, 500])
        self.assertEqual(clusters[0].contributing_leads, ("I", "II", "V1"))
        self.assertEqual(clusters[0].source_sample_median, 502.0)
        self.assertLessEqual(max(cluster.mapping_error_ms for cluster in clusters), 2.0)

    def test_reference_cluster_never_accepts_two_peaks_from_one_lead(self):
        with self.assertRaises(LUDBRecordError):
            cluster_reference_qrs({"II": [500, 520], "V1": [501]}, source_rate_hz=500)

    def test_record_validation_rejects_missing_lead_annotation_or_wrong_shape(self):
        annotation_peaks = {lead: [500, 1000] for lead in CANONICAL_LEADS}
        validate_ludb_record(
            sample_rate_hz=500,
            sample_count=5000,
            signal_names=[lead.lower() for lead in CANONICAL_LEADS],
            annotation_peaks_by_lead=annotation_peaks,
        )
        missing = dict(annotation_peaks)
        missing.pop("V6")
        with self.assertRaises(LUDBRecordError):
            validate_ludb_record(
                sample_rate_hz=500,
                sample_count=5000,
                signal_names=CANONICAL_LEADS,
                annotation_peaks_by_lead=missing,
            )
        with self.assertRaises(LUDBRecordError):
            validate_ludb_record(
                sample_rate_hz=250,
                sample_count=2500,
                signal_names=CANONICAL_LEADS,
                annotation_peaks_by_lead=annotation_peaks,
            )

    def test_inventory_is_deterministic_and_hashes_every_regular_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "nested").mkdir()
            (root / "a.hea").write_bytes(b"header")
            (root / "nested" / "a.dat").write_bytes(b"signal")
            inventory = build_sha256_inventory(root)
            self.assertEqual([row["relative_path"] for row in inventory], ["a.hea", "nested/a.dat"])
            self.assertEqual(inventory[0]["sha256"], hashlib.sha256(b"header").hexdigest())
            json.dumps(inventory)

    def test_records_file_and_published_sha256s_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "data").mkdir()
            (root / "data" / "1.hea").write_bytes(b"one")
            (root / "data" / "2.hea").write_bytes(b"two")
            (root / "RECORDS").write_text("data/1\ndata/2\n", encoding="ascii")
            self.assertEqual(discover_ludb_records(root, expected_count=2), ["data/1", "data/2"])
            digest = hashlib.sha256(b"one").hexdigest()
            (root / "SHA256SUMS.txt").write_text(f"{digest}  data/1.hea\n", encoding="ascii")
            verified = verify_published_sha256s(root)
            self.assertEqual(verified["verified_file_count"], 1)
            (root / "data" / "1.hea").write_bytes(b"changed")
            with self.assertRaises(LUDBRecordError):
                verify_published_sha256s(root)

            (root / "RECORDS").write_text("../escape\ndata/2\n", encoding="ascii")
            with self.assertRaises(LUDBRecordError):
                discover_ludb_records(root, expected_count=2)


class TestLUDBEvaluation(unittest.TestCase):
    def test_m1_gate_requires_gross_average_and_count_limits(self):
        passing_gross = {"QTP": 1824, "QFN": 8, "QFP": 9, "qrs_se_percent": 99.56, "qrs_plus_p_percent": 99.50}
        passing_average = {"qrs_se_percent": 99.55, "qrs_plus_p_percent": 99.56}
        self.assertTrue(_m1_gate_passes(passing_gross, passing_average))
        for field, value in (("QFN", 10), ("QFP", 10), ("qrs_se_percent", 99.49), ("qrs_plus_p_percent", 99.49)):
            failing = dict(passing_gross)
            failing[field] = value
            self.assertFalse(_m1_gate_passes(failing, passing_average))
        for field in ("qrs_se_percent", "qrs_plus_p_percent"):
            failing_average = dict(passing_average)
            failing_average[field] = 99.49
            self.assertFalse(_m1_gate_passes(passing_gross, failing_average))

    def test_annotation_support_uses_exact_millisecond_bounds_inclusively(self):
        span = annotation_support_span([250, 500], sample_rate_hz=250, tolerance_ms=150.0)
        self.assertEqual(span, (212.5, 537.5))
        report = evaluate_record(
            "support-boundary",
            [250, 500],
            [212, 213, 250, 500, 537, 538],
            sample_rate_hz=250,
            learning_period_s=0,
            evaluation_span=span,
        )
        self.assertEqual((report["QTP"], report["QFN"], report["QFP"]), (2, 0, 2))

    def test_two_second_sqi_windows_select_three_leads_and_fuse_qrs(self):
        expected = [250, 500, 750, 1000, 1250, 1500, 1750, 2000, 2250]
        signals = {lead: [0] * 2500 for lead in CANONICAL_LEADS}
        signals["II"] = synthetic_qrs(expected, offset=0)
        signals["V1"] = synthetic_qrs([peak + 2 for peak in expected], offset=1)
        signals["V2"] = synthetic_qrs([peak - 2 for peak in expected], offset=2)
        float_result = select_and_fuse_record(signals, fixed=False)
        fixed_result = select_and_fuse_record(signals, fixed=True)
        self.assertEqual(float_result.peak_indices, expected)
        self.assertEqual(fixed_result.peak_indices, expected)
        self.assertEqual(float_result.peak_indices, fixed_result.peak_indices)
        self.assertEqual(len(float_result.windows), 5)
        self.assertTrue(all(window.status == "FULL_12_LEAD" for window in float_result.windows))
        self.assertTrue(all(set(window.selected_leads) == {"II", "V1", "V2"} for window in float_result.windows))

    def test_loaded_record_report_keeps_counts_mapping_error_and_diff(self):
        expected = [250, 500, 750, 1000, 1250, 1500, 1750, 2000, 2250]
        signals = {lead: [0] * 2500 for lead in CANONICAL_LEADS}
        signals["II"] = synthetic_qrs(expected, offset=0)
        signals["V1"] = synthetic_qrs([peak + 2 for peak in expected], offset=1)
        signals["V2"] = synthetic_qrs([peak - 2 for peak in expected], offset=2)
        report = evaluate_loaded_record(
            record_id="synthetic-ludb",
            signals_lsb_250=signals,
            reference_indices_250=expected,
            max_mapping_error_ms=2.0,
        )
        self.assertEqual(report["QTP"], len(expected))
        self.assertEqual(report["QFN"], 0)
        self.assertEqual(report["QFP"], 0)
        self.assertEqual(report["fixed_full"]["QTP"], len(expected))
        self.assertEqual(report["fixed_annotation_support"]["QTP"], len(expected))
        self.assertEqual(report["gate_scope"], "fixed_annotation_support")
        self.assertEqual(report["full_record_metrics_role"], "required_diagnostic")
        self.assertEqual(report["float_fixed_mismatch_count"], 0)
        self.assertEqual(report["max_mapping_error_ms"], 2.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
