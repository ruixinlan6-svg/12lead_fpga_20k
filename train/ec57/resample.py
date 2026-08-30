"""Deterministic rational-polyphase resampling and annotation time mapping."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence


class ResampleError(ValueError):
    """Raised for invalid rates, timestamp drift, or unsupported input."""


@dataclass(frozen=True)
class PolyphaseDesign:
    source_rate_hz: int
    target_rate_hz: int
    up: int
    down: int
    taps_per_phase: int
    phases: tuple[tuple[float, ...], ...]


@dataclass(frozen=True)
class ResampledEvent:
    event_id: str
    source_sample_index: int
    source_rate_hz: float
    target_rate_hz: int
    event_time_s: float
    target_sample_index: int
    target_time_s: float
    error_ms: float

    @property
    def target_sample_drift(self) -> float:
        exact_target_index = self.event_time_s * self.target_rate_hz
        return abs(self.target_sample_index - exact_target_index)


def _validate_rate(rate_hz: float, name: str) -> int:
    if not isinstance(rate_hz, (int, float)) or not math.isfinite(rate_hz) or rate_hz <= 0:
        raise ResampleError(f"{name} must be positive")
    integer_rate = int(rate_hz)
    if integer_rate != rate_hz:
        raise ResampleError(f"{name} must be an integer Hz rate")
    return integer_rate


def _sinc(value: float) -> float:
    if abs(value) < 1e-15:
        return 1.0
    return math.sin(math.pi * value) / (math.pi * value)


def design_polyphase(source_rate_hz: int, target_rate_hz: int, taps_per_phase: int = 16) -> PolyphaseDesign:
    source = _validate_rate(source_rate_hz, "source_rate_hz")
    target = _validate_rate(target_rate_hz, "target_rate_hz")
    if taps_per_phase < 4 or taps_per_phase % 2:
        raise ResampleError("taps_per_phase must be an even integer >= 4")
    gcd = math.gcd(source, target)
    up = target // gcd
    down = source // gcd
    half = taps_per_phase // 2
    phases: list[tuple[float, ...]] = []
    # The FIR operates directly on the source-sample grid.  Its normalized
    # cutoff is therefore the target/source Nyquist ratio, not 1/max(up,down)
    # (the latter is only appropriate after explicitly inserting up-1 zeros).
    cutoff = min(1.0, target / source)
    for phase in range(up):
        fraction = phase / up
        coefficients: list[float] = []
        for tap in range(taps_per_phase):
            offset = tap - half + 1
            distance = offset - fraction
            window_position = tap / (taps_per_phase - 1)
            window = 0.5 - 0.5 * math.cos(2.0 * math.pi * window_position)
            coefficients.append(cutoff * _sinc(cutoff * distance) * window)
        total = sum(coefficients)
        if abs(total) < 1e-15:
            raise ResampleError("polyphase coefficient normalization failed")
        phases.append(tuple(coefficient / total for coefficient in coefficients))
    return PolyphaseDesign(source, target, up, down, taps_per_phase, tuple(phases))


def resample_signal(
    samples: Sequence[float],
    source_rate_hz: int,
    target_rate_hz: int = 250,
    *,
    taps_per_phase: int = 16,
) -> list[float]:
    """Resample a finite sequence with a deterministic edge-replicated polyphase FIR."""
    if not samples:
        return []
    design = design_polyphase(source_rate_hz, target_rate_hz, taps_per_phase)
    output_length = int(round(len(samples) * design.target_rate_hz / design.source_rate_hz))
    output: list[float] = []
    center = design.taps_per_phase // 2
    for output_index in range(output_length):
        source_position = output_index * design.down / design.up
        source_base = math.floor(source_position)
        phase = (output_index * design.down) % design.up
        coefficients = design.phases[phase]
        value = 0.0
        for tap, coefficient in enumerate(coefficients):
            source_index = source_base + tap - center + 1
            source_index = min(max(source_index, 0), len(samples) - 1)
            value += float(samples[source_index]) * coefficient
        output.append(value)
    return output


def _round_half_away_from_zero(value: float) -> int:
    if value < 0:
        return -math.floor(abs(value) + 0.5)
    return math.floor(value + 0.5)


def map_event_sample(
    event_id: str,
    source_sample_index: int,
    source_rate_hz: float,
    target_rate_hz: int = 250,
) -> ResampledEvent:
    source_rate = _validate_rate(source_rate_hz, "source_rate_hz")
    target_rate = _validate_rate(target_rate_hz, "target_rate_hz")
    if not isinstance(source_sample_index, int) or source_sample_index < 0:
        raise ResampleError("source_sample_index must be a non-negative integer")
    event_time_s = source_sample_index / source_rate
    exact_target_index = event_time_s * target_rate
    target_sample_index = _round_half_away_from_zero(exact_target_index)
    target_time_s = target_sample_index / target_rate
    error_ms = abs(target_time_s - event_time_s) * 1000.0
    return ResampledEvent(
        event_id=event_id,
        source_sample_index=source_sample_index,
        source_rate_hz=source_rate,
        target_rate_hz=target_rate,
        event_time_s=event_time_s,
        target_sample_index=target_sample_index,
        target_time_s=target_time_s,
        error_ms=error_ms,
    )


def validate_event_mapping(
    mapping: ResampledEvent,
    *,
    max_error_ms: float = 2.0,
    max_target_sample_drift: float = 1.0,
) -> None:
    source_rate = _validate_rate(mapping.source_rate_hz, "source_rate_hz")
    target_rate = _validate_rate(mapping.target_rate_hz, "target_rate_hz")
    if not isinstance(mapping.source_sample_index, int) or mapping.source_sample_index < 0:
        raise ResampleError("source_sample_index must be a non-negative integer")
    expected_event_time_s = mapping.source_sample_index / source_rate
    if abs(mapping.event_time_s - expected_event_time_s) > 1e-12:
        raise ResampleError(f"event {mapping.event_id} contains an inconsistent event_time_s")
    expected_target_index = _round_half_away_from_zero(expected_event_time_s * target_rate)
    if mapping.target_sample_index != expected_target_index:
        raise ResampleError(f"event {mapping.event_id} contains an inconsistent target_sample_index")
    expected_target_time_s = expected_target_index / target_rate
    if abs(mapping.target_time_s - expected_target_time_s) > 1e-12:
        raise ResampleError(f"event {mapping.event_id} contains an inconsistent target_time_s")
    computed_error_ms = abs(mapping.target_time_s - mapping.event_time_s) * 1000.0
    if abs(computed_error_ms - mapping.error_ms) > 1e-9:
        raise ResampleError(f"event {mapping.event_id} contains an inconsistent error_ms")
    if mapping.error_ms > max_error_ms + 1e-12:
        raise ResampleError(
            f"event {mapping.event_id} error {mapping.error_ms:.6f} ms exceeds {max_error_ms} ms"
        )
    if mapping.target_sample_drift > max_target_sample_drift + 1e-12:
        raise ResampleError(
            f"event {mapping.event_id} drift {mapping.target_sample_drift:.6f} samples exceeds "
            f"{max_target_sample_drift}"
        )


def map_event_samples(
    events: Sequence[tuple[str, int]], source_rate_hz: float, target_rate_hz: int = 250
) -> list[ResampledEvent]:
    mappings = [map_event_sample(event_id, index, source_rate_hz, target_rate_hz) for event_id, index in events]
    for mapping in mappings:
        validate_event_mapping(mapping)
    return mappings


def round_trip_time_error_ms(mapping: ResampledEvent) -> float:
    """Return the explicit target-time error kept in a mapping for audit reports."""
    return abs(mapping.target_time_s - mapping.event_time_s) * 1000.0


if __name__ == "__main__":
    raise SystemExit("Use this module through the M1 registry/evaluation workflow; no implicit data I/O is performed.")
