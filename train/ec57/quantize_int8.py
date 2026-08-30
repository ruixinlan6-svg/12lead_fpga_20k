"""Static symmetric INT8 post-training quantization (PTQ) for TinyECGCNN_NV (Section 1.3 & 3.3).

Implements:
  1. Per-channel symmetric weight quantization (signed INT8).
  2. Per-layer symmetric activation quantization (signed INT8).
  3. Bias quantization in INT32.
  4. Multiplier and right-shift decomposition: M = (s_in * s_w) / s_out.
  5. Exact hardware-matching requantization math with round-half-away-from-zero.
"""

import math
import numpy as np
from typing import Tuple, Dict, Any, List, Union

try:
    import torch
    import torch.nn as nn
except ImportError:
    torch = None
    nn = None


def decompose_multiplier_shift(real_scale: float, max_shift: int = 31) -> Tuple[int, int]:
    """
    Decomposes a real multiplier scale M into an integer multiplier M0 (in [0, 2^31 - 1])
    and a non-negative right shift n:
      M ≈ M0 * 2^(-n)
    """
    if real_scale <= 0.0:
        return 0, 0

    if real_scale >= 1.0:
        # Scale >= 1.0, e.g. 1.5 -> M0 = round(1.5 * 2^30), shift = 30
        shift = 30
        mult = int(math.floor(real_scale * (2.0 ** shift) + 0.5))
        while mult >= (1 << 31) and shift > 0:
            shift -= 1
            mult = int(math.floor(real_scale * (2.0 ** shift) + 0.5))
        return mult, shift

    # Scale < 1.0: find shift such that M0 is in [2^30, 2^31 - 1]
    # M = significand * 2^(exponent), with significand in [0.5, 1)
    significand, exponent = math.frexp(real_scale)
    # significand in [0.5, 1), so significand * 2^31 is in [2^30, 2^31)
    shift = 31 - exponent
    mult = int(math.floor(significand * (2.0 ** 31) + 0.5))

    # Clamp shift to max_shift if necessary
    if shift > max_shift:
        mult = mult >> (shift - max_shift)
        shift = max_shift

    return mult, shift


def requantize_integer(
    acc: Union[int, np.ndarray],
    mult: int,
    shift: int,
    relu: bool = False
) -> Union[int, np.ndarray]:
    """
    Hardware-identical integer requantization arithmetic:
      1. prod = acc * mult (signed 64-bit)
      2. round_term = (1 << (shift - 1)) if shift > 0 and prod >= 0
                      (1 << (shift - 1)) - 1 if shift > 0 and prod < 0
      3. scaled = (prod + round_term) >> shift
      4. optional ReLU: scaled = max(0, scaled)
      5. clamp to [-128, 127]
    """
    if isinstance(acc, (int, np.integer)):
        prod = int(acc) * int(mult)
        if shift == 0:
            round_term = 0
        else:
            if prod >= 0:
                round_term = 1 << (shift - 1)
            else:
                round_term = (1 << (shift - 1)) - 1

        prod_rounded = prod + round_term
        scaled = prod_rounded >> shift

        if relu and scaled < 0:
            scaled = 0

        if scaled > 127:
            return 127
        elif scaled < -128:
            return -128
        else:
            return int(scaled)
    else:
        acc_arr = np.asarray(acc, dtype=np.int64)
        prod = acc_arr * int(mult)
        if shift == 0:
            scaled = prod
        else:
            half = 1 << (shift - 1)
            round_term = np.where(prod >= 0, half, half - 1)
            prod_rounded = prod + round_term
            scaled = prod_rounded >> shift

        if relu:
            scaled = np.maximum(0, scaled)

        clamped = np.clip(scaled, -128, 127).astype(np.int8)
        return clamped


def quantize_tensor_symmetric_int8(tensor: np.ndarray) -> Tuple[np.ndarray, float]:
    """
    Symmetric per-tensor INT8 quantization:
      scale = max(|tensor|) / 127.0
      q_tensor = clip(round(tensor / scale), -128, 127)
    """
    max_val = float(np.max(np.abs(tensor)))
    if max_val == 0.0:
        scale = 1.0 / 127.0
        return np.zeros_like(tensor, dtype=np.int8), scale

    scale = max_val / 127.0
    scaled = tensor / scale
    # Round half away from zero
    rounded = np.where(scaled >= 0, np.floor(scaled + 0.5), np.ceil(scaled - 0.5))
    q_tensor = np.clip(rounded, -128, 127).astype(np.int8)
    return q_tensor, scale


def quantize_weights_per_channel(weights: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """
    Symmetric per-channel weight quantization for Conv1d and Linear:
      Output shape: [out_channels, in_channels, kernel_size] or [out_features, in_features]
      Returns: (quantized_int8_weights, scales_per_out_channel)
    """
    out_channels = weights.shape[0]
    q_weights = np.zeros_like(weights, dtype=np.int8)
    scales = np.zeros(out_channels, dtype=np.float64)

    for oc in range(out_channels):
        w_ch = weights[oc]
        max_val = float(np.max(np.abs(w_ch)))
        if max_val == 0.0:
            scale = 1.0 / 127.0
        else:
            scale = max_val / 127.0
        scales[oc] = scale

        scaled = w_ch / scale
        rounded = np.where(scaled >= 0, np.floor(scaled + 0.5), np.ceil(scaled - 0.5))
        q_weights[oc] = np.clip(rounded, -128, 127).astype(np.int8)

    return q_weights, scales
