"""Beat dataset extraction and normalization for QN88 Twelve-Lead ECG (Section 1.3).

Handles:
  1. 160-sample window extraction [R - 64, R + 95] around R peak at 250 Hz.
  2. Median subtraction and robust percentile scaling to signed INT8 [-128, 127].
  3. Extraction and robust median/IQR normalization of 4 scalar auxiliary features.
  4. Exact round-half-away-from-zero integer quantization matching FPGA hardware.
"""

import math
import numpy as np
from dataclasses import dataclass
from typing import Tuple, Optional, Union, List


# 1 LSB = 5 uV in project contract; 100 uV floor = 20 LSB
MIN_SCALE_FLOOR_LSB = 20.0  # 100 uV / 5 uV/LSB = 20 LSB


def round_half_away_from_zero(val: Union[float, np.ndarray]) -> Union[int, np.ndarray]:
    """
    Symmetric rounding away from zero (standard commercial / integer arithmetic rounding).
    0.5 -> 1, -0.5 -> -1, 1.5 -> 2, -1.5 -> -2
    """
    if isinstance(val, (int, float)):
        if val >= 0:
            return int(math.floor(val + 0.5))
        else:
            return int(math.ceil(val - 0.5))
    else:
        # Vectorized numpy version
        arr = np.asarray(val, dtype=np.float64)
        out = np.where(arr >= 0, np.floor(arr + 0.5), np.ceil(arr - 0.5))
        return out.astype(np.int64)


@dataclass
class BeatWindowSpec:
    """Specification of the beat window geometry and sample rate."""
    sample_rate_hz: int = 250
    window_length: int = 160
    r_peak_index: int = 64
    pre_r_samples: int = 64   # 256 ms @ 250 Hz
    post_r_samples: int = 96  # 384 ms @ 250 Hz


def extract_beat_window(
    signal: np.ndarray,
    r_index: int,
    spec: BeatWindowSpec = BeatWindowSpec(),
    pad_mode: str = 'constant',
    pad_value: int = 0
) -> np.ndarray:
    """
    Extracts a 160-point window centered such that R-peak is at index 64.
    Range: [r_index - 64, r_index + 96).
    
    Pads with `pad_value` if near start or end of signal.
    """
    total_len = len(signal)
    start_idx = r_index - spec.pre_r_samples
    end_idx = r_index + spec.post_r_samples

    pad_left = max(0, -start_idx)
    pad_right = max(0, end_idx - total_len)

    actual_start = max(0, start_idx)
    actual_end = min(total_len, end_idx)

    slice_data = signal[actual_start:actual_end]

    if pad_left > 0 or pad_right > 0:
        window = np.pad(slice_data, (pad_left, pad_right), mode=pad_mode, constant_values=pad_value)
    else:
        window = slice_data.copy()

    return window.astype(signal.dtype)


def normalize_waveform_int8(
    raw_window: np.ndarray,
    scale_ref: float,
    min_floor_lsb: float = MIN_SCALE_FLOOR_LSB
) -> np.ndarray:
    """
    Normalizes a 160-point raw waveform to signed INT8 [-128, 127]:
      1. Subtract window median.
      2. Scale with max(min_floor_lsb, scale_ref) such that scale_ref -> 127.
      3. Round half away from zero.
      4. Clamp to [-128, 127].
    """
    median_val = np.median(raw_window)
    centered = raw_window.astype(np.float64) - median_val

    effective_scale = max(float(min_floor_lsb), float(scale_ref))
    scaled = (centered / effective_scale) * 127.0
    rounded = round_half_away_from_zero(scaled)

    clamped = np.clip(rounded, -128, 127).astype(np.int8)
    return clamped


def normalize_scalar_features_int8(
    raw_features: np.ndarray,
    medians: np.ndarray,
    iqrs: np.ndarray
) -> np.ndarray:
    """
    Normalizes 4 scalar auxiliary features to signed INT8 [-128, 127]:
      Formula: round_half_away_from_zero(32.0 * (x - median) / (IQR / 2.0))
    Raises ValueError if any IQR is zero.
    """
    raw_feat = np.asarray(raw_features, dtype=np.float64)
    med = np.asarray(medians, dtype=np.float64)
    iqr = np.asarray(iqrs, dtype=np.float64)

    if np.any(iqr <= 0):
        zero_indices = np.where(iqr <= 0)[0]
        raise ValueError(f"Feature IQR cannot be zero or negative! Indices: {zero_indices}")

    half_iqr = iqr / 2.0
    scaled = 32.0 * (raw_feat - med) / half_iqr
    rounded = round_half_away_from_zero(scaled)

    clamped = np.clip(rounded, -128, 127).astype(np.int8)
    return clamped
