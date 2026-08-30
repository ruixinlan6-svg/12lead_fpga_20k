"""Floating-point and hardware-equivalent integer SQI references."""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from typing import Mapping, Sequence


INT16_MIN = -32768
INT16_MAX = 32767
MICROVOLTS_PER_LSB = 5
SQI_WINDOW_SAMPLES = 500
LEAD_ORDER = [
    "I",
    "II",
    "III",
    "aVR",
    "aVL",
    "aVF",
    "V1",
    "V2",
    "V3",
    "V4",
    "V5",
    "V6",
]


@dataclass(frozen=True)
class SQIResult:
    valid: bool
    reason_codes: tuple[str, ...]
    peak_to_peak_uv: float
    std_uv: float
    saturation_count: int
    differential_noise_count: int
    sample_count: int
    qrs_candidate_count: int = 0

    @property
    def saturation_fraction(self) -> float:
        return self.saturation_count / self.sample_count if self.sample_count else 0.0

    @property
    def differential_noise_fraction(self) -> float:
        denominator = max(self.sample_count - 1, 1)
        return self.differential_noise_count / denominator

    @property
    def ranking_key(self) -> tuple[float, float, float]:
        return (
            -float(self.qrs_candidate_count),
            self.differential_noise_fraction,
            self.saturation_fraction,
        )


@dataclass(frozen=True)
class LeadSelection:
    status: str
    selected_leads: list[str]
    quality_by_lead: dict[str, SQIResult]


def _window(samples: Sequence[float | int]) -> list[float | int]:
    values = list(samples)
    if len(values) < SQI_WINDOW_SAMPLES:
        raise ValueError(f"SQI requires a complete {SQI_WINDOW_SAMPLES}-sample window")
    return values[-SQI_WINDOW_SAMPLES:]


def evaluate_sqi_float(
    samples_lsb: Sequence[float],
    *,
    qrs_candidate_count: int = 0,
) -> SQIResult:
    """Evaluate M0 thresholds using floating-point statistics on int16-LSB values."""
    values = _window(samples_lsb)
    if not all(math.isfinite(float(value)) for value in values):
        raise ValueError("SQI input contains a non-finite value")
    peak_to_peak_lsb = max(values) - min(values)
    std_lsb = statistics.pstdev([float(value) for value in values])
    rail = [float(value) <= INT16_MIN or float(value) >= INT16_MAX for value in values]
    saturation_count = sum(rail)
    has_consecutive_saturation = any(rail[index] and rail[index + 1] and rail[index + 2] for index in range(len(rail) - 2))
    differential_noise_count = sum(
        abs(float(values[index + 1]) - float(values[index])) * MICROVOLTS_PER_LSB > 2000
        for index in range(len(values) - 1)
    )
    reasons: list[str] = []
    if peak_to_peak_lsb * MICROVOLTS_PER_LSB < 50 or std_lsb * MICROVOLTS_PER_LSB < 10:
        reasons.append("FLATLINE")
    if has_consecutive_saturation or saturation_count / len(values) >= 0.01:
        reasons.append("SATURATION")
    if differential_noise_count / max(len(values) - 1, 1) > 0.01:
        reasons.append("IMPULSIVE_NOISE")
    return SQIResult(
        valid=not reasons,
        reason_codes=tuple(reasons),
        peak_to_peak_uv=peak_to_peak_lsb * MICROVOLTS_PER_LSB,
        std_uv=std_lsb * MICROVOLTS_PER_LSB,
        saturation_count=saturation_count,
        differential_noise_count=differential_noise_count,
        sample_count=len(values),
        qrs_candidate_count=int(qrs_candidate_count),
    )


def evaluate_sqi_fixed(
    samples_lsb: Sequence[int],
    *,
    qrs_candidate_count: int = 0,
) -> SQIResult:
    """Evaluate the same thresholds with integer comparisons used by hardware.

    This implementation intentionally does not call the floating-point
    implementation: variance and percentage thresholds are compared as exact
    integer inequalities.
    """
    values_raw = _window(samples_lsb)
    values: list[int] = []
    for value in values_raw:
        if not isinstance(value, int) or value < INT16_MIN or value > INT16_MAX:
            raise ValueError("fixed SQI input must be an int16 integer")
        values.append(value)
    count = len(values)
    total = sum(values)
    sum_squares = sum(value * value for value in values)
    variance_numerator = sum_squares * count - total * total
    peak_to_peak_lsb = max(values) - min(values)
    rail = [value <= INT16_MIN or value >= INT16_MAX for value in values]
    saturation_count = sum(1 for value in rail if value)
    has_consecutive_saturation = any(rail[index] and rail[index + 1] and rail[index + 2] for index in range(count - 2))
    differential_noise_count = sum(
        1 for index in range(count - 1) if abs(values[index + 1] - values[index]) * MICROVOLTS_PER_LSB > 2000
    )
    reasons: list[str] = []
    # std_uv < 10 is std_lsb < 2; population variance is numerator / count^2.
    if peak_to_peak_lsb * MICROVOLTS_PER_LSB < 50 or variance_numerator < 4 * count * count:
        reasons.append("FLATLINE")
    if has_consecutive_saturation or saturation_count * 100 >= count:
        reasons.append("SATURATION")
    if differential_noise_count * 100 > max(count - 1, 1):
        reasons.append("IMPULSIVE_NOISE")
    variance = variance_numerator / (count * count)
    return SQIResult(
        valid=not reasons,
        reason_codes=tuple(reasons),
        peak_to_peak_uv=float(peak_to_peak_lsb * MICROVOLTS_PER_LSB),
        std_uv=math.sqrt(variance) * MICROVOLTS_PER_LSB,
        saturation_count=saturation_count,
        differential_noise_count=differential_noise_count,
        sample_count=count,
        qrs_candidate_count=int(qrs_candidate_count),
    )


def _select(quality_by_lead: Mapping[str, SQIResult]) -> LeadSelection:
    valid_leads = [lead for lead, quality in quality_by_lead.items() if quality.valid]
    valid_leads.sort(key=lambda lead: (quality_by_lead[lead].ranking_key, LEAD_ORDER.index(lead) if lead in LEAD_ORDER else len(LEAD_ORDER), lead))
    selected = valid_leads[:3]
    if not selected:
        status = "SIGNAL_LOSS"
    elif len(valid_leads) < 3:
        # M0 exposes one contract-level degraded state; keep incomplete
        # multi-lead selection inside that frozen enum as well.
        status = "DEGRADED_ONE_LEAD"
    else:
        status = "FULL_12_LEAD"
    return LeadSelection(status=status, selected_leads=selected, quality_by_lead=dict(quality_by_lead))


def select_valid_leads_float(lead_samples: Mapping[str, Sequence[float]]) -> LeadSelection:
    qualities = {lead: evaluate_sqi_float(samples) for lead, samples in lead_samples.items()}
    return _select(qualities)


def select_valid_leads_fixed(lead_samples: Mapping[str, Sequence[int]]) -> LeadSelection:
    qualities = {lead: evaluate_sqi_fixed(samples) for lead, samples in lead_samples.items()}
    return _select(qualities)
