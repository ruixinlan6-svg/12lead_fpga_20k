"""Deterministic QRS reference with independent float/fixed paths."""

from __future__ import annotations

import math
import statistics
import cmath
from dataclasses import dataclass
from typing import Sequence


CANONICAL_LEADS = ("I", "II", "III", "aVR", "aVL", "aVF", "V1", "V2", "V3", "V4", "V5", "V6")

QRS_CONFIG = {
    "sample_rate_hz": 250,
    "bandpass_hz": (5.0, 25.0),
    "derivative_kernel": (-1, -2, 0, 2, 1),
    "derivative_divisor": 8,
    "moving_integrator_length_samples": 30,
    "refractory_period_samples": 50,
    "refractory_period_ms": 200,
    "searchback_rr_multiplier": 1.66,
    "searchback_rr_history_length": 8,
    "lead_vote_window_samples": 20,
}

Q14 = 1 << 14
INT24_MIN = -(1 << 23)
INT24_MAX = (1 << 23) - 1
INT40_MIN = -(1 << 39)
INT40_MAX = (1 << 39) - 1


class QRSReferenceError(ValueError):
    """Raised for an invalid QRS reference configuration or input."""


class StreamIntegrityError(QRSReferenceError):
    """Raised for missing, duplicate, or out-of-order sample indices."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class QRS_Candidate:
    index: int
    strength: float
    primary: bool


@dataclass(frozen=True)
class QRSResult:
    peak_indices: list[int]
    candidates: list[QRS_Candidate]
    searchback_indices: list[int]
    error_state: str | None = None


@dataclass(frozen=True)
class FusedQRSResult:
    peak_indices: list[int]
    status: str
    selected_leads: list[str]


def _round_half_away_from_zero(value: float) -> int:
    if value < 0:
        return -math.floor(abs(value) + 0.5)
    return math.floor(value + 0.5)


def design_butterworth_bandpass_sos(
    sample_rate_hz: int = 250, low_hz: float = 5.0, high_hz: float = 25.0, order: int = 4
) -> tuple[tuple[float, float, float, float, float], ...]:
    """Design digital Butterworth band-pass SOS coefficients without SciPy.

    The analog Butterworth prototype is frequency transformed with prewarped
    bilinear frequencies.  The returned sections use the direct-form
    convention ``b0 + b1 z^-1 + b2 z^-2`` over
    ``1 + a1 z^-1 + a2 z^-2``.
    """
    if sample_rate_hz != 250 or order != 4 or not 0 < low_hz < high_hz < sample_rate_hz / 2:
        raise QRSReferenceError("only the frozen 250 Hz, 5-25 Hz, fourth-order QRS filter is supported")
    warped_low = 2.0 * sample_rate_hz * math.tan(math.pi * low_hz / sample_rate_hz)
    warped_high = 2.0 * sample_rate_hz * math.tan(math.pi * high_hz / sample_rate_hz)
    bandwidth = warped_high - warped_low
    center = math.sqrt(warped_low * warped_high)
    prototype_poles = [
        cmath.exp(1j * math.pi * (2 * index + order + 1) / (2 * order))
        for index in range(order)
    ]
    analog_poles: list[complex] = []
    for pole in prototype_poles:
        discriminant = (bandwidth * pole) ** 2 - 4.0 * center * center
        root = cmath.sqrt(discriminant)
        analog_poles.extend(((bandwidth * pole + root) / 2.0, (bandwidth * pole - root) / 2.0))
    digital_poles = [
        (2.0 * sample_rate_hz + pole) / (2.0 * sample_rate_hz - pole) for pole in analog_poles
    ]
    remaining = list(digital_poles)
    pole_pairs: list[tuple[complex, complex]] = []
    while remaining:
        pole = remaining.pop(0)
        partner_index = min(range(len(remaining)), key=lambda index: abs(remaining[index] - pole.conjugate()))
        partner = remaining.pop(partner_index)
        pole_pairs.append((pole, partner))
    sections: list[list[float]] = []
    for pole_a, pole_b in pole_pairs:
        a1 = float((-pole_a - pole_b).real)
        a2 = float((pole_a * pole_b).real)
        sections.append([1.0, 0.0, -1.0, a1, a2])
    center_angle = 2.0 * math.pi * math.sqrt(low_hz * high_hz) / sample_rate_hz
    z_inverse = cmath.exp(-1j * center_angle)
    response = 1.0 + 0.0j
    for b0, b1, b2, a1, a2 in sections:
        response *= (b0 + b1 * z_inverse + b2 * z_inverse * z_inverse) / (
            1.0 + a1 * z_inverse + a2 * z_inverse * z_inverse
        )
    if abs(response) < 1e-15:
        raise QRSReferenceError("Butterworth band-pass normalization failed")
    gain = 1.0 / abs(response)
    per_section_gain = gain ** (1.0 / len(sections))
    for section in sections:
        section[0] *= per_section_gain
        section[1] *= per_section_gain
        section[2] *= per_section_gain
    return tuple(tuple(section) for section in sections)


QRS_SOS_FLOAT = design_butterworth_bandpass_sos()
QRS_SOS_Q2_14 = tuple(
    tuple(_round_half_away_from_zero(coefficient * Q14) for coefficient in section)
    for section in QRS_SOS_FLOAT
)


def _saturate_int24(value: int) -> int:
    return min(max(value, INT24_MIN), INT24_MAX)


def saturate_int40(value: int) -> int:
    """Clamp an intermediate to the signed 40-bit RTL accumulator range."""
    return min(max(int(value), INT40_MIN), INT40_MAX)


def qrs_filter_float(signal: Sequence[float]) -> list[float]:
    """Apply the frozen 5-25 Hz fourth-order floating-point SOS filter."""
    values = [float(value) for value in signal]
    for b0, b1, b2, a1, a2 in QRS_SOS_FLOAT:
        x1 = x2 = y1 = y2 = 0.0
        filtered: list[float] = []
        for value in values:
            output = b0 * value + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2
            filtered.append(output)
            x2, x1 = x1, value
            y2, y1 = y1, output
        values = filtered
    return values


def qrs_filter_fixed(signal: Sequence[int]) -> list[int]:
    """Apply Q2.14 SOS sections with 40-bit-style arithmetic and int24 saturation."""
    values: list[int] = []
    for value in signal:
        if not isinstance(value, int) or isinstance(value, bool):
            raise QRSReferenceError("fixed QRS filter requires integer samples")
        values.append(value)
    for b0, b1, b2, a1, a2 in QRS_SOS_Q2_14:
        x1 = x2 = y1 = y2 = 0
        filtered: list[int] = []
        for value in values:
            accumulator = saturate_int40(b0 * value + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2)
            if accumulator >= 0:
                output = (accumulator + Q14 // 2) // Q14
            else:
                output = -((-accumulator + Q14 // 2) // Q14)
            output = _saturate_int24(output)
            filtered.append(output)
            x2, x1 = x1, value
            y2, y1 = y1, output
        values = filtered
    return values


def validate_sample_index_stream(sample_indices: Sequence[int]) -> None:
    if not sample_indices:
        return
    previous = sample_indices[0]
    if not isinstance(previous, int) or isinstance(previous, bool):
        raise StreamIntegrityError("INVALID_SAMPLE_INDEX", "sample index must be an integer")
    for current in sample_indices[1:]:
        if not isinstance(current, int) or isinstance(current, bool):
            raise StreamIntegrityError("INVALID_SAMPLE_INDEX", "sample index must be an integer")
        if current == previous:
            raise StreamIntegrityError("DUPLICATE_SAMPLE", f"sample index repeated: {current}")
        if current < previous:
            raise StreamIntegrityError("OUT_OF_ORDER_SAMPLE", f"sample index decreased: {previous}->{current}")
        if current > previous + 1:
            raise StreamIntegrityError("MISSING_SAMPLE", f"sample gap: {previous}->{current}")
        previous = current


def _validate_signal(signal: Sequence[float | int], sample_rate_hz: int) -> list[float | int]:
    if sample_rate_hz != 250:
        raise QRSReferenceError("INVALID_SAMPLING_RATE: QRS reference requires 250 Hz")
    values = list(signal)
    if len(values) < 5:
        raise QRSReferenceError("INVALID_WINDOW: QRS reference requires at least five samples")
    return values


def _moving_integral_float(values: Sequence[float]) -> list[float]:
    derivative_squared: list[float] = [0.0] * len(values)
    for index in range(2, len(values) - 2):
        derivative = (-values[index - 2] - 2.0 * values[index - 1] + 2.0 * values[index + 1] + values[index + 2]) / 8.0
        derivative_squared[index] = derivative * derivative
    integral: list[float] = []
    running = 0.0
    window = QRS_CONFIG["moving_integrator_length_samples"]
    for index, value in enumerate(derivative_squared):
        running += value
        if index >= window:
            running -= derivative_squared[index - window]
        integral.append(running / min(index + 1, window))
    return integral


def _moving_integral_fixed(values: Sequence[int]) -> list[int]:
    derivative_squared: list[int] = [0] * len(values)
    for index in range(2, len(values) - 2):
        numerator = -values[index - 2] - 2 * values[index - 1] + 2 * values[index + 1] + values[index + 2]
        derivative = abs(numerator) // QRS_CONFIG["derivative_divisor"]
        if numerator < 0:
            derivative = -derivative
        derivative_squared[index] = saturate_int40(derivative * derivative)
    integral: list[int] = []
    running = 0
    window = QRS_CONFIG["moving_integrator_length_samples"]
    for index, value in enumerate(derivative_squared):
        running = saturate_int40(running + value)
        if index >= window:
            running = saturate_int40(running - derivative_squared[index - window])
        divisor = min(index + 1, window)
        integral.append(running // divisor)
    return integral


def qrs_energy_float(signal: Sequence[float]) -> list[float]:
    """Expose the floating-point bandpass/derivative/square/integration stage."""
    if len(signal) < 5:
        raise QRSReferenceError("QRS energy requires at least five samples")
    return _moving_integral_float(qrs_filter_float([float(value) for value in signal]))


def qrs_energy_fixed(signal: Sequence[int]) -> list[int]:
    """Expose the integer bandpass/derivative/square/integration stage."""
    if len(signal) < 5:
        raise QRSReferenceError("QRS energy requires at least five samples")
    if any((not isinstance(value, int) or isinstance(value, bool)) for value in signal):
        raise QRSReferenceError("fixed QRS energy requires integer samples")
    return _moving_integral_fixed(qrs_filter_fixed(list(signal)))


def _energy_local_maxima(energy: Sequence[float | int]) -> list[int]:
    return [
        index
        for index in range(1, len(energy) - 1)
        if energy[index] > 0 and energy[index] >= energy[index - 1] and energy[index] > energy[index + 1]
    ]


def _energy_representatives(energy: Sequence[float | int]) -> list[int]:
    """Collapse integrator ripples while retaining an early and strongest edge.

    A 30-sample moving integrator can create several local maxima for one QRS.
    Keeping both the first and strongest maximum preserves deterministic
    refractory behavior when two true pulses are closer than 200 ms, while
    preventing the ripple tail from becoming a later false QRS.
    """
    maxima = _energy_local_maxima(energy)
    if not maxima:
        return []
    clusters: list[list[int]] = [[maxima[0]]]
    max_gap = QRS_CONFIG["moving_integrator_length_samples"]
    for index in maxima[1:]:
        if index - clusters[-1][0] <= max_gap:
            clusters[-1].append(index)
        else:
            clusters.append([index])
    representatives: list[int] = []
    for cluster in clusters:
        first = cluster[0]
        strongest = max(cluster, key=lambda index: (energy[index], -index))
        representatives.append(first)
        if strongest != first:
            representatives.append(strongest)
    return sorted(representatives)


def _raw_timestamp(values: Sequence[float | int], energy_index: int) -> int:
    """Compensate the causal filter/integrator delay using the raw local peak."""
    start = max(1, energy_index - 45)
    stop = min(len(values) - 1, energy_index + 1)
    return max(range(start, stop), key=lambda index: (abs(values[index]), -index))


def _adaptive_candidates(
    values: Sequence[float | int], energy: Sequence[float | int]
) -> list[QRS_Candidate]:
    """Classify integrated-energy maxima with adaptive signal/noise levels.

    The raw waveform is used only to compensate timestamp delay after an
    energy decision; it is never the primary decision threshold.
    """
    maxima = _energy_representatives(energy)
    if not maxima:
        return []
    strengths = [float(energy[index]) for index in maxima]
    signal_level = max(strengths)
    noise_level = min(statistics.median(strengths), signal_level * 0.02)
    if noise_level >= signal_level:
        noise_level = 0.0
    candidates: list[QRS_Candidate] = []
    for energy_index in maxima:
        strength = float(energy[energy_index])
        threshold = noise_level + 0.08 * max(signal_level - noise_level, 0.0)
        primary = strength >= max(threshold, 1e-12)
        if primary:
            signal_level = 0.875 * signal_level + 0.125 * strength
        else:
            noise_level = 0.875 * noise_level + 0.125 * strength
        # Keep meaningful sub-threshold peaks for deterministic searchback.
        if primary or strength >= max(noise_level, threshold * 0.5, 1e-12):
            candidates.append(
                QRS_Candidate(
                    index=_raw_timestamp(values, energy_index),
                    strength=strength,
                    primary=primary,
                )
            )
    # Multiple energy ripples may compensate to the same raw R peak.
    deduplicated: dict[int, QRS_Candidate] = {}
    for candidate in candidates:
        previous = deduplicated.get(candidate.index)
        if previous is None or (candidate.primary, candidate.strength) > (previous.primary, previous.strength):
            deduplicated[candidate.index] = candidate
    return [deduplicated[index] for index in sorted(deduplicated)]


class CausalPureIntegerQRSDetector:
    """Strictly causal, pure-integer streaming QRS detector for FPGA reference."""

    def __init__(self, sample_rate_hz: int = 250):
        if sample_rate_hz != 250:
            raise QRSReferenceError("Causal integer detector requires 250 Hz")
        # 4 cascaded SOS sections state: (x1, x2, y1, y2)
        self.sections: list[list[int]] = [[0, 0, 0, 0] for _ in range(4)]
        # 5-tap derivative buffer of filtered signal
        self.filt_buf: list[int] = [0] * 5
        # 30-sample MWI ring buffer and accumulator
        self.mwi_buf: list[int] = [0] * 30
        self.mwi_ptr: int = 0
        self.mwi_sum: int = 0
        # 3-tap MWI output history for local peak detection
        self.mwi_0: int = 0
        self.mwi_1: int = 0
        self.mwi_2: int = 0
        # Rolling raw sample buffer for timestamp delay compensation (up to 64 samples)
        self.raw_buf: list[int] = []
        self.sample_idx: int = 0
        # Adaptive integer threshold tracking
        self.signal_level: int = 1000
        self.noise_level: int = 20
        # Peak and candidate tracking
        self.candidates: list[QRS_Candidate] = []
        self.accepted_peaks: list[int] = []
        self.searchback_indices: list[int] = []
        self.rr_history: list[int] = []
        self.last_cand_sample: int = -100
        self.last_peak_sample: int = -500
        self.last_qrs_slope: int = 500
        # A simultaneous searchback/current-primary collision is serialized so
        # the one-event-per-clock streaming interface never drops an event.
        self.pending_primary: tuple[QRS_Candidate, int] | None = None
        # Saturation counters for RTL accounting
        self.saturation_events: dict[str, int] = {"sos": 0, "derivative": 0, "mwi": 0}

    def step(self, raw_sample: int) -> int | None:
        """Process a single integer sample causally."""
        if not isinstance(raw_sample, int) or isinstance(raw_sample, bool):
            raise QRSReferenceError("Causal integer QRS requires integer input samples")
        n = self.sample_idx
        self.sample_idx += 1

        self.raw_buf.append(raw_sample)
        if len(self.raw_buf) > 64:
            self.raw_buf.pop(0)

        # 1. Four-Stage Cascaded Q2.14 SOS Biquads
        curr_in = raw_sample
        for k in range(4):
            b0, b1, b2, a1, a2 = QRS_SOS_Q2_14[k]
            x1, x2, y1, y2 = self.sections[k]
            acc = b0 * curr_in + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2
            sat_acc = saturate_int40(acc)
            if sat_acc != acc:
                self.saturation_events["sos"] += 1
            if sat_acc >= 0:
                y = (sat_acc + Q14 // 2) // Q14
            else:
                y = -((-sat_acc + Q14 // 2) // Q14)
            sat_y = _saturate_int24(y)
            if sat_y != y:
                self.saturation_events["sos"] += 1
            self.sections[k] = [curr_in, x1, sat_y, y1]
            curr_in = sat_y

        filtered_out = curr_in

        # 2. Derivative (5-tap central difference)
        self.filt_buf.append(filtered_out)
        self.filt_buf.pop(0)
        num = -self.filt_buf[0] - 2 * self.filt_buf[1] + 2 * self.filt_buf[3] + self.filt_buf[4]
        d = abs(num) // QRS_CONFIG["derivative_divisor"]
        if num < 0:
            d = -d
        sat_d = _saturate_int24(d)
        if sat_d != d:
            self.saturation_events["derivative"] += 1

        # 3. Square
        sq = saturate_int40(sat_d * sat_d)

        # 4. Moving Window Integrator (30-sample sliding sum)
        old_sq = self.mwi_buf[self.mwi_ptr]
        self.mwi_buf[self.mwi_ptr] = sq
        self.mwi_ptr = (self.mwi_ptr + 1) % 30
        new_sum = self.mwi_sum + sq - old_sq
        sat_sum = saturate_int40(new_sum)
        if sat_sum != new_sum:
            self.saturation_events["mwi"] += 1
        self.mwi_sum = sat_sum
        divisor = min(n + 1, 30)
        mwi_out = self.mwi_sum // divisor

        # Shift 3-tap MWI output history
        self.mwi_2 = self.mwi_1
        self.mwi_1 = self.mwi_0
        self.mwi_0 = mwi_out

        detected_peak: int | None = None

        if self.pending_primary is not None:
            pending, pending_peak_sample = self.pending_primary
            self.pending_primary = None
            if not self.accepted_peaks or pending.index - self.accepted_peaks[-1] >= 50:
                self.accepted_peaks.append(pending.index)
                self.last_peak_sample = pending_peak_sample
                if len(self.accepted_peaks) >= 2:
                    self.rr_history.append(self.accepted_peaks[-1] - self.accepted_peaks[-2])
                    if len(self.rr_history) > 8:
                        self.rr_history.pop(0)
                detected_peak = pending.index

        # Threshold decay on prolonged absence of QRS (> 1.2s / 300 samples)
        if n - self.last_peak_sample > 300:
            if self.signal_level > max(self.noise_level * 2, 48):
                self.signal_level = (self.signal_level * 63) >> 6

        # Causal Searchback: recover missed weak beats when gap >= 1.66 * median RR
        if detected_peak is None and len(self.rr_history) >= 1:
            hist = sorted(self.rr_history[-8:])
            mid = len(hist) // 2
            median_rr = hist[mid] if len(hist) % 2 == 1 else (hist[mid - 1] + hist[mid]) // 2
            if median_rr >= 50 and (n - self.last_peak_sample) * 100 >= 166 * median_rr:
                # Look back in candidates buffer for sub-threshold peaks
                eligible = [
                    c for c in self.candidates
                    if c.index >= self.last_peak_sample + 50
                    and c.index < n
                    and c.index not in self.accepted_peaks
                    and c.strength >= max(self.noise_level, 1)
                ]
                if eligible:
                    best_c = max(eligible, key=lambda c: (c.strength, -c.index))
                    self.accepted_peaks.append(best_c.index)
                    self.searchback_indices.append(best_c.index)
                    self.last_peak_sample = best_c.index
                    if len(self.accepted_peaks) >= 2:
                        self.rr_history.append(self.accepted_peaks[-1] - self.accepted_peaks[-2])
                        if len(self.rr_history) > 8:
                            self.rr_history.pop(0)
                    self.signal_level = (self.signal_level * 7 + best_c.strength) >> 3
                    detected_peak = best_c.index

        # 5. Causal Peak Detection: check if sample n-1 was a local maximum
        if self.mwi_1 > 0 and self.mwi_1 >= self.mwi_2 and self.mwi_1 > self.mwi_0:
            peak_sample = n - 1
            peak_energy = self.mwi_1

            # Dynamic floor to suppress baseline drift ripples
            dyn_floor = max((self.noise_level * 3) >> 1, 16)
            base_thresh = self.noise_level + (((max(self.signal_level - self.noise_level, 0)) * 20) >> 8)
            thresh = max(base_thresh, dyn_floor)

            # T-wave refractory window (50..95 samples post-R): require higher threshold
            if 50 <= peak_sample - self.last_peak_sample <= 95:
                t_wave_thresh = max(thresh, self.signal_level >> 1)
                primary = peak_energy >= t_wave_thresh
            else:
                primary = peak_energy >= thresh

            # Integer state update: (level * 7 + energy) >> 3
            if primary:
                self.signal_level = (self.signal_level * 7 + peak_energy) >> 3
            else:
                self.noise_level = (self.noise_level * 7 + peak_energy) >> 3

            # Retain sub-threshold peak if above secondary threshold
            if primary or peak_energy >= max(self.noise_level, thresh // 2, 1):
                # Timestamp compensation in raw buffer
                best_raw_idx = peak_sample
                max_abs_raw = -1
                buf_len = len(self.raw_buf)
                for look_back in range(min(buf_len, 48)):
                    s_idx = n - look_back
                    if peak_sample - 45 <= s_idx <= peak_sample:
                        val = abs(self.raw_buf[buf_len - 1 - look_back])
                        if val > max_abs_raw or (val == max_abs_raw and s_idx < best_raw_idx):
                            max_abs_raw = val
                            best_raw_idx = s_idx

                cand = QRS_Candidate(index=best_raw_idx, strength=peak_energy, primary=primary)
                # 30-sample ripple clustering
                if peak_sample - self.last_cand_sample <= 30 and self.candidates:
                    if peak_energy > self.candidates[-1].strength:
                        if not self.accepted_peaks or self.accepted_peaks[-1] != self.candidates[-1].index:
                            self.candidates[-1] = cand
                else:
                    self.candidates.append(cand)
                    self.last_cand_sample = peak_sample
                    # Startup protection (first 100 samples): require established signal or strong peak
                    if n >= 100 or (primary and peak_energy > 400):
                        # Refractory period check: 50 samples = 200 ms
                        if not self.accepted_peaks or (best_raw_idx - self.accepted_peaks[-1] >= 50):
                            if primary:
                                if detected_peak is None:
                                    self.accepted_peaks.append(best_raw_idx)
                                    self.last_peak_sample = peak_sample
                                    if len(self.accepted_peaks) >= 2:
                                        self.rr_history.append(self.accepted_peaks[-1] - self.accepted_peaks[-2])
                                        if len(self.rr_history) > 8:
                                            self.rr_history.pop(0)
                                    detected_peak = best_raw_idx
                                else:
                                    self.pending_primary = (cand, peak_sample)

        return detected_peak

    def feed_chunk(self, samples: Sequence[int]) -> list[int]:
        """Feed a sequence of samples and return all committed peaks in order."""
        emitted: list[int] = []
        for s in samples:
            peak = self.step(s)
            if peak is not None:
                emitted.append(peak)
        return emitted

    def get_result(self) -> QRSResult:
        """Return the final immutable QRSResult."""
        return QRSResult(
            peak_indices=list(self.accepted_peaks),
            candidates=list(self.candidates),
            searchback_indices=list(self.searchback_indices),
        )


def get_fixed_qrs_rtl_parameters() -> dict[str, object]:
    """Export Q2.14 SOS and arithmetic parameters for Gowin RTL bit-exact verification."""
    return {
        "sample_rate_hz": 250,
        "q_format": "Q2.14",
        "scale_factor_q14": Q14,
        "sos_sections_q14": [list(sec) for sec in QRS_SOS_Q2_14],
        "sos_sections_float": [list(sec) for sec in QRS_SOS_FLOAT],
        "derivative_divisor": QRS_CONFIG["derivative_divisor"],
        "mwi_length_samples": QRS_CONFIG["moving_integrator_length_samples"],
        "refractory_period_samples": QRS_CONFIG["refractory_period_samples"],
        "decay_shift": 3,
        "decay_weight_old": 7,
        "decay_weight_new": 1,
        "threshold_fraction_num": 20,
        "threshold_fraction_den_shift": 8,
    }


def _local_candidates_float(values: Sequence[float]) -> list[QRS_Candidate]:
    return _adaptive_candidates(values, qrs_energy_float(values))


def _local_candidates_fixed(values: Sequence[int]) -> list[QRS_Candidate]:
    detector = CausalPureIntegerQRSDetector()
    detector.feed_chunk(values)
    return detector.candidates


def apply_refractory_and_searchback_float(
    candidates: Sequence[QRS_Candidate],
    *,
    rr_history: Sequence[float] = (),
) -> list[int]:
    """Apply 50-sample refractory suppression and 1.66x median-RR searchback."""
    ordered = sorted(candidates, key=lambda candidate: candidate.index)
    accepted: list[QRS_Candidate] = []
    for candidate in ordered:
        if not candidate.primary:
            continue
        if accepted and candidate.index - accepted[-1].index < QRS_CONFIG["refractory_period_samples"]:
            continue
        accepted.append(candidate)
    history = [float(value) for value in rr_history if float(value) > 0]
    if not history:
        history = [float(accepted[index].index - accepted[index - 1].index) for index in range(1, len(accepted))]
    history = history[-QRS_CONFIG["searchback_rr_history_length"] :]
    median_rr = statistics.median(history) if history else None
    if median_rr is None:
        return [candidate.index for candidate in accepted]
    inserted: list[QRS_Candidate] = []
    accepted_with_searchback = list(accepted)
    for left, right in zip(accepted, accepted[1:]):
        if right.index - left.index <= 1.66 * median_rr:
            continue
        weak = [
            candidate
            for candidate in ordered
            if left.index + QRS_CONFIG["refractory_period_samples"] <= candidate.index < right.index
            and not candidate.primary
        ]
        weak.sort(key=lambda candidate: (-candidate.strength, candidate.index))
        if weak:
            selected = weak[0]
            accepted_with_searchback.append(selected)
            inserted.append(selected)
    return [candidate.index for candidate in sorted(accepted_with_searchback, key=lambda candidate: candidate.index)]


def apply_refractory_and_searchback_fixed(
    candidates: Sequence[QRS_Candidate],
    *,
    rr_history: Sequence[int] = (),
) -> list[int]:
    """Pure integer refractory and searchback policy."""
    ordered = sorted(candidates, key=lambda candidate: candidate.index)
    accepted: list[QRS_Candidate] = []
    for candidate in ordered:
        if not candidate.primary:
            continue
        if accepted and candidate.index - accepted[-1].index < 50:
            continue
        accepted.append(candidate)
    history = [int(value) for value in rr_history if int(value) > 0]
    if not history:
        history = [accepted[index].index - accepted[index - 1].index for index in range(1, len(accepted))]
    history = history[-8:]
    if not history:
        return [candidate.index for candidate in accepted]
    ordered_history = sorted(history)
    middle = len(ordered_history) // 2
    if len(ordered_history) % 2:
        median_rr = ordered_history[middle]
    else:
        median_rr = (ordered_history[middle - 1] + ordered_history[middle]) // 2
    result = list(accepted)
    for left, right in zip(accepted, accepted[1:]):
        gap = right.index - left.index
        if gap * 100 <= 166 * median_rr:
            continue
        weak = [
            candidate
            for candidate in ordered
            if left.index + 50 <= candidate.index < right.index and not candidate.primary
        ]
        if weak:
            selected = sorted(weak, key=lambda candidate: (-candidate.strength, candidate.index))[0]
            result.append(selected)
    return [candidate.index for candidate in sorted(result, key=lambda candidate: candidate.index)]


def fuse_qrs_leads(
    peaks_by_lead: dict[str, Sequence[int]],
    selected_leads: Sequence[str],
    *,
    sample_rate_hz: int = 250,
) -> FusedQRSResult:
    """Fuse selected-lead QRS events using the frozen 2-of-3/80 ms rule."""
    if sample_rate_hz != 250:
        raise QRSReferenceError("INVALID_SAMPLING_RATE: lead voting requires 250 Hz")
    leads = list(dict.fromkeys(str(lead) for lead in selected_leads))
    if not leads:
        return FusedQRSResult([], "SIGNAL_LOSS", [])
    for lead in leads:
        if lead not in CANONICAL_LEADS:
            raise QRSReferenceError(f"INVALID_LEAD: {lead!r} is not a canonical lead")
    if len(leads) == 1:
        return FusedQRSResult(sorted(dict.fromkeys(int(index) for index in peaks_by_lead.get(leads[0], ()))), "DEGRADED_ONE_LEAD", leads)

    vote_window = QRS_CONFIG["lead_vote_window_samples"]
    events = sorted(
        (int(index), lead)
        for lead in leads[:3]
        for index in peaks_by_lead.get(lead, ())
    )
    used: set[tuple[int, str]] = set()
    fused: list[int] = []
    for anchor_index, anchor_lead in events:
        if (anchor_index, anchor_lead) in used:
            continue
        cluster: list[tuple[int, str]] = []
        seen_leads: set[str] = set()
        for index, lead in events:
            if (index, lead) in used or lead in seen_leads:
                continue
            if anchor_index <= index <= anchor_index + vote_window:
                cluster.append((index, lead))
                seen_leads.add(lead)
        if len(cluster) < 2:
            continue
        indices = sorted(index for index, _ in cluster)
        middle = len(indices) // 2
        if len(indices) % 2:
            fused_index = indices[middle]
        else:
            fused_index = (indices[middle - 1] + indices[middle] + 1) // 2
        fused.append(fused_index)
        used.update(cluster)
    return FusedQRSResult(fused, "FULL_12_LEAD", leads[:3])


def detect_qrs_float(signal: Sequence[float], sample_rate_hz: int = 250) -> QRSResult:
    """Execute independent floating-point QRS algorithmic reference."""
    values = [float(v) for v in _validate_signal(signal, sample_rate_hz)]
    candidates = _local_candidates_float(values)
    peaks = apply_refractory_and_searchback_float(candidates)
    return QRSResult(peak_indices=peaks, candidates=candidates, searchback_indices=[])


def detect_qrs_fixed(signal: Sequence[int], sample_rate_hz: int = 250) -> QRSResult:
    """Execute strictly causal, pure-integer streaming QRS detection."""
    values = _validate_signal(signal, sample_rate_hz)
    detector = CausalPureIntegerQRSDetector(sample_rate_hz=sample_rate_hz)
    for value in values:
        if not isinstance(value, int) or isinstance(value, bool):
            raise QRSReferenceError("fixed QRS input must contain integer samples")
        detector.step(value)
    return detector.get_result()
