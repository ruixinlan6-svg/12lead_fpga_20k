from __future__ import annotations

import ast
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "train" / "ec57"))

from rhythm_engine import RhythmEngine


def update(
    engine: RhythmEngine,
    timestamp_ms: int,
    *,
    leads: int = 1,
    hr: int | None = None,
    qrs: bool = False,
    beat: str | None = None,
    sample_index: int | None = None,
):
    return engine.update(
        timestamp_ms=timestamp_ms,
        valid_lead_count=leads,
        hr_bpm=hr,
        qrs_valid=qrs,
        beat_class=beat,
        sample_index=sample_index,
    )


def feed_beats(engine: RhythmEngine, labels: list[str], *, start_ms: int = 0, rr_ms: int = 1000):
    return [
        update(engine, start_ms + index * rr_ms, qrs=True, beat=label)
        for index, label in enumerate(labels)
    ]


class TestIntegerTimeAndThresholds(unittest.TestCase):
    def test_implementation_has_no_float_constant_or_true_division(self):
        source_path = ROOT / "train" / "ec57" / "rhythm_engine.py"
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        self.assertFalse(
            any(isinstance(node, ast.Constant) and isinstance(node.value, float) for node in ast.walk(tree))
        )
        self.assertFalse(any(isinstance(node, ast.Div) for node in ast.walk(tree)))

    def test_brady_asserts_at_10000_ms_not_9999_and_50_does_not_start(self):
        engine = RhythmEngine()
        self.assertNotIn("BRADY_CANDIDATE", update(engine, 0, hr=50, qrs=True).active_states)
        self.assertNotIn("BRADY_CANDIDATE", update(engine, 1, hr=49, qrs=True).active_states)
        self.assertNotIn("BRADY_CANDIDATE", update(engine, 10000, hr=49, qrs=True).active_states)
        asserted = update(engine, 10001, hr=49, qrs=True)
        self.assertIn("BRADY_CANDIDATE", asserted.active_states)
        self.assertEqual(asserted.point_events, ("BRADY_CANDIDATE",))

    def test_brady_clear_uses_55_and_exact_5000_ms(self):
        engine = RhythmEngine()
        update(engine, 0, hr=49, qrs=True)
        update(engine, 10000, hr=49, qrs=True)
        self.assertIn("BRADY_CANDIDATE", update(engine, 10001, hr=54, qrs=True).active_states)
        self.assertIn("BRADY_CANDIDATE", update(engine, 10002, hr=55, qrs=True).active_states)
        self.assertIn("BRADY_CANDIDATE", update(engine, 15001, hr=55, qrs=True).active_states)
        self.assertNotIn("BRADY_CANDIDATE", update(engine, 15002, hr=55, qrs=True).active_states)

    def test_tachy_strict_100_101_and_95_clear_boundaries(self):
        engine = RhythmEngine()
        update(engine, 0, hr=100, qrs=True)
        update(engine, 1, hr=101, qrs=True)
        self.assertNotIn("TACHY_CANDIDATE", update(engine, 10000, hr=101, qrs=True).active_states)
        self.assertIn("TACHY_CANDIDATE", update(engine, 10001, hr=101, qrs=True).active_states)
        self.assertIn("TACHY_CANDIDATE", update(engine, 10002, hr=96, qrs=True).active_states)
        update(engine, 10003, hr=95, qrs=True)
        self.assertIn("TACHY_CANDIDATE", update(engine, 15002, hr=95, qrs=True).active_states)
        self.assertNotIn("TACHY_CANDIDATE", update(engine, 15003, hr=95, qrs=True).active_states)

    def test_asystole_asserts_at_3000_ms_not_2999_and_next_qrs_clears(self):
        engine = RhythmEngine()
        update(engine, 0)
        self.assertNotIn("ASYSTOLE_CANDIDATE", update(engine, 2999).active_states)
        asserted = update(engine, 3000)
        self.assertIn("ASYSTOLE_CANDIDATE", asserted.active_states)
        self.assertEqual(asserted.point_events, ("ASYSTOLE_CANDIDATE",))
        cleared = update(engine, 3001, qrs=True, beat="nonV")
        self.assertNotIn("ASYSTOLE_CANDIDATE", cleared.active_states)

    def test_invalid_hr_breaks_pending_timer_but_not_active_hysteretic_state(self):
        engine = RhythmEngine()
        update(engine, 0, hr=49, qrs=True)
        update(engine, 9999, hr=None)
        self.assertNotIn("BRADY_CANDIDATE", update(engine, 10000, hr=49, qrs=True).active_states)
        self.assertIn("BRADY_CANDIDATE", update(engine, 20000, hr=49, qrs=True).active_states)
        self.assertIn("BRADY_CANDIDATE", update(engine, 20001, hr=None).active_states)


class TestVentricularEvents(unittest.TestCase):
    def test_second_v_is_point_couplet_and_third_v_upgrades_to_active_run(self):
        engine = RhythmEngine()
        first, second, third = feed_beats(engine, ["V", "V", "V"], rr_ms=700)
        self.assertEqual(first.point_events, ())
        self.assertEqual(second.point_events, ("PVC_COUPLET",))
        self.assertNotIn("PVC_COUPLET", second.active_states)
        self.assertIn("VENTRICULAR_RUN", third.point_events)
        self.assertIn("VENTRICULAR_RUN", third.active_states)
        self.assertNotIn("PVC_COUPLET", third.active_states)

    def test_exact_100_bpm_median_qualifies_vt_without_float_division(self):
        engine = RhythmEngine()
        results = feed_beats(engine, ["V", "V", "V"], rr_ms=600)
        self.assertIn("VT_CANDIDATE", results[-1].point_events)
        self.assertIn("VT_CANDIDATE", results[-1].active_states)

        slow = RhythmEngine()
        slow_results = feed_beats(slow, ["V", "V", "V"], rr_ms=601)
        self.assertNotIn("VT_CANDIDATE", slow_results[-1].active_states)

    def test_six_continuous_v_emit_one_couplet_and_keep_run_active(self):
        engine = RhythmEngine()
        results = feed_beats(engine, ["V"] * 6, rr_ms=500)
        self.assertEqual(sum("PVC_COUPLET" in result.point_events for result in results), 1)
        self.assertTrue(all("VENTRICULAR_RUN" in result.active_states for result in results[2:]))
        self.assertIn("VT_CANDIDATE", results[-1].active_states)
        ended = update(engine, 3000, qrs=True, beat="nonV")
        self.assertNotIn("VENTRICULAR_RUN", ended.active_states)
        self.assertNotIn("VT_CANDIDATE", ended.active_states)

    def test_unclassified_qrs_breaks_a_ventricular_run(self):
        engine = RhythmEngine()
        feed_beats(engine, ["V", "V", "V"], rr_ms=500)
        result = update(engine, 1500, qrs=True)
        self.assertNotIn("VENTRICULAR_RUN", result.active_states)


class TestPeriodicPatterns(unittest.TestCase):
    def test_bigeminy_activates_at_six_beats_and_clears_after_two_consecutive_violations(self):
        engine = RhythmEngine()
        results = feed_beats(engine, ["nonV", "V", "nonV", "V", "nonV", "V"])
        self.assertEqual(results[-1].point_events, ("BIGEMINY_CANDIDATE",))
        self.assertIn("BIGEMINY_CANDIDATE", results[-1].active_states)

        violation_one = update(engine, 6000, qrs=True, beat="V")  # expected nonV
        self.assertIn("BIGEMINY_CANDIDATE", violation_one.active_states)
        violation_two = update(engine, 7000, qrs=True, beat="nonV")  # expected V
        self.assertNotIn("BIGEMINY_CANDIDATE", violation_two.active_states)

    def test_one_pattern_violation_is_forgiven_by_next_correct_beat(self):
        engine = RhythmEngine()
        feed_beats(engine, ["nonV", "V", "nonV", "V", "nonV", "V"])
        self.assertIn("BIGEMINY_CANDIDATE", update(engine, 6000, qrs=True, beat="V").active_states)
        self.assertIn("BIGEMINY_CANDIDATE", update(engine, 7000, qrs=True, beat="V").active_states)
        self.assertIn("BIGEMINY_CANDIDATE", update(engine, 8000, qrs=True, beat="V").active_states)
        self.assertNotIn("BIGEMINY_CANDIDATE", update(engine, 9000, qrs=True, beat="nonV").active_states)

    def test_trigeminy_activates_at_nine_beats_and_clears_after_two_violations(self):
        engine = RhythmEngine()
        labels = ["nonV", "nonV", "V"] * 3
        results = feed_beats(engine, labels)
        self.assertEqual(results[-1].point_events, ("TRIGEMINY_CANDIDATE",))
        self.assertIn("TRIGEMINY_CANDIDATE", results[-1].active_states)
        self.assertIn("TRIGEMINY_CANDIDATE", update(engine, 9000, qrs=True, beat="V").active_states)
        self.assertNotIn("TRIGEMINY_CANDIDATE", update(engine, 10000, qrs=True, beat="V").active_states)


class TestIntegritySignalLossAndReplay(unittest.TestCase):
    def test_zero_valid_leads_outputs_only_signal_loss_and_restarts_asystole_clock(self):
        engine = RhythmEngine()
        update(engine, 0)
        update(engine, 3000)
        lost = update(engine, 3001, leads=0)
        self.assertEqual(lost.active_states, ("SIGNAL_LOSS",))
        self.assertEqual(lost.point_events, ("SIGNAL_LOSS",))
        regained = update(engine, 3002, leads=1)
        self.assertEqual(regained.active_states, ())
        self.assertNotIn("ASYSTOLE_CANDIDATE", update(engine, 6001, leads=1).active_states)
        self.assertIn("ASYSTOLE_CANDIDATE", update(engine, 6002, leads=1).active_states)

    def test_duplicate_backward_and_forward_gap_fail_closed_and_are_counted(self):
        engine = RhythmEngine()
        self.assertTrue(update(engine, 0, sample_index=10, hr=49).accepted)

        duplicate = update(engine, 1, sample_index=10, hr=49)
        self.assertFalse(duplicate.accepted)
        self.assertEqual(duplicate.error_state, "DUPLICATE_SAMPLE")
        self.assertEqual(duplicate.active_states, ())
        self.assertEqual(duplicate.error_counts["DUPLICATE_SAMPLE"], 1)

        self.assertTrue(update(engine, 2, sample_index=11).accepted)
        backward = update(engine, 3, sample_index=9, qrs=True, beat="V")
        self.assertFalse(backward.accepted)
        self.assertEqual(backward.error_state, "OUT_OF_ORDER_SAMPLE")
        self.assertEqual(backward.point_events, ())
        self.assertEqual(backward.error_counts["OUT_OF_ORDER_SAMPLE"], 1)

        self.assertTrue(update(engine, 4, sample_index=12).accepted)
        gap = update(engine, 5, sample_index=15, qrs=True, beat="V")
        self.assertFalse(gap.accepted)
        self.assertEqual(gap.error_state, "MISSING_SAMPLE")
        self.assertEqual(gap.error_counts["MISSING_SAMPLE"], 2)
        self.assertEqual(gap.point_events, ())
        self.assertTrue(update(engine, 6, sample_index=16).accepted)

    def test_equal_or_backward_time_and_invalid_event_combinations_fail_closed(self):
        engine = RhythmEngine()
        update(engine, 10)
        equal_time = update(engine, 10, qrs=True, beat="V")
        self.assertFalse(equal_time.accepted)
        self.assertEqual(equal_time.error_state, "OUT_OF_ORDER_SAMPLE")
        self.assertEqual(equal_time.point_events, ())

        bad_beat = update(engine, 11, beat="V")
        self.assertFalse(bad_beat.accepted)
        self.assertEqual(bad_beat.error_state, "INVALID_CONFIGURATION")

        no_lead_qrs = update(engine, 12, leads=0, qrs=True, beat="V")
        self.assertFalse(no_lead_qrs.accepted)
        self.assertEqual(no_lead_qrs.active_states, ())

        bad_hr = update(engine, 13, hr=29)
        self.assertFalse(bad_hr.accepted)
        self.assertEqual(bad_hr.error_state, "INVALID_CONFIGURATION")

    def test_reset_clears_state_and_replay_is_deterministic(self):
        vectors = [
            dict(timestamp_ms=0, valid_lead_count=1, hr_bpm=49),
            dict(timestamp_ms=10000, valid_lead_count=1, hr_bpm=49),
            dict(timestamp_ms=11000, valid_lead_count=1, hr_bpm=60, qrs_valid=True, beat_class="V"),
            dict(timestamp_ms=11600, valid_lead_count=1, hr_bpm=60, qrs_valid=True, beat_class="V"),
            dict(timestamp_ms=12200, valid_lead_count=1, hr_bpm=60, qrs_valid=True, beat_class="V"),
        ]
        engine = RhythmEngine()
        first = [result.as_dict() for result in engine.replay(vectors)]
        reset_result = engine.reset()
        self.assertEqual(reset_result.point_events, ("RESET_SEEN",))
        self.assertEqual(reset_result.active_states, ())
        second = [result.as_dict() for result in engine.replay(vectors)]
        engine.reset()
        third = [result.as_dict() for result in engine.replay(vectors)]

        def without_audit_counts(items):
            return [{key: value for key, value in item.items() if key != "error_counts"} for item in items]

        self.assertEqual(without_audit_counts(first), without_audit_counts(second))
        self.assertEqual(without_audit_counts(second), without_audit_counts(third))
        self.assertEqual(
            json.dumps(without_audit_counts(second), sort_keys=True),
            json.dumps(without_audit_counts(third), sort_keys=True),
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
