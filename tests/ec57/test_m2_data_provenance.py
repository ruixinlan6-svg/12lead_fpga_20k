from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np


sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "train" / "ec57"))

from cache_provenance import CacheProvenanceError, validate_m2_cache_split, validate_patient_disjoint_splits

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools" / "remote"))
from audit_m2_cache import audit_npz
from audit_icentia_annotations import (
    build_patient_cohort,
    select_by_digest,
    select_readable_records,
    summarize_symbols,
)
from audit_icentia_duplicate_timestamps import find_same_sample_native_groups
from audit_icentia_signal_integrity import analyze_signal_integrity, extract_contiguous_runs
from build_finite_replacement_audit import select_first_valid_candidate
import prepare_icentia_native_cache as cache_builder
from prepare_icentia_native_cache import (
    NativeBeat,
    WFDB_DOWNLOAD_DB,
    build_record_examples,
    combined_record_sha256,
    compute_train_waveform_scale,
    finalize_split_arrays,
    normalize_native_beats_for_features,
    select_training_beats,
    source_relative_files,
)
from sqi import continuous_sqi_score_q15_fixed
from train.ec57.train_nv_remote import load_native_cache_splits


def valid_split(*, patients: tuple[str, ...] = ("p001", "p002")) -> dict[str, np.ndarray]:
    size = len(patients)
    return {
        "waveforms": np.zeros((size, 160), dtype=np.int8),
        "features": np.zeros((size, 4), dtype=np.int8),
        "labels": np.array([0, 1][:size], dtype=np.int64),
        "patient_ids": np.array(patients),
        "database": np.array(["Icentia11k"] * size),
        "database_version": np.array(["1.0"] * size),
        "record_ids": np.array([f"{patient}-r0" for patient in patients]),
        "sample_indices": np.arange(size, dtype=np.int64) + 100,
        "native_symbols": np.array(["N", "V"][:size]),
        "source_file_sha256": np.array(["a" * 64] * size),
    }


class TestM2DataProvenance(unittest.TestCase):
    def test_continuous_fixed_sqi_is_bounded_integer_and_distinguishes_waveform_shape(self):
        narrow = [0] * 500
        narrow[245:255] = [20, 40, 80, 120, 180, 180, 120, 80, 40, 20]
        broad = [int(80 * np.sin(2.0 * np.pi * index / 80.0)) for index in range(500)]
        narrow_score = continuous_sqi_score_q15_fixed(narrow)
        broad_score = continuous_sqi_score_q15_fixed(broad)
        self.assertIsInstance(narrow_score, int)
        self.assertGreaterEqual(narrow_score, 0)
        self.assertLessEqual(narrow_score, 32767)
        self.assertGreaterEqual(broad_score, 0)
        self.assertLessEqual(broad_score, 32767)
        self.assertNotEqual(narrow_score, broad_score)

    def test_training_loader_uses_frozen_three_way_native_splits_without_resplitting(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_dir = Path(temp_dir)
            expected_patients = {
                "train": ("p001", "p002"),
                "validation": ("p003",),
                "internal_test": ("p004",),
            }
            for split, patients in expected_patients.items():
                np.savez_compressed(cache_dir / f"{split}_beats.npz", **valid_split(patients=patients))
            loaded = load_native_cache_splits(cache_dir)
            self.assertEqual(set(loaded), set(expected_patients))
            for split, patients in expected_patients.items():
                self.assertEqual(set(loaded[split]["patient_ids"].tolist()), set(patients))

    def test_training_loader_rejects_old_two_file_cache(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_dir = Path(temp_dir)
            np.savez_compressed(cache_dir / "train_beats.npz", **valid_split())
            np.savez_compressed(cache_dir / "val_beats.npz", **valid_split(patients=("p003",)))
            with self.assertRaisesRegex(FileNotFoundError, "validation_beats"):
                load_native_cache_splits(cache_dir)

    def test_validation_only_loader_does_not_require_or_open_internal_test(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_dir = Path(temp_dir)
            np.savez_compressed(cache_dir / "train_beats.npz", **valid_split(patients=("p001",)))
            np.savez_compressed(cache_dir / "validation_beats.npz", **valid_split(patients=("p002",)))
            loaded = load_native_cache_splits(cache_dir, include_internal_test=False)
            self.assertEqual(set(loaded), {"train", "validation"})

    def test_wfdb_download_database_does_not_duplicate_version_component(self):
        self.assertEqual(WFDB_DOWNLOAD_DB, "icentia11k-continuous-ecg")

    def test_source_file_paths_and_combined_digest_are_canonical(self):
        self.assertEqual(
            source_relative_files("p00000", "p00000_s03"),
            [
                "p00/p00000/p00000_s03.atr",
                "p00/p00000/p00000_s03.dat",
                "p00/p00000/p00000_s03.hea",
            ],
        )
        hashes = {"b.dat": "b" * 64, "a.hea": "a" * 64}
        self.assertEqual(combined_record_sha256(hashes), combined_record_sha256(dict(reversed(list(hashes.items())))))
        self.assertEqual(len(combined_record_sha256(hashes)), 64)

    def test_complete_local_source_set_bypasses_download_but_missing_file_uses_original_call(self):
        relative_files = ["p00/p00001/a.atr", "p00/p00001/a.dat", "p00/p00001/a.hea"]
        with tempfile.TemporaryDirectory() as temp_dir:
            source_root = Path(temp_dir)
            for relative in relative_files:
                path = source_root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(relative.encode("ascii"))

            downloader = unittest.mock.Mock()
            complete = cache_builder.ensure_source_files(
                source_root, relative_files, downloader=downloader
            )
            self.assertEqual(complete["mode"], "existing_verified_later")
            self.assertEqual(complete["missing_before"], [])
            downloader.assert_not_called()

            (source_root / relative_files[1]).unlink()
            missing = cache_builder.ensure_source_files(
                source_root, relative_files, downloader=downloader
            )
            self.assertEqual(missing["mode"], "download_requested")
            self.assertEqual(missing["missing_before"], [relative_files[1]])
            downloader.assert_called_once_with(
                WFDB_DOWNLOAD_DB,
                str(source_root.resolve()),
                relative_files,
                keep_subdirs=True,
                overwrite=False,
            )

    def test_patient_coverage_accepts_only_train_q_only_absence(self):
        from audit_m2_patient_coverage import audit_patient_coverage

        annotation_audit = {
            "cohort": {
                "train": ["p1", "p2"],
                "validation": ["p3"],
                "internal_test": ["p4"],
            },
            "records": [
                {"split": "train", "patient_id": "p1", "native_beat_counts": {"N": 10, "V": 1}},
                {"split": "train", "patient_id": "p2", "native_beat_counts": {"Q": 12}},
                {"split": "validation", "patient_id": "p3", "native_beat_counts": {"N": 2}},
                {"split": "internal_test", "patient_id": "p4", "native_beat_counts": {"V": 2}},
            ],
        }
        report = audit_patient_coverage(
            annotation_audit,
            {
                "train": np.array(["p1"]),
                "validation": np.array(["p3"]),
                "internal_test": np.array(["p4"]),
            },
        )
        self.assertTrue(report["accepted"])
        self.assertEqual(report["splits"]["train"]["missing_patients"], ["p2"])
        self.assertEqual(
            report["splits"]["train"]["missing_patient_native_counts"]["p2"],
            {"N": 0, "Q": 12, "S": 0, "V": 0},
        )

    def test_patient_coverage_rejects_trainable_missing_unexpected_and_heldout_absence(self):
        from audit_m2_patient_coverage import audit_patient_coverage

        annotation_audit = {
            "cohort": {
                "train": ["p1", "p2"],
                "validation": ["p3"],
                "internal_test": ["p4"],
            },
            "records": [
                {"split": "train", "patient_id": "p1", "native_beat_counts": {"N": 2}},
                {"split": "train", "patient_id": "p2", "native_beat_counts": {"V": 1, "Q": 2}},
                {"split": "validation", "patient_id": "p3", "native_beat_counts": {"Q": 4}},
                {"split": "internal_test", "patient_id": "p4", "native_beat_counts": {"N": 2}},
            ],
        }
        report = audit_patient_coverage(
            annotation_audit,
            {
                "train": np.array(["p1", "unexpected"]),
                "validation": np.array([], dtype=str),
                "internal_test": np.array(["p4"]),
            },
        )
        self.assertFalse(report["accepted"])
        self.assertIn("unexpected", report["splits"]["train"]["unexpected_patients"])
        self.assertFalse(report["splits"]["train"]["missing_patients_q_only"])
        self.assertFalse(report["splits"]["validation"]["accepted"])

    def test_finalized_cache_uses_train_only_statistics_and_passes_provenance_contract(self):
        def example(patient: str, record: str, symbol: str, value: int, sample: int) -> dict[str, object]:
            return {
                "patient_id": patient,
                "record_id": record,
                "sample_index": sample,
                "native_symbol": symbol,
                "source_file_sha256": "a" * 64,
                "label": 1 if symbol == "V" else 0,
                "waveform": np.full(160, value, dtype=np.int16) + np.arange(160, dtype=np.int16),
                "raw_features": np.array(
                    [1.0 + value * 0.01, 40.0 + value, 1.0 + value * 0.02, 0.9 - value * 0.001],
                    dtype=np.float32,
                ),
            }

        examples = {
            "train": [example("p001", "r1", "N", 0, 100), example("p002", "r2", "V", 10, 200)],
            "validation": [example("p003", "r3", "N", 1000, 300)],
            "internal_test": [example("p004", "r4", "V", 2000, 400)],
        }
        arrays, normalization = finalize_split_arrays(examples)
        self.assertEqual(set(arrays), {"train", "validation", "internal_test"})
        self.assertEqual(arrays["train"]["waveforms"].dtype, np.int8)
        self.assertEqual(arrays["train"]["features"].dtype, np.int8)
        self.assertLess(normalization["waveform_scale_ref_lsb"], 1000.0)
        for split, data in arrays.items():
            validate_m2_cache_split(data, split_name=split)
        validate_patient_disjoint_splits(arrays)

    def test_training_selection_keeps_all_v_and_s_and_caps_total_negatives_four_to_one(self):
        beats = [NativeBeat("p1", "r1", index, "N", "a" * 64) for index in range(100, 120)]
        beats += [NativeBeat("p1", "r1", 200, "S", "a" * 64)]
        beats += [NativeBeat("p1", "r1", 300, "V", "a" * 64), NativeBeat("p2", "r2", 400, "V", "b" * 64)]
        selected = select_training_beats(beats, max_negative_per_positive=4)
        counts = {symbol: sum(beat.native_symbol == symbol for beat in selected) for symbol in ("N", "S", "V")}
        self.assertEqual(counts, {"N": 7, "S": 1, "V": 2})
        self.assertEqual(selected, select_training_beats(list(reversed(beats)), max_negative_per_positive=4))

    def test_train_waveform_scale_uses_abs_deviation_percentile_and_floor(self):
        quiet = np.zeros((4, 160), dtype=np.int16)
        self.assertEqual(compute_train_waveform_scale(quiet), 20.0)
        loud = np.zeros((2, 160), dtype=np.int16)
        loud[:, 64] = 1000
        self.assertGreater(compute_train_waveform_scale(loud), 20.0)

    def test_record_examples_preserve_native_indices_labels_and_finite_causal_features(self):
        signal = np.zeros(700, dtype=np.int16)
        for sample, amplitude in ((100, 200), (250, -300), (500, 400)):
            signal[sample - 1 : sample + 2] = (amplitude // 2, amplitude, amplitude // 2)
        beats = [
            NativeBeat("p1", "r1", 100, "N", "a" * 64),
            NativeBeat("p1", "r1", 250, "V", "a" * 64),
            NativeBeat("p1", "r1", 500, "S", "a" * 64),
        ]
        examples = build_record_examples(signal, beats, selected_keys={beat.key for beat in beats})
        self.assertEqual([row["sample_index"] for row in examples], [100, 250, 500])
        self.assertEqual([row["label"] for row in examples], [0, 1, 0])
        self.assertTrue(all(row["waveform"].shape == (160,) for row in examples))
        self.assertTrue(all(np.isfinite(row["raw_features"]).all() for row in examples))

    def test_record_examples_compute_sqi_only_for_emitted_examples_without_changing_state(self):
        signal = np.zeros(700, dtype=np.int16)
        for sample, amplitude in ((100, 200), (180, 800), (400, 100), (500, 400)):
            signal[sample - 1 : sample + 2] = (amplitude // 2, amplitude, amplitude // 2)
        beats = [
            NativeBeat("p1", "r1", 100, "N", "a" * 64),
            NativeBeat("p1", "r1", 180, "Q", "a" * 64),
            NativeBeat("p1", "r1", 400, "N", "a" * 64),
            NativeBeat("p1", "r1", 500, "V", "a" * 64),
        ]
        selected_keys = {beats[0].key, beats[-1].key}

        with patch(
            "prepare_icentia_native_cache.continuous_sqi_score_q15_fixed",
            wraps=continuous_sqi_score_q15_fixed,
        ) as score:
            examples = build_record_examples(signal, beats, selected_keys=selected_keys)

        self.assertEqual(score.call_count, 2)
        self.assertEqual([row["sample_index"] for row in examples], [100, 500])
        np.testing.assert_array_equal(
            examples[0]["raw_features"],
            np.array([1.0, 12.0, 1.0, 0.9494003057479858], dtype=np.float32),
        )
        np.testing.assert_array_equal(
            examples[1]["raw_features"],
            np.array([1.0, 12.0, 0.6666666865348816, 0.9371623992919922], dtype=np.float32),
        )

    def test_duplicate_q_only_marker_is_collapsed_for_features_without_mutating_raw_beats(self):
        signal = np.zeros(700, dtype=np.int16)
        for sample in (100, 250, 500):
            signal[sample - 1 : sample + 2] = (100, 200, 100)
        single_q = [
            NativeBeat("p1", "r1", 100, "N", "a" * 64),
            NativeBeat("p1", "r1", 250, "Q", "a" * 64),
            NativeBeat("p1", "r1", 500, "V", "a" * 64),
        ]
        duplicate_q = single_q[:2] + [single_q[1]] + single_q[2:]
        selected_keys = {single_q[0].key, single_q[-1].key}

        normalized = normalize_native_beats_for_features(duplicate_q)
        expected = build_record_examples(signal, single_q, selected_keys=selected_keys)
        actual = build_record_examples(signal, duplicate_q, selected_keys=selected_keys)

        self.assertEqual(sum(beat.native_symbol == "Q" for beat in duplicate_q), 2)
        self.assertEqual(sum(beat.native_symbol == "Q" for beat in normalized), 1)
        self.assertEqual([row["sample_index"] for row in actual], [100, 500])
        np.testing.assert_array_equal(actual[0]["raw_features"], expected[0]["raw_features"])
        np.testing.assert_array_equal(actual[1]["raw_features"], expected[1]["raw_features"])

    def test_duplicate_timestamp_containing_trainable_symbol_fails_closed(self):
        for symbols in (("N", "N"), ("Q", "V"), ("S", "V")):
            beats = [NativeBeat("p1", "r1", 100, symbol, "a" * 64) for symbol in symbols]
            with self.subTest(symbols=symbols), self.assertRaisesRegex(ValueError, "ambiguous native beat"):
                normalize_native_beats_for_features(beats)

    def test_duplicate_timestamp_audit_lists_q_only_and_ambiguous_groups(self):
        groups = find_same_sample_native_groups(
            [100, 200, 200, 300, 300, 400],
            ["N", "Q", "Q", "N", "V", "+"],
        )
        self.assertEqual(
            groups,
            [
                {"sample_index": 200, "symbols": ["Q", "Q"], "allowed_q_only": True},
                {"sample_index": 300, "symbols": ["N", "V"], "allowed_q_only": False},
            ],
        )

    def test_signal_integrity_extracts_contiguous_missing_runs_without_mutation(self):
        indices = np.array([8, 2, 3, 3, 10, 9, 20], dtype=np.int64)
        before = indices.copy()
        self.assertEqual(
            extract_contiguous_runs(indices),
            [
                {"start": 2, "stop_exclusive": 4, "length": 2},
                {"start": 8, "stop_exclusive": 11, "length": 3},
                {"start": 20, "stop_exclusive": 21, "length": 1},
            ],
        )
        np.testing.assert_array_equal(indices, before)

    def test_signal_integrity_preserves_sentinel_and_half_open_feature_support_boundaries(self):
        physical = np.zeros(700, dtype=np.float64)
        digital = np.zeros(700, dtype=np.int32)
        physical[[95, 96, 595, 596]] = np.nan
        digital[[95, 96, 595, 596]] = -32768
        physical_before = physical.copy()
        digital_before = digital.copy()

        report = analyze_signal_integrity(
            physical,
            digital,
            beat_samples=[500],
            beat_symbols=["V"],
        )

        self.assertEqual(report["nonfinite_sample_count"], 4)
        self.assertEqual(report["digital_values_at_nonfinite"], [-32768])
        self.assertEqual(report["affected_beats"], [{"sample_index": 500, "symbol": "V"}])
        self.assertEqual(report["affected_native_symbol_counts"], {"V": 1})
        self.assertEqual(report["missing_runs"][0], {"start": 95, "stop_exclusive": 97, "length": 2})
        np.testing.assert_array_equal(physical, physical_before)
        np.testing.assert_array_equal(digital, digital_before)

        left_only = np.zeros(700, dtype=np.float64)
        left_only[96] = np.nan
        self.assertEqual(
            analyze_signal_integrity(left_only, digital, beat_samples=[500], beat_symbols=["N"])[
                "affected_native_symbol_counts"
            ],
            {"N": 1},
        )
        outside = np.zeros(700, dtype=np.float64)
        outside[[95, 596]] = np.nan
        self.assertEqual(
            analyze_signal_integrity(outside, digital, beat_samples=[500], beat_symbols=["N"])[
                "affected_native_symbol_counts"
            ],
            {},
        )

    def test_finite_replacement_selection_is_deterministic_excludes_selected_and_logs_failures(self):
        available = ["s5", "s2", "s4", "s1", "s3"]
        ordered = select_by_digest(available, len(available))
        already_selected = {ordered[0]}
        rejected = {ordered[1]}

        def validate(record_id: str) -> dict[str, str]:
            if record_id in rejected:
                raise ValueError(f"non-finite {record_id}")
            return {"record_id": record_id, "status": "finite"}

        chosen, payload, attempts = select_first_valid_candidate(
            available,
            already_selected=already_selected,
            validate=validate,
        )
        reversed_result = select_first_valid_candidate(
            list(reversed(available)),
            already_selected=already_selected,
            validate=validate,
        )

        self.assertEqual(chosen, ordered[2])
        self.assertEqual(payload, {"record_id": ordered[2], "status": "finite"})
        self.assertEqual((chosen, payload, attempts), reversed_result)
        self.assertEqual(
            attempts,
            [
                {"record_id": ordered[1], "accepted": False, "reason": f"ValueError('non-finite {ordered[1]}')"},
                {"record_id": ordered[2], "accepted": True, "reason": "finite signal and valid annotation"},
            ],
        )
        self.assertNotIn(ordered[0], [attempt["record_id"] for attempt in attempts])

    def test_finite_replacement_selection_fails_when_no_candidate_is_valid(self):
        def reject(record_id: str) -> dict[str, str]:
            raise ValueError(f"invalid {record_id}")

        with self.assertRaisesRegex(ValueError, "no valid finite replacement"):
            select_first_valid_candidate(["s1", "s2"], already_selected={"s1"}, validate=reject)

    def test_annotation_audit_selection_is_deterministic_and_split_stratified(self):
        patients = [f"p{index:05d}" for index in range(200)]
        forward = build_patient_cohort(patients, patients_per_split=3)
        reverse = build_patient_cohort(list(reversed(patients)), patients_per_split=3)
        self.assertEqual(forward, reverse)
        self.assertEqual({key: len(value) for key, value in forward.items()}, {"train": 3, "validation": 3, "internal_test": 3})
        self.assertEqual(select_by_digest(["s2", "s1", "s3"], 2), select_by_digest(["s3", "s2", "s1"], 2))

    def test_annotation_cohort_supports_split_specific_patient_counts(self):
        patients = [f"p{index:05d}" for index in range(1000)]
        cohort = build_patient_cohort(
            patients,
            patients_per_split={"train": 25, "validation": 4, "internal_test": 4},
        )
        self.assertEqual(
            {split: len(values) for split, values in cohort.items()},
            {"train": 25, "validation": 4, "internal_test": 4},
        )

    def test_annotation_fallback_is_deterministic_and_records_unreadable_candidates(self):
        available = ["s5", "s2", "s4", "s1", "s3"]
        ordered = select_by_digest(available, len(available))
        failed = {ordered[0], ordered[2]}

        def read_annotation(record_id: str) -> str:
            if record_id in failed:
                raise FileNotFoundError(f"missing {record_id}.atr")
            return f"annotation:{record_id}"

        selected, exclusions = select_readable_records(
            available,
            count=3,
            read_annotation=read_annotation,
            split="train",
            patient_id="p09486",
        )
        reversed_selected, reversed_exclusions = select_readable_records(
            list(reversed(available)),
            count=3,
            read_annotation=read_annotation,
            split="train",
            patient_id="p09486",
        )

        expected_records = [record for record in ordered if record not in failed][:3]
        self.assertEqual([record for record, _ in selected], expected_records)
        self.assertEqual(selected, reversed_selected)
        self.assertEqual(exclusions, reversed_exclusions)
        self.assertEqual([row["record_id"] for row in exclusions], [ordered[0], ordered[2]])
        self.assertTrue(all(row["split"] == "train" for row in exclusions))
        self.assertTrue(all(row["patient_id"] == "p09486" for row in exclusions))
        self.assertTrue(all("FileNotFoundError" in row["error"] for row in exclusions))

    def test_annotation_audit_separates_native_beats_from_other_markers(self):
        summary = summarize_symbols(["N", "+", "V", "Q", "S", "N", "x"])
        self.assertEqual(summary["native_beat_counts"], {"N": 2, "Q": 1, "S": 1, "V": 1})
        self.assertEqual(summary["other_symbol_counts"], {"+": 1, "x": 1})

    def test_npz_audit_reports_rejection_and_source_counts_without_mutation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "old.npz"
            np.savez_compressed(
                path,
                waveforms=np.zeros((2, 160), dtype=np.int8),
                features=np.zeros((2, 4), dtype=np.int8),
                labels=np.array([0, 1]),
                patient_ids=np.array(["p1", "p2"]),
                sources=np.array(["mitdb", "icentia11k"]),
            )
            before = path.read_bytes()
            report = audit_npz(path, split_name="train")
            self.assertFalse(report["accepted"])
            self.assertEqual(report["source_counts"], {"icentia11k": 1, "mitdb": 1})
            self.assertIn("missing required provenance fields", report["error"])
            self.assertEqual(path.read_bytes(), before)

    def test_contract_valid_native_symbol_cache_is_accepted(self):
        result = validate_m2_cache_split(valid_split(), split_name="train")
        self.assertEqual(result["sample_count"], 2)
        self.assertEqual(result["native_symbol_counts"], {"N": 1, "V": 1})

    def test_old_heuristic_cache_without_native_annotations_is_rejected(self):
        old_cache = {
            "waveforms": np.zeros((2, 160), dtype=np.int8),
            "features": np.zeros((2, 4), dtype=np.int8),
            "labels": np.array([0, 1]),
            "patient_ids": np.array(["segment-a", "segment-b"]),
        }
        with self.assertRaisesRegex(CacheProvenanceError, "missing required provenance fields"):
            validate_m2_cache_split(old_cache, split_name="train")

    def test_locked_or_non_icentia_source_is_rejected(self):
        invalid = valid_split()
        invalid["database"] = np.array(["MIT-BIH Arrhythmia", "Icentia11k"])
        with self.assertRaisesRegex(CacheProvenanceError, "Icentia11k"):
            validate_m2_cache_split(invalid, split_name="train")

    def test_native_symbol_mapping_cannot_be_silently_changed(self):
        invalid = valid_split()
        invalid["labels"] = np.array([1, 0])
        with self.assertRaisesRegex(CacheProvenanceError, "native symbol mapping"):
            validate_m2_cache_split(invalid, split_name="train")

    def test_q_must_be_excluded_from_loss_cache(self):
        invalid = valid_split()
        invalid["native_symbols"] = np.array(["Q", "V"])
        with self.assertRaisesRegex(CacheProvenanceError, "Q must be counted then excluded"):
            validate_m2_cache_split(invalid, split_name="train")

    def test_patient_overlap_between_splits_is_rejected(self):
        splits = {
            "train": valid_split(patients=("p001",)),
            "validation": valid_split(patients=("p002",)),
            "internal_test": valid_split(patients=("p001",)),
        }
        with self.assertRaisesRegex(CacheProvenanceError, "patient overlap"):
            validate_patient_disjoint_splits(splits)


if __name__ == "__main__":
    unittest.main(verbosity=2)
