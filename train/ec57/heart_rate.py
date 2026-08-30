"""Reference heart-rate calculation with explicit RR validity and staleness."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence


MIN_RR_MS = 250
MAX_RR_MS = 2000
RECENT_RR_COUNT = 5
STALE_AFTER_SAMPLES = 750  # 3 s at the frozen 250 Hz rate


class HeartRateError(ValueError):
    """Raised for invalid sample-rate or QRS inputs."""


def _valid_rr_float(rr_ms: Sequence[float]) -> list[float]:
    return [float(value) for value in rr_ms if MIN_RR_MS <= float(value) <= MAX_RR_MS]


def _median_float(values: Sequence[float]) -> float:
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2.0


def compute_hr_float(rr_ms: Sequence[float]) -> float | None:
    valid = _valid_rr_float(rr_ms)[-RECENT_RR_COUNT:]
    if not valid:
        return None
    return 60000.0 / _median_float(valid)


def _valid_rr_fixed(rr_ms: Sequence[int]) -> list[int]:
    valid: list[int] = []
    for value in rr_ms:
        if not isinstance(value, int):
            raise HeartRateError("fixed RR values must be integers")
        if MIN_RR_MS <= value <= MAX_RR_MS:
            valid.append(value)
    return valid


def compute_hr_fixed(rr_ms: Sequence[int]) -> float | None:
    """Compute HR from integer RR values, retaining a Q16.16 result."""
    valid = _valid_rr_fixed(rr_ms)[-RECENT_RR_COUNT:]
    if not valid:
        return None
    ordered = sorted(valid)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        median_numerator = ordered[middle]
        median_denominator = 1
    else:
        median_numerator = ordered[middle - 1] + ordered[middle]
        median_denominator = 2
    hr_q16 = (60000 * median_denominator * (1 << 16)) // median_numerator
    return hr_q16 / float(1 << 16)


@dataclass(frozen=True)
class HRUpdate:
    sample_index: int
    rr_ms: int | None
    rr_history_ms: list[int]
    heart_rate_bpm: float | None
    valid: bool
    state: str


class HeartRateReference:
    """Stateful HR reference using only QRS timestamps supplied by the caller."""

    def __init__(self, sample_rate_hz: int = 250, mode: str = "float"):
        if sample_rate_hz != 250:
            raise HeartRateError("INVALID_SAMPLING_RATE: HR reference requires 250 Hz")
        if mode not in {"float", "fixed"}:
            raise HeartRateError("mode must be float or fixed")
        self.sample_rate_hz = sample_rate_hz
        self.mode = mode
        self._last_qrs_index: int | None = None
        self._rr_history_ms: list[int] = []
        self._heart_rate_bpm: float | None = None
        self._state = "HR_INVALID_NO_QRS"

    @property
    def rr_history_ms(self) -> list[int]:
        return list(self._rr_history_ms)

    def _make_update(self, sample_index: int, rr_ms: int | None, state: str | None = None) -> HRUpdate:
        current_state = state or self._state
        valid = current_state == "HR_VALID" and self._heart_rate_bpm is not None
        return HRUpdate(
            sample_index=sample_index,
            rr_ms=rr_ms,
            rr_history_ms=list(self._rr_history_ms),
            heart_rate_bpm=self._heart_rate_bpm if valid else None,
            valid=valid,
            state=current_state,
        )

    def add_qrs(self, sample_index: int, valid: bool = True) -> HRUpdate:
        if not isinstance(sample_index, int) or sample_index < 0:
            raise HeartRateError("sample_index must be a non-negative integer")
        if self._last_qrs_index is not None and sample_index <= self._last_qrs_index:
            raise HeartRateError("QRS sample indices must increase")
        if not valid:
            return self._make_update(sample_index, None, "QRS_INVALID")
        rr_ms: int | None = None
        if self._last_qrs_index is not None:
            delta_samples = sample_index - self._last_qrs_index
            rr_ms = (delta_samples * 1000) // self.sample_rate_hz
            if MIN_RR_MS <= rr_ms <= MAX_RR_MS:
                self._rr_history_ms.append(rr_ms)
                self._rr_history_ms = self._rr_history_ms[-RECENT_RR_COUNT:]
        self._last_qrs_index = sample_index
        if self.mode == "float":
            self._heart_rate_bpm = compute_hr_float(self._rr_history_ms)
        else:
            self._heart_rate_bpm = compute_hr_fixed(self._rr_history_ms)
        self._state = "HR_VALID" if self._heart_rate_bpm is not None else "HR_INVALID_NO_VALID_RR"
        return self._make_update(sample_index, rr_ms)

    def advance_to(self, sample_index: int) -> HRUpdate:
        if not isinstance(sample_index, int) or sample_index < 0:
            raise HeartRateError("sample_index must be a non-negative integer")
        if self._last_qrs_index is not None and sample_index < self._last_qrs_index:
            raise HeartRateError("time cannot move backwards")
        if self._last_qrs_index is None or sample_index - self._last_qrs_index >= STALE_AFTER_SAMPLES:
            self._heart_rate_bpm = None
            self._state = "HR_INVALID_NO_QRS"
            return self._make_update(sample_index, None)
        return self._make_update(sample_index, None)
