from __future__ import annotations

import csv
import json
import math
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "train" / "ec57"))

from qrs_detector import (
    QRS_CONFIG,
    QRS_Candidate,
    QRSReferenceError,
    StreamIntegrityError,
    apply_refractory_and_searchback_fixed,
    apply_refractory_and_searchback_float,
    detect_qrs_fixed,
    detect_qrs_float,
    fuse_qrs_leads,
    saturate_int40,
    validate_sample_index_stream,
)
from evaluate_qrs import evaluate_records, generate_reference_evidence
from sqi import (
    evaluate_sqi_fixed,
    evaluate_sqi_float,
    select_valid_leads_fixed,
    select_valid_leads_float,
)


def synthetic_qrs(peaks, length=1000):
    signal = [0] * length
    for peak in peaks:
        for offset, value in ((-3, 80), (-2, 220), (-1, 700), (0, 1200), (1, 700), (2, 220), (3, 80)):
            signal[peak + offset] = value
    return signal


class TestQRSReference(unittest.TestCase):
    def test_float_and_fixed_qrs_timestamps_are_exact_on_synthetic_pulses(self):
        expected = [200, 500, 800]
        signal = synthetic_qrs(expected)
        float_result = detect_qrs_float(signal, sample_rate_hz=250)
        fixed_result = detect_qrs_fixed(signal, sample_rate_hz=250)
        self.assertEqual(float_result.peak_indices, expected)
        self.assertEqual(fixed_result.peak_indices, expected)
        self.assertEqual(float_result.peak_indices, fixed_result.peak_indices)

    def test_adaptive_energy_qrs_handles_baseline_noise_and_amplitude_change(self):
        expected = [250, 500, 750]
        signal = [
            int(round(700 * math.sin(2 * math.pi * 0.5 * index / 250) + 15 * math.sin(2 * math.pi * 37 * index / 250)))
            for index in range(1000)
        ]
        for peak, scale in zip(expected, (1200, 450, 850)):
            for offset, value in ((-3, 80), (-2, 220), (-1, 700), (0, 1200), (1, 700), (2, 220), (3, 80)):
                signal[peak + offset] += value * scale // 1200
        float_result = detect_qrs_float(signal)
        fixed_result = detect_qrs_fixed(signal)
        self.assertEqual(float_result.peak_indices, expected)
        self.assertEqual(fixed_result.peak_indices, expected)
        self.assertTrue(all(candidate.strength > 0 for candidate in float_result.candidates))

    def test_fixed_filter_accumulator_has_explicit_signed_40_bit_saturation(self):
        self.assertEqual(saturate_int40(1 << 50), (1 << 39) - 1)
        self.assertEqual(saturate_int40(-(1 << 50)), -(1 << 39))
        self.assertEqual(saturate_int40(123), 123)

    def test_two_hundred_ms_refractory_period_suppresses_early_duplicate(self):
        signal = synthetic_qrs([200, 240, 320])
        result = detect_qrs_fixed(signal, sample_rate_hz=250)
        self.assertEqual(result.peak_indices, [200, 320])

    def test_searchback_accepts_a_weak_candidate_after_long_gap(self):
        candidates = [
            QRS_Candidate(index=200, strength=1.0, primary=True),
            QRS_Candidate(index=500, strength=0.20, primary=False),
            QRS_Candidate(index=800, strength=1.0, primary=True),
        ]
        float_result = apply_refractory_and_searchback_float(candidates, rr_history=[300, 300, 300])
        fixed_result = apply_refractory_and_searchback_fixed(candidates, rr_history=[300, 300, 300])
        self.assertEqual(float_result, [200, 500, 800])
        self.assertEqual(float_result, fixed_result)

    def test_missing_duplicate_and_out_of_order_samples_fail_closed(self):
        for indices, code in (
            ([0, 1, 3], "MISSING_SAMPLE"),
            ([0, 1, 1], "DUPLICATE_SAMPLE"),
            ([0, 1, 0], "OUT_OF_ORDER_SAMPLE"),
        ):
            with self.subTest(code=code):
                with self.assertRaises(StreamIntegrityError) as context:
                    validate_sample_index_stream(indices)
                self.assertEqual(context.exception.code, code)

    def test_sqi_float_and_fixed_cover_flatline_saturation_and_impulsive_noise(self):
        flatline = [0] * 500
        saturated = [0] * 500
        saturated[0:3] = [32767, 32767, 32767]
        impulsive = [0] * 500
        for index in range(10, 31):
            impulsive[index] = 500 if index % 2 == 0 else 0
        for samples, reason in ((flatline, "FLATLINE"), (saturated, "SATURATION"), (impulsive, "IMPULSIVE_NOISE")):
            with self.subTest(reason=reason):
                float_quality = evaluate_sqi_float(samples)
                fixed_quality = evaluate_sqi_fixed(samples)
                self.assertFalse(float_quality.valid)
                self.assertFalse(fixed_quality.valid)
                self.assertIn(reason, float_quality.reason_codes)
                self.assertIn(reason, fixed_quality.reason_codes)

    def test_lead_dropout_reports_degraded_or_signal_loss(self):
        valid = [(index % 100) - 50 for index in range(1000)]
        lead_samples = {"II": valid, "V1": [0] * 1000, "V2": [0] * 1000}
        float_selection = select_valid_leads_float(lead_samples)
        fixed_selection = select_valid_leads_fixed(lead_samples)
        self.assertEqual(float_selection.status, "DEGRADED_ONE_LEAD")
        self.assertEqual(float_selection.selected_leads, ["II"])
        self.assertEqual(float_selection.status, fixed_selection.status)
        self.assertEqual(select_valid_leads_fixed({"II": [0] * 500}).status, "SIGNAL_LOSS")

    def test_sqi_requires_a_complete_five_hundred_sample_window(self):
        with self.assertRaises(ValueError):
            evaluate_sqi_fixed([0] * 499)
        with self.assertRaises(ValueError):
            evaluate_sqi_float([0.0] * 499)

    def test_three_lead_two_of_three_vote_is_inclusive_at_eighty_ms(self):
        fused = fuse_qrs_leads(
            {"II": [100, 300], "V1": [119, 319], "V2": [120, 320]},
            ["II", "V1", "V2"],
        )
        self.assertEqual(fused.status, "FULL_12_LEAD")
        self.assertEqual(fused.peak_indices, [119, 319])
        rejected = fuse_qrs_leads({"II": [100], "V1": [121], "V2": []}, ["II", "V1", "V2"])
        self.assertEqual(rejected.peak_indices, [])

    def test_one_lead_degrades_and_zero_leads_signal_loss(self):
        degraded = fuse_qrs_leads({"II": [100, 300]}, ["II"])
        self.assertEqual(degraded.status, "DEGRADED_ONE_LEAD")
        self.assertEqual(degraded.peak_indices, [100, 300])
        loss = fuse_qrs_leads({}, [])
        self.assertEqual(loss.status, "SIGNAL_LOSS")
        self.assertEqual(loss.peak_indices, [])

    def test_qrs_evaluator_keeps_raw_counts_and_na_denominators(self):
        report = evaluate_records(
            [("record-a", [0, 1000], [0, 1010]), ("record-b", [0], [])],
            sample_rate_hz=250,
            learning_period_s=0,
        )
        self.assertEqual(report["gross"]["QTP"], 2)
        self.assertEqual(report["gross"]["QFN"], 1)
        self.assertEqual(report["gross"]["QFP"], 0)
        self.assertAlmostEqual(report["gross"]["qrs_se_percent"], 2 / 3 * 100)
        empty = evaluate_records([("empty", [], [])], sample_rate_hz=250, learning_period_s=0)
        self.assertEqual(empty["gross"]["qrs_se_percent"], "N/A")

    def test_evidence_package_marks_ludb_not_evaluated_without_database_access(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            files = generate_reference_evidence(Path(temp_dir), run_id="m1-test")
            names = {path.name for path in files}
            self.assertTrue({
                "config.json",
                "manifest_hashes.json",
                "ludb_per_record_metrics.csv",
                "failed_samples.csv",
                "float_fixed_qrs_diff.json",
            }.issubset(names))
            manifest = json.loads((Path(temp_dir) / "manifest_hashes.json").read_text(encoding="utf-8"))
            self.assertFalse(manifest["database_accessed"])
            with (Path(temp_dir) / "ludb_per_record_metrics.csv").open(encoding="utf-8", newline="") as handle:
                row = next(csv.DictReader(handle))
            self.assertEqual(row["status"], "not_evaluated")

    def test_evidence_is_derived_by_executing_registry_detector_and_evaluator(self):
        with tempfile.TemporaryDirectory() as first_dir, tempfile.TemporaryDirectory() as second_dir:
            generate_reference_evidence(Path(first_dir), run_id="m1-derived-a", synthetic_peaks=(200, 500, 800))
            generate_reference_evidence(Path(second_dir), run_id="m1-derived-b", synthetic_peaks=(220, 520, 820))
            first_diff = json.loads((Path(first_dir) / "float_fixed_qrs_diff.json").read_text(encoding="utf-8"))
            second_diff = json.loads((Path(second_dir) / "float_fixed_qrs_diff.json").read_text(encoding="utf-8"))
            self.assertEqual(first_diff["float_peak_indices"], [200, 500, 800])
            self.assertEqual(second_diff["float_peak_indices"], [220, 520, 820])
            self.assertNotEqual(first_diff["float_peak_indices"], second_diff["float_peak_indices"])
            summary = json.loads((Path(first_dir) / "summary.json").read_text(encoding="utf-8"))
            self.assertTrue(summary["registry_executed"])
            self.assertTrue(summary["detector_executed"])
            self.assertTrue(summary["evaluator_executed"])
            self.assertEqual(summary["patient_leakage_count"], 0)

    def test_fixed_qrs_energy_is_nonzero_on_realistic_amplitude_signals(self):
        from qrs_detector import qrs_energy_fixed, qrs_energy_float, qrs_filter_fixed, qrs_filter_float
        # Realistic small to moderate amplitude ECG signal: 50..200 LSB (0.25..1.0 mV)
        signal = [20] * 50 + [150] * 5 + [-80] * 5 + [20] * 50
        filt_float = qrs_filter_float(signal)
        filt_fixed = qrs_filter_fixed(signal)
        self.assertGreater(max(filt_fixed), 0, "Fixed filter output must not be truncated to 0")
        self.assertLess(min(filt_fixed), 0, "Fixed filter output must swing negative")
        energy_float = qrs_energy_float(signal)
        energy_fixed = qrs_energy_fixed(signal)
        self.assertGreater(max(energy_fixed), 0, "Fixed MWI energy must be non-zero on realistic ECG")
        self.assertAlmostEqual(max(energy_fixed) / max(energy_float), 1.0, delta=0.20)

    def test_float_and_fixed_per_lead_candidates_and_fused_peaks_match(self):
        expected = [250, 500, 750]
        signal = synthetic_qrs(expected)
        float_res = detect_qrs_float(signal)
        fixed_res = detect_qrs_fixed(signal)
        self.assertEqual(float_res.peak_indices, fixed_res.peak_indices)
        self.assertEqual(len(float_res.candidates), len(fixed_res.candidates))
        for fc, xc in zip(float_res.candidates, fixed_res.candidates):
            self.assertEqual(fc.index, xc.index)
            self.assertEqual(fc.primary, xc.primary)
            self.assertGreater(xc.strength, 0)

    def test_prefix_invariance_streaming_qrs(self):
        from qrs_detector import CausalPureIntegerQRSDetector
        signal = synthetic_qrs([250, 500, 750, 1000], length=1200)
        det = CausalPureIntegerQRSDetector()
        # Feed first 600 samples
        peaks_at_600 = det.feed_chunk(signal[:600])
        # Feed remaining 600 samples
        peaks_at_1200 = det.feed_chunk(signal[600:])
        all_peaks = peaks_at_600 + peaks_at_1200
        # Prefix invariance: peaks emitted during first 600 samples must be exact prefix of final peaks
        self.assertEqual(all_peaks[:len(peaks_at_600)], peaks_at_600)
        self.assertEqual(det.accepted_peaks, [250, 500, 750, 1000])

    def test_chunk_streaming_equivalence(self):
        from qrs_detector import CausalPureIntegerQRSDetector, detect_qrs_fixed
        signal = synthetic_qrs([250, 500, 750, 1000], length=1200)
        batch_peaks = detect_qrs_fixed(signal).peak_indices

        # Test chunk sizes: 1, 10, 50, 500
        for chunk_size in (1, 10, 50, 500):
            det = CausalPureIntegerQRSDetector()
            chunk_peaks = []
            for start in range(0, len(signal), chunk_size):
                chunk = signal[start : start + chunk_size]
                chunk_peaks.extend(det.feed_chunk(chunk))
            self.assertEqual(chunk_peaks, batch_peaks, f"Mismatch with chunk_size={chunk_size}")
            self.assertEqual(det.get_result().peak_indices, batch_peaks)

    def test_fixed_paths_fail_closed_on_float_and_bool_inputs(self):
        from qrs_detector import CausalPureIntegerQRSDetector, qrs_energy_fixed, qrs_filter_fixed

        # Fixed detector must reject floating-point samples
        with self.assertRaises(QRSReferenceError):
            detect_qrs_fixed([1.0, 2.0, 3.0, 4.0, 5.0])
        with self.assertRaises(QRSReferenceError):
            detect_qrs_fixed([100, 200, 300.5, 400, 500])
        with self.assertRaises(QRSReferenceError):
            detect_qrs_fixed([True, False, True, False, True])

        # Detector step must reject float and bool
        det = CausalPureIntegerQRSDetector()
        with self.assertRaises(QRSReferenceError):
            det.step(1.5)
        with self.assertRaises(QRSReferenceError):
            det.step(True)
        with self.assertRaises(QRSReferenceError):
            det.step("invalid")

        # Fixed filter and energy must reject float and bool
        with self.assertRaises(QRSReferenceError):
            qrs_filter_fixed([1.0, 2.0, 3.0, 4.0, 5.0])
        with self.assertRaises(QRSReferenceError):
            qrs_filter_fixed([True, False])
        with self.assertRaises(QRSReferenceError):
            qrs_energy_fixed([1.0, 2.0, 3.0, 4.0, 5.0])
        with self.assertRaises(QRSReferenceError):
            qrs_energy_fixed([True, False, True, False, True])

        # Chunk API must not silently coerce float/bool values via int(...).
        chunk_det = CausalPureIntegerQRSDetector()
        with self.assertRaises(QRSReferenceError):
            chunk_det.feed_chunk([0, 1.25, 0])
        with self.assertRaises(QRSReferenceError):
            chunk_det.feed_chunk([0, True, 0])

    def test_searchback_and_current_primary_are_both_emitted_without_overwrite(self):
        from qrs_detector import CausalPureIntegerQRSDetector, QRS_Candidate

        detector = CausalPureIntegerQRSDetector()
        detector.sample_idx = 633
        detector.accepted_peaks = [100, 300]
        detector.last_peak_sample = 300
        detector.rr_history = [200]
        detector.signal_level = 100
        detector.noise_level = 1
        detector.candidates = [QRS_Candidate(index=500, strength=50, primary=False)]

        # The same input clock triggers the long-gap searchback and a new
        # primary local maximum. Both committed events must reach the caller.
        detector.mwi_0 = 1000
        detector.mwi_1 = 0
        detector.mwi_2 = 0
        detector.mwi_sum = 0
        detector.mwi_buf = [0] * 30
        detector.raw_buf = [0] * 64

        emitted = detector.feed_chunk([0, 0])
        result = detector.get_result()

        self.assertEqual(emitted, [500, 587])
        self.assertEqual(result.peak_indices[-2:], [500, 587])
        self.assertEqual(emitted, result.peak_indices[2:])

    def test_prefix_invariance_independent_runs_on_diverse_waveforms(self):
        from qrs_detector import CausalPureIntegerQRSDetector

        # Test across multiple deterministic waveform patterns
        waveforms = [
            synthetic_qrs([200, 450, 700, 950, 1200, 1450], length=1600),
            [
                int(round(600 * math.sin(2 * math.pi * 0.3 * i / 250) + (1200 if i in (220, 500, 780, 1100, 1380) else 0)))
                for i in range(1500)
            ],
        ]
        for signal in waveforms:
            cutoffs = [150, 300, 480, 650, 800, 1050, 1300, 1500]
            # Run a reference detector on full signal, recording emitted peaks incrementally
            full_det = CausalPureIntegerQRSDetector()
            emitted_up_to_k: dict[int, list[int]] = {}
            running_emitted = []
            for sample_idx, sample in enumerate(signal):
                res = full_det.step(sample)
                if res is not None:
                    running_emitted.append(res)
                if (sample_idx + 1) in cutoffs:
                    emitted_up_to_k[sample_idx + 1] = list(running_emitted)

            # For each cutoff, run an independent detector from scratch on prefix only
            for k in cutoffs:
                if k > len(signal):
                    continue
                prefix_det = CausalPureIntegerQRSDetector()
                prefix_peaks = prefix_det.feed_chunk(signal[:k])
                self.assertEqual(
                    prefix_peaks,
                    emitted_up_to_k[k],
                    f"Prefix run on first {k} samples does not match full run prefix",
                )
                self.assertEqual(
                    prefix_det.get_result().peak_indices,
                    emitted_up_to_k[k],
                    f"Result peak indices on prefix {k} do not match",
                )

    def test_arbitrary_chunk_streaming_equivalence_diverse_signals(self):
        from qrs_detector import CausalPureIntegerQRSDetector, detect_qrs_fixed

        # Signal with multiple beats, noise, and baseline drift
        signal = [
            int(round(400 * math.sin(2 * math.pi * 0.4 * i / 250) + 20 * math.cos(2 * math.pi * 15 * i / 250)))
            for i in range(2000)
        ]
        peaks = [200, 450, 700, 950, 1200, 1500, 1750]
        pulse = ((-3, 80), (-2, 220), (-1, 700), (0, 1200), (1, 700), (2, 220), (3, 80))
        for p in peaks:
            for delta, val in pulse:
                signal[p + delta] += val

        batch_peaks = detect_qrs_fixed(signal).peak_indices

        # Test various regular and irregular chunk patterns
        chunk_patterns = [
            [1] * len(signal),  # Single-sample streaming
            [2] * (len(signal) // 2),
            [3] * (len(signal) // 3) + [len(signal) % 3],
            [7] * (len(signal) // 7) + [len(signal) % 7],
            [13] * (len(signal) // 13) + [len(signal) % 13],
            [29] * (len(signal) // 29) + [len(signal) % 29],
            [50] * (len(signal) // 50),
            [500] * (len(signal) // 500),
            # Irregular / alternating chunk sizes
            [5, 17, 33, 1, 100, 50, 2, 7, 85, 200, 500, len(signal) - 1000],
        ]
        for pattern in chunk_patterns:
            det = CausalPureIntegerQRSDetector()
            collected_peaks = []
            idx = 0
            for chunk_len in pattern:
                if chunk_len <= 0 or idx >= len(signal):
                    continue
                chunk = signal[idx : idx + chunk_len]
                collected_peaks.extend(det.feed_chunk(chunk))
                idx += chunk_len
            if idx < len(signal):
                collected_peaks.extend(det.feed_chunk(signal[idx:]))
            self.assertEqual(collected_peaks, batch_peaks, f"Mismatch with chunk pattern {pattern[:5]}...")
            self.assertEqual(det.get_result().peak_indices, batch_peaks)

    def test_causal_streaming_searchback_recovers_subthreshold_beat(self):
        from qrs_detector import CausalPureIntegerQRSDetector

        # Primary beats at 200 and 450 (RR = 250 samples = 1000 ms)
        # Followed by a sub-threshold beat at 650 (gap = 550 > 1.66 * 250 = 415 samples)
        # Followed by normal beat at 1000
        signal = [0] * 1200
        pulse_strong = ((-3, 80), (-2, 220), (-1, 700), (0, 1200), (1, 700), (2, 220), (3, 80))
        pulse_weak = ((-3, 10), (-2, 25), (-1, 75), (0, 140), (1, 75), (2, 25), (3, 10))

        for p in (200, 450, 1000):
            for delta, val in pulse_strong:
                signal[p + delta] += val
        for delta, val in pulse_weak:
            signal[650 + delta] += val

        det = CausalPureIntegerQRSDetector()
        emitted = det.feed_chunk(signal)
        result = det.get_result()

        # The sub-threshold beat at 650 must be recovered via searchback
        self.assertIn(650, result.peak_indices, "Searchback must recover the sub-threshold beat at 650")
        self.assertIn(650, result.searchback_indices, "Searchback indices must record 650")
        self.assertEqual(emitted, result.peak_indices)

    def test_output_irrevocability_in_streaming(self):
        from qrs_detector import CausalPureIntegerQRSDetector

        signal = synthetic_qrs([200, 450, 700, 950, 1200], length=1400)
        det = CausalPureIntegerQRSDetector()
        emitted_history = []
        for sample_idx, sample in enumerate(signal):
            out = det.step(sample)
            if out is not None:
                emitted_history.append(out)
                # Output must be monotonic in time
                if len(emitted_history) >= 2:
                    self.assertGreater(
                        emitted_history[-1],
                        emitted_history[-2],
                        "Emitted QRS timestamps must be strictly monotonic",
                    )

        # Final accepted_peaks must strictly match the stream of emitted outputs
        self.assertEqual(
            det.accepted_peaks,
            emitted_history,
            "Detector internal accepted_peaks must match irrevocable emitted stream",
        )

    def test_twave_and_startup_transient_protection(self):
        from qrs_detector import CausalPureIntegerQRSDetector

        # Signal with:
        # 1. Startup noise spike at sample 30 (should be suppressed by startup window)
        # 2. Strong QRS at sample 200
        # 3. Peaked T-wave at sample 270 (70 samples post-R, in 50..95 window, should be suppressed)
        # 4. Strong QRS at sample 500
        signal = [0] * 800
        signal[30] = 300  # Startup transient
        pulse_strong = ((-3, 80), (-2, 220), (-1, 700), (0, 1200), (1, 700), (2, 220), (3, 80))
        pulse_twave = ((-5, 20), (-3, 60), (-1, 150), (0, 200), (1, 150), (3, 60), (5, 20))

        for p in (200, 500):
            for delta, val in pulse_strong:
                signal[p + delta] += val
        for delta, val in pulse_twave:
            signal[270 + delta] += val

        det = CausalPureIntegerQRSDetector()
        det.feed_chunk(signal)
        result = det.get_result()

        self.assertNotIn(30, result.peak_indices, "Startup transient at sample 30 must not be accepted")
        self.assertNotIn(270, result.peak_indices, "Peaked T-wave at sample 270 must not be accepted as QRS")
        self.assertEqual(result.peak_indices, [200, 500])

    def test_independent_float_reference_differs_honestly_from_causal_integer_reference(self):
        # On synthetic pulse where both are clean, both match
        clean_signal = synthetic_qrs([200, 500, 800], length=1000)
        float_clean = detect_qrs_float(clean_signal)
        fixed_clean = detect_qrs_fixed(clean_signal)
        self.assertEqual(float_clean.peak_indices, [200, 500, 800])
        self.assertEqual(fixed_clean.peak_indices, [200, 500, 800])

        # Verify detect_qrs_float produces float candidates with float strengths
        self.assertTrue(all(isinstance(c.strength, float) for c in float_clean.candidates))
        # Verify detect_qrs_fixed produces int candidates with int strengths
        self.assertTrue(all(isinstance(c.strength, int) for c in fixed_clean.candidates))

    def test_pure_integer_causal_state_no_float(self):
        from qrs_detector import CausalPureIntegerQRSDetector
        signal = synthetic_qrs([250, 500, 750], length=1000)
        det = CausalPureIntegerQRSDetector()
        det.feed_chunk(signal)
        self.assertIsInstance(det.signal_level, int)
        self.assertIsInstance(det.noise_level, int)
        self.assertIsInstance(det.mwi_sum, int)
        for sec in det.sections:
            for val in sec:
                self.assertIsInstance(val, int)

    def test_rtl_parameter_export(self):
        from qrs_detector import get_fixed_qrs_rtl_parameters
        params = get_fixed_qrs_rtl_parameters()
        self.assertEqual(params["q_format"], "Q2.14")
        self.assertEqual(params["scale_factor_q14"], 16384)
        self.assertEqual(len(params["sos_sections_q14"]), 4)
        self.assertEqual(params["derivative_divisor"], 8)
        self.assertEqual(params["mwi_length_samples"], 30)


if __name__ == "__main__":
    unittest.main(verbosity=2)
