"""Pure-integer deterministic reference for the frozen research rhythm events.

This module is a software Golden, not a clinical alarm implementation.  Event
durations use integer milliseconds.  Optional 250 Hz sample indices are used
only to audit stream continuity and never as wall-clock time.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping


BRADY_ASSERT_MS = 10_000
BRADY_CLEAR_MS = 5_000
TACHY_ASSERT_MS = 10_000
TACHY_CLEAR_MS = 5_000
ASYSTOLE_ASSERT_MS = 3_000
VT_LIMIT_RR_MS = 600
MIN_VALID_HR_BPM = 30
MAX_VALID_HR_BPM = 220

BIGEMINY_PATTERN = ("nonV", "V", "nonV", "V", "nonV", "V")
TRIGEMINY_PATTERN = ("nonV", "nonV", "V", "nonV", "nonV", "V", "nonV", "nonV", "V")

POINT_EVENT_ORDER = (
    "RESET_SEEN",
    "SIGNAL_LOSS",
    "BRADY_CANDIDATE",
    "TACHY_CANDIDATE",
    "ASYSTOLE_CANDIDATE",
    "PVC_COUPLET",
    "VENTRICULAR_RUN",
    "VT_CANDIDATE",
    "BIGEMINY_CANDIDATE",
    "TRIGEMINY_CANDIDATE",
)

ACTIVE_STATE_ORDER = (
    "SIGNAL_LOSS",
    "BRADY_CANDIDATE",
    "TACHY_CANDIDATE",
    "ASYSTOLE_CANDIDATE",
    "VENTRICULAR_RUN",
    "VT_CANDIDATE",
    "BIGEMINY_CANDIDATE",
    "TRIGEMINY_CANDIDATE",
)

ERROR_ORDER = (
    "MISSING_SAMPLE",
    "DUPLICATE_SAMPLE",
    "OUT_OF_ORDER_SAMPLE",
    "INVALID_CONFIGURATION",
    "RESET_SEEN",
)


def _is_plain_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _ordered_subset(values: Iterable[str], order: tuple[str, ...]) -> tuple[str, ...]:
    present = frozenset(values)
    return tuple(name for name in order if name in present)


@dataclass(frozen=True)
class RhythmResult:
    """One deterministic output observation from :class:`RhythmEngine`."""

    timestamp_ms: int
    accepted: bool
    status: str
    error_state: str | None
    point_events: tuple[str, ...]
    active_states: tuple[str, ...]
    error_counts: dict[str, int]

    def as_dict(self) -> dict[str, object]:
        return {
            "timestamp_ms": self.timestamp_ms,
            "accepted": self.accepted,
            "status": self.status,
            "error_state": self.error_state,
            "point_events": list(self.point_events),
            "active_states": list(self.active_states),
            "error_counts": dict(self.error_counts),
        }


class RhythmEngine:
    """Integer-only reference state machine for EC57 project research events."""

    def __init__(self) -> None:
        self._error_counts = {name: 0 for name in ERROR_ORDER}
        self._last_timestamp_ms: int | None = None
        self._last_sample_index: int | None = None
        self._initialize_rhythm_state()

    def _initialize_rhythm_state(self) -> None:
        self._valid_lead_count = 0
        self._signal_loss = False
        self._valid_leads_since_ms: int | None = None
        self._last_qrs_timestamp_ms: int | None = None

        self._brady_active = False
        self._brady_assert_since_ms: int | None = None
        self._brady_clear_since_ms: int | None = None
        self._tachy_active = False
        self._tachy_assert_since_ms: int | None = None
        self._tachy_clear_since_ms: int | None = None
        self._asystole_active = False

        self._consecutive_v = 0
        self._v_timestamps_ms: list[int] = []
        self._ventricular_run_active = False
        self._vt_active = False

        self._recent_beats: list[str] = []
        self._bigeminy_active = False
        self._bigeminy_phase = 0
        self._bigeminy_violations = 0
        self._trigeminy_active = False
        self._trigeminy_phase = 0
        self._trigeminy_violations = 0

    @property
    def error_counts(self) -> dict[str, int]:
        return dict(self._error_counts)

    def reset(self) -> RhythmResult:
        """Reset temporal state while retaining cumulative audit counters."""
        self._initialize_rhythm_state()
        self._last_timestamp_ms = None
        self._last_sample_index = None
        self._error_counts["RESET_SEEN"] += 1
        return self._make_result(
            timestamp_ms=0,
            accepted=True,
            status="RESET_SEEN",
            point_events=("RESET_SEEN",),
        )

    def replay(self, vectors: Iterable[Mapping[str, object]]) -> list[RhythmResult]:
        """Replay already ordered input mappings without implicit reset."""
        results: list[RhythmResult] = []
        for vector in vectors:
            results.append(self.update(**dict(vector)))
        return results

    def update(
        self,
        *,
        timestamp_ms: int,
        valid_lead_count: int,
        hr_bpm: int | None = None,
        qrs_valid: bool = False,
        beat_class: str | None = None,
        sample_index: int | None = None,
    ) -> RhythmResult:
        """Consume one atomic observation and return point and active outputs."""
        if not self._configuration_is_valid(
            timestamp_ms=timestamp_ms,
            valid_lead_count=valid_lead_count,
            hr_bpm=hr_bpm,
            qrs_valid=qrs_valid,
            beat_class=beat_class,
            sample_index=sample_index,
        ):
            return self._reject(timestamp_ms, "INVALID_CONFIGURATION")

        if self._last_timestamp_ms is not None and timestamp_ms <= self._last_timestamp_ms:
            return self._reject(timestamp_ms, "OUT_OF_ORDER_SAMPLE")

        sample_error = self._sample_error(sample_index)
        if sample_error is not None:
            error_name, count = sample_error
            if error_name == "MISSING_SAMPLE":
                self._last_sample_index = sample_index
                self._last_timestamp_ms = timestamp_ms
            return self._reject(timestamp_ms, error_name, count)

        self._last_timestamp_ms = timestamp_ms
        if sample_index is not None:
            self._last_sample_index = sample_index

        point_events: list[str] = []
        if valid_lead_count == 0:
            first_loss_observation = not self._signal_loss
            self._initialize_rhythm_state()
            self._signal_loss = True
            if first_loss_observation:
                point_events.append("SIGNAL_LOSS")
            return self._make_result(
                timestamp_ms=timestamp_ms,
                accepted=True,
                status="SIGNAL_LOSS",
                point_events=point_events,
            )

        if self._valid_lead_count == 0:
            self._valid_leads_since_ms = timestamp_ms
        self._valid_lead_count = valid_lead_count
        self._signal_loss = False

        self._update_hr_states(timestamp_ms, hr_bpm, point_events)

        if qrs_valid:
            self._last_qrs_timestamp_ms = timestamp_ms
            self._asystole_active = False
            self._process_beat(timestamp_ms, beat_class, point_events)

        self._update_asystole(timestamp_ms, point_events)
        return self._make_result(
            timestamp_ms=timestamp_ms,
            accepted=True,
            status="OK",
            point_events=point_events,
        )

    def _configuration_is_valid(
        self,
        *,
        timestamp_ms: object,
        valid_lead_count: object,
        hr_bpm: object,
        qrs_valid: object,
        beat_class: object,
        sample_index: object,
    ) -> bool:
        if not _is_plain_int(timestamp_ms) or timestamp_ms < 0:
            return False
        if not _is_plain_int(valid_lead_count) or not 0 <= valid_lead_count <= 12:
            return False
        if hr_bpm is not None:
            if not _is_plain_int(hr_bpm) or not MIN_VALID_HR_BPM <= hr_bpm <= MAX_VALID_HR_BPM:
                return False
        if not isinstance(qrs_valid, bool):
            return False
        if beat_class not in {None, "nonV", "V"}:
            return False
        if beat_class is not None and not qrs_valid:
            return False
        if qrs_valid and valid_lead_count == 0:
            return False
        if sample_index is not None and (not _is_plain_int(sample_index) or sample_index < 0):
            return False
        return True

    def _sample_error(self, sample_index: int | None) -> tuple[str, int] | None:
        if sample_index is None or self._last_sample_index is None:
            return None
        if sample_index == self._last_sample_index:
            return "DUPLICATE_SAMPLE", 1
        if sample_index < self._last_sample_index:
            return "OUT_OF_ORDER_SAMPLE", 1
        if sample_index > self._last_sample_index + 1:
            return "MISSING_SAMPLE", sample_index - self._last_sample_index - 1
        return None

    def _reject(self, timestamp_ms: object, error_name: str, count: int = 1) -> RhythmResult:
        self._error_counts[error_name] += count
        self._initialize_rhythm_state()
        safe_timestamp = timestamp_ms if _is_plain_int(timestamp_ms) and timestamp_ms >= 0 else 0
        return self._make_result(
            timestamp_ms=safe_timestamp,
            accepted=False,
            status="STREAM_ERROR",
            error_state=error_name,
        )

    def _update_hr_states(self, timestamp_ms: int, hr_bpm: int | None, point_events: list[str]) -> None:
        if hr_bpm is None:
            self._brady_assert_since_ms = None
            self._brady_clear_since_ms = None
            self._tachy_assert_since_ms = None
            self._tachy_clear_since_ms = None
            return

        if not self._brady_active:
            self._brady_clear_since_ms = None
            if hr_bpm < 50:
                if self._brady_assert_since_ms is None:
                    self._brady_assert_since_ms = timestamp_ms
                if timestamp_ms - self._brady_assert_since_ms >= BRADY_ASSERT_MS:
                    self._brady_active = True
                    self._brady_assert_since_ms = None
                    point_events.append("BRADY_CANDIDATE")
            else:
                self._brady_assert_since_ms = None
        else:
            self._brady_assert_since_ms = None
            if hr_bpm >= 55:
                if self._brady_clear_since_ms is None:
                    self._brady_clear_since_ms = timestamp_ms
                if timestamp_ms - self._brady_clear_since_ms >= BRADY_CLEAR_MS:
                    self._brady_active = False
                    self._brady_clear_since_ms = None
            else:
                self._brady_clear_since_ms = None

        if not self._tachy_active:
            self._tachy_clear_since_ms = None
            if hr_bpm > 100:
                if self._tachy_assert_since_ms is None:
                    self._tachy_assert_since_ms = timestamp_ms
                if timestamp_ms - self._tachy_assert_since_ms >= TACHY_ASSERT_MS:
                    self._tachy_active = True
                    self._tachy_assert_since_ms = None
                    point_events.append("TACHY_CANDIDATE")
            else:
                self._tachy_assert_since_ms = None
        else:
            self._tachy_assert_since_ms = None
            if hr_bpm <= 95:
                if self._tachy_clear_since_ms is None:
                    self._tachy_clear_since_ms = timestamp_ms
                if timestamp_ms - self._tachy_clear_since_ms >= TACHY_CLEAR_MS:
                    self._tachy_active = False
                    self._tachy_clear_since_ms = None
            else:
                self._tachy_clear_since_ms = None

    def _update_asystole(self, timestamp_ms: int, point_events: list[str]) -> None:
        anchor_ms = self._last_qrs_timestamp_ms
        if anchor_ms is None:
            anchor_ms = self._valid_leads_since_ms
        if anchor_ms is None:
            return
        if not self._asystole_active and timestamp_ms - anchor_ms >= ASYSTOLE_ASSERT_MS:
            self._asystole_active = True
            point_events.append("ASYSTOLE_CANDIDATE")

    def _process_beat(self, timestamp_ms: int, beat_class: str | None, point_events: list[str]) -> None:
        normalized_class = beat_class if beat_class is not None else "UNCLASSIFIED"
        if normalized_class == "V":
            self._consecutive_v += 1
            self._v_timestamps_ms.append(timestamp_ms)
            if self._consecutive_v == 2:
                point_events.append("PVC_COUPLET")
            if self._consecutive_v >= 3:
                if not self._ventricular_run_active:
                    point_events.append("VENTRICULAR_RUN")
                self._ventricular_run_active = True
                qualifies_vt = self._median_v_interval_is_at_most_limit()
                if qualifies_vt and not self._vt_active:
                    point_events.append("VT_CANDIDATE")
                self._vt_active = qualifies_vt
        else:
            self._consecutive_v = 0
            self._v_timestamps_ms = []
            self._ventricular_run_active = False
            self._vt_active = False

        self._update_periodic_patterns(normalized_class, point_events)

    def _median_v_interval_is_at_most_limit(self) -> bool:
        intervals = [
            current - previous
            for previous, current in zip(self._v_timestamps_ms, self._v_timestamps_ms[1:])
        ]
        if not intervals:
            return False
        ordered = sorted(intervals)
        middle = len(ordered) // 2
        if len(ordered) % 2:
            return ordered[middle] <= VT_LIMIT_RR_MS
        return ordered[middle - 1] + ordered[middle] <= 2 * VT_LIMIT_RR_MS

    def _update_periodic_patterns(self, beat_class: str, point_events: list[str]) -> None:
        if self._bigeminy_active:
            expected = BIGEMINY_PATTERN[self._bigeminy_phase]
            if beat_class == expected:
                self._bigeminy_violations = 0
            else:
                self._bigeminy_violations += 1
            self._bigeminy_phase = (self._bigeminy_phase + 1) % len(BIGEMINY_PATTERN)
            if self._bigeminy_violations >= 2:
                self._bigeminy_active = False
                self._bigeminy_phase = 0
                self._bigeminy_violations = 0

        if self._trigeminy_active:
            expected = TRIGEMINY_PATTERN[self._trigeminy_phase]
            if beat_class == expected:
                self._trigeminy_violations = 0
            else:
                self._trigeminy_violations += 1
            self._trigeminy_phase = (self._trigeminy_phase + 1) % len(TRIGEMINY_PATTERN)
            if self._trigeminy_violations >= 2:
                self._trigeminy_active = False
                self._trigeminy_phase = 0
                self._trigeminy_violations = 0

        self._recent_beats.append(beat_class)
        self._recent_beats = self._recent_beats[-len(TRIGEMINY_PATTERN) :]

        if not self._bigeminy_active and tuple(self._recent_beats[-len(BIGEMINY_PATTERN) :]) == BIGEMINY_PATTERN:
            self._bigeminy_active = True
            self._bigeminy_phase = 0
            self._bigeminy_violations = 0
            point_events.append("BIGEMINY_CANDIDATE")

        if not self._trigeminy_active and tuple(self._recent_beats[-len(TRIGEMINY_PATTERN) :]) == TRIGEMINY_PATTERN:
            self._trigeminy_active = True
            self._trigeminy_phase = 0
            self._trigeminy_violations = 0
            point_events.append("TRIGEMINY_CANDIDATE")

    def _active_states(self) -> tuple[str, ...]:
        if self._signal_loss:
            return ("SIGNAL_LOSS",)
        values: list[str] = []
        if self._brady_active:
            values.append("BRADY_CANDIDATE")
        if self._tachy_active:
            values.append("TACHY_CANDIDATE")
        if self._asystole_active:
            values.append("ASYSTOLE_CANDIDATE")
        if self._ventricular_run_active:
            values.append("VENTRICULAR_RUN")
        if self._vt_active:
            values.append("VT_CANDIDATE")
        if self._bigeminy_active:
            values.append("BIGEMINY_CANDIDATE")
        if self._trigeminy_active:
            values.append("TRIGEMINY_CANDIDATE")
        return _ordered_subset(values, ACTIVE_STATE_ORDER)

    def _make_result(
        self,
        *,
        timestamp_ms: int,
        accepted: bool,
        status: str,
        error_state: str | None = None,
        point_events: Iterable[str] = (),
    ) -> RhythmResult:
        return RhythmResult(
            timestamp_ms=timestamp_ms,
            accepted=accepted,
            status=status,
            error_state=error_state,
            point_events=_ordered_subset(point_events, POINT_EVENT_ORDER),
            active_states=self._active_states() if accepted else (),
            error_counts={name: self._error_counts[name] for name in ERROR_ORDER},
        )
