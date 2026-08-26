#!/usr/bin/env python3
"""Fixed-shape TinyECGCNN INT8 reference used by the model-sized RTL smoke.

The script consumes private ``*.mem`` exports under a run directory.  It keeps
the graph explicit so a future streaming RTL implementation can compare every
buffer rather than only the final five logits.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np


QSHIFT = 31
QDEN = 1 << QSHIFT


def round_signed(num: int, den: int = QDEN) -> int:
    """Round a signed integer ratio half away from zero."""
    if num >= 0:
        return (num + den // 2) // den
    return -((-num + den // 2) // den)


def ratio(scale_in: float, scale_out: float) -> int:
    # The PyTorch PTQ model stores dequantized parameters and activations as
    # float32 tensors even though the contract is serialized as JSON doubles.
    # Reconstruct that effective scale before deriving a fixed-point ratio.
    in32 = float(np.float32(scale_in))
    out32 = float(np.float32(scale_out))
    return int(round(in32 / out32 * QDEN))


def clip8(value: int) -> np.int8:
    return np.int8(max(-128, min(127, value)))


def read_mem(path: Path, shape: tuple[int, ...]) -> np.ndarray:
    values = [int(line) for line in path.read_text(encoding="utf-8").split()]
    expected = int(np.prod(shape))
    if len(values) != expected:
        raise ValueError(f"{path}: expected {expected} values, got {len(values)}")
    if any(value < -128 or value > 127 for value in values):
        raise ValueError(f"{path}: value outside signed INT8 range")
    return np.asarray(values, dtype=np.int8).reshape(shape)


def conv1d_int8(
    signal: np.ndarray,
    weight: np.ndarray,
    bias: np.ndarray,
    input_scale: float,
    weight_scale: float,
    bias_scale: float,
    output_scale: float,
    padding: int,
) -> np.ndarray:
    channels, length = signal.shape
    out_channels, in_channels, kernel = weight.shape
    if channels != in_channels:
        raise ValueError("input/channel mismatch")
    output = np.zeros((out_channels, length), dtype=np.int8)
    product_multiplier = ratio(input_scale * weight_scale, output_scale)
    bias_multiplier = ratio(bias_scale, output_scale)
    padded = np.pad(signal.astype(np.int16), ((0, 0), (padding, padding)))
    for out_index in range(out_channels):
        for position in range(length):
            window = padded[:, position : position + kernel]
            acc = int(np.sum(window.astype(np.int64) * weight[out_index].astype(np.int64)))
            output[out_index, position] = clip8(
                round_signed(acc * product_multiplier + int(bias[out_index]) * bias_multiplier)
            )
    return output


def requantize(value: np.ndarray, input_scale: float, output_scale: float) -> np.ndarray:
    multiplier = ratio(input_scale, output_scale)
    result = np.empty(value.shape, dtype=np.int8)
    for index in np.ndindex(value.shape):
        result[index] = clip8(round_signed(int(value[index]) * multiplier))
    return result


def max_pool2(value: np.ndarray) -> np.ndarray:
    return value[:, ::2] if value.shape[1] % 2 else value.reshape(value.shape[0], -1, 2).max(axis=2)


def adaptive_average(value: np.ndarray, input_scale: float, output_scale: float) -> np.ndarray:
    multiplier = ratio(input_scale, output_scale)
    result = np.empty((value.shape[0],), dtype=np.int8)
    length = value.shape[1]
    for channel in range(value.shape[0]):
        # Keep the division in the fixed-point numerator so the operation is
        # deterministic and matches the RTL's integer accumulator.
        numerator = int(np.sum(value[channel].astype(np.int64))) * multiplier
        result[channel] = clip8(round_signed(numerator, QDEN * length))
    return result


def dense_int8(
    value: np.ndarray,
    weight: np.ndarray,
    bias: np.ndarray,
    input_scale: float,
    weight_scale: float,
    bias_scale: float,
    output_scale: float,
) -> np.ndarray:
    product_multiplier = ratio(input_scale * weight_scale, output_scale)
    bias_multiplier = ratio(bias_scale, output_scale)
    result = np.empty((weight.shape[0],), dtype=np.int8)
    for out_index in range(weight.shape[0]):
        acc = int(np.sum(value.astype(np.int64) * weight[out_index].astype(np.int64)))
        result[out_index] = clip8(
            round_signed(acc * product_multiplier + int(bias[out_index]) * bias_multiplier)
        )
    return result


def conv1d_float_quant(
    signal: np.ndarray,
    weight: np.ndarray,
    bias: np.ndarray,
    input_scale: float,
    weight_scale: float,
    bias_scale: float,
    output_scale: float,
    padding: int,
) -> np.ndarray:
    """Reference the PTQ evaluator's float32 dequantize/compute/requantize path."""
    channels, length = signal.shape
    out_channels, _in_channels, kernel = weight.shape
    result = np.zeros((out_channels, length), dtype=np.int8)
    padded = np.pad(signal.astype(np.float32) * np.float32(input_scale), ((0, 0), (padding, padding)))
    weight_f = weight.astype(np.float32) * np.float32(weight_scale)
    bias_f = bias.astype(np.float32) * np.float32(bias_scale)
    out_scale = np.float32(output_scale)
    for out_index in range(out_channels):
        for position in range(length):
            window = padded[:, position : position + kernel]
            value = np.sum(window * weight_f[out_index], dtype=np.float32) + bias_f[out_index]
            scaled = np.float32(value / out_scale)
            result[out_index, position] = clip8(int(np.floor(scaled + np.float32(0.5)) if scaled >= 0 else np.ceil(scaled - np.float32(0.5))))
    return result


def float_requantize(value: np.ndarray, input_scale: float, output_scale: float) -> np.ndarray:
    result = np.empty(value.shape, dtype=np.int8)
    scale = np.float32(input_scale)
    out_scale = np.float32(output_scale)
    for index in np.ndindex(value.shape):
        scaled = np.float32(np.float32(value[index]) * scale / out_scale)
        result[index] = clip8(int(np.floor(scaled + np.float32(0.5)) if scaled >= 0 else np.ceil(scaled - np.float32(0.5))))
    return result


def float_adaptive_average(value: np.ndarray, input_scale: float, output_scale: float) -> np.ndarray:
    scale = np.float32(input_scale)
    out_scale = np.float32(output_scale)
    result = np.empty((value.shape[0],), dtype=np.int8)
    for channel in range(value.shape[0]):
        averaged = np.mean(value[channel].astype(np.float32) * scale, dtype=np.float32)
        scaled = np.float32(averaged / out_scale)
        result[channel] = clip8(int(np.floor(scaled + np.float32(0.5)) if scaled >= 0 else np.ceil(scaled - np.float32(0.5))))
    return result


def float_dense_quant(value: np.ndarray, weight: np.ndarray, bias: np.ndarray, input_scale: float, weight_scale: float, bias_scale: float, output_scale: float) -> np.ndarray:
    result = np.empty((weight.shape[0],), dtype=np.int8)
    x = value.astype(np.float32) * np.float32(input_scale)
    w = weight.astype(np.float32) * np.float32(weight_scale)
    b = bias.astype(np.float32) * np.float32(bias_scale)
    out_scale = np.float32(output_scale)
    for out_index in range(weight.shape[0]):
        scaled = np.float32((np.sum(x * w[out_index], dtype=np.float32) + b[out_index]) / out_scale)
        result[out_index] = clip8(int(np.floor(scaled + np.float32(0.5)) if scaled >= 0 else np.ceil(scaled - np.float32(0.5))))
    return result


def sha256_array(value: np.ndarray) -> str:
    return hashlib.sha256(value.tobytes()).hexdigest()


def run(run_dir: Path, dump: bool = False, compare_path: Path | None = None) -> dict:
    mem = run_dir / "model_mem"
    meta = json.loads((mem / "meta.json").read_text(encoding="utf-8"))
    scales = meta["activation_scales"]
    input_q = read_mem(mem / "input.mem", (12, 1000))
    conv1_w = read_mem(mem / "features_0_weight.mem", (16, 12, 7))
    conv1_b = read_mem(mem / "features_0_bias.mem", (16,))
    conv2_w = read_mem(mem / "features_3_weight.mem", (32, 16, 7))
    conv2_b = read_mem(mem / "features_3_bias.mem", (32,))
    conv3_w = read_mem(mem / "features_6_weight.mem", (32, 32, 5))
    conv3_b = read_mem(mem / "features_6_bias.mem", (32,))
    head_w = read_mem(mem / "head_weight.mem", (5, 32))
    head_b = read_mem(mem / "head_bias.mem", (5,))

    c1 = conv1d_int8(input_q, conv1_w, conv1_b, scales["input"], meta["features.0.weight"]["scale"], meta["features.0.bias"]["scale"], scales["features.0"], 3)
    r1 = requantize(np.maximum(c1, 0), scales["features.0"], scales["features.1"])
    p1 = requantize(max_pool2(r1), scales["features.2"], scales["features.2"])
    c2 = conv1d_int8(p1, conv2_w, conv2_b, scales["features.2"], meta["features.3.weight"]["scale"], meta["features.3.bias"]["scale"], scales["features.3"], 3)
    r2 = requantize(np.maximum(c2, 0), scales["features.3"], scales["features.4"])
    p2 = requantize(max_pool2(r2), scales["features.4"], scales["features.5"])
    c3 = conv1d_int8(p2, conv3_w, conv3_b, scales["features.5"], meta["features.6.weight"]["scale"], meta["features.6.bias"]["scale"], scales["features.6"], 2)
    r3 = requantize(np.maximum(c3, 0), scales["features.6"], scales["features.7"])
    gap = adaptive_average(r3, scales["features.7"], scales["features.8"])
    logits_q = dense_int8(gap, head_w, head_b, scales["features.8"], meta["head.weight"]["scale"], meta["head.bias"]["scale"], scales["head"])
    fc1 = conv1d_float_quant(input_q, conv1_w, conv1_b, scales["input"], meta["features.0.weight"]["scale"], meta["features.0.bias"]["scale"], scales["features.0"], 3)
    fr1 = float_requantize(np.maximum(fc1, 0), scales["features.0"], scales["features.1"])
    fp1 = float_requantize(max_pool2(fr1), scales["features.2"], scales["features.2"])
    fc2 = conv1d_float_quant(fp1, conv2_w, conv2_b, scales["features.2"], meta["features.3.weight"]["scale"], meta["features.3.bias"]["scale"], scales["features.3"], 3)
    fr2 = float_requantize(np.maximum(fc2, 0), scales["features.3"], scales["features.4"])
    fp2 = float_requantize(max_pool2(fr2), scales["features.4"], scales["features.5"])
    fc3 = conv1d_float_quant(fp2, conv3_w, conv3_b, scales["features.5"], meta["features.6.weight"]["scale"], meta["features.6.bias"]["scale"], scales["features.6"], 2)
    fr3 = float_requantize(np.maximum(fc3, 0), scales["features.6"], scales["features.7"])
    fg = float_adaptive_average(fr3, scales["features.7"], scales["features.8"])
    fl = float_dense_quant(fg, head_w, head_b, scales["features.8"], meta["head.weight"]["scale"], meta["head.bias"]["scale"], scales["head"])
    float_buffers = {"conv1": fc1, "relu1": fr1, "pool1": fp1, "conv2": fc2, "relu2": fr2, "pool2": fp2, "conv3": fc3, "relu3": fr3, "gap": fg, "logits": fl}
    expected_q = read_mem(mem / "expected_logits.mem", (5,))
    buffers = {"input": input_q, "conv1": c1, "relu1": r1, "pool1": p1, "conv2": c2, "relu2": r2, "pool2": p2, "conv3": c3, "relu3": r3, "gap": gap, "logits": logits_q}
    comparison = {}
    if compare_path is not None:
        other = np.load(compare_path)
        mapping = {"conv1": "features.0", "relu1": "features.1", "pool1": "features.2", "conv2": "features.3", "relu2": "features.4", "pool2": "features.5", "conv3": "features.6", "relu3": "features.7", "gap": "features.8", "logits": "head"}
        for name, other_name in mapping.items():
            candidate = other[other_name].reshape(buffers[name].shape).astype(np.int16)
            delta = np.abs(buffers[name].astype(np.int16) - candidate)
            comparison[name] = {"max_abs": int(delta.max()), "equal": bool(np.array_equal(buffers[name], candidate))}
    float_comparison = {name: {"max_abs": int(np.max(np.abs(value.astype(np.int16) - buffers[name].astype(np.int16)))), "equal": bool(np.array_equal(value, buffers[name]))} for name, value in float_buffers.items()}
    if dump:
        np.savez(run_dir / "integer_buffers.npz", **buffers)
    return {"shapes": {name: list(value.shape) for name, value in buffers.items()}, "sha256": {name: sha256_array(value) for name, value in buffers.items()}, "logits_q": logits_q.astype(int).tolist(), "expected_logits_q": expected_q.astype(int).tolist(), "logits_equal": bool(np.array_equal(logits_q, expected_q)), "torch_comparison": comparison, "float_vs_integer": float_comparison}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--dump", action="store_true")
    parser.add_argument("--compare", type=Path)
    args = parser.parse_args()
    print(json.dumps(run(args.run_dir, dump=args.dump, compare_path=args.compare), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
