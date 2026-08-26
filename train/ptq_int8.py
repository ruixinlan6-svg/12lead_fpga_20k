#!/usr/bin/env python3
"""Small, explicit static-INT8 PTQ reference for TinyECGCNN.

This is an integration artifact, not a clinical benchmark.  It uses per-tensor
symmetric scales and sign-symmetric nearest rounding so the quantizer agrees
with fpga/rtl/requantize_clip.sv.  Weights are stored as INT8 plus scales; the
evaluation model dequantizes them and fake-quantizes calibrated activations.
"""

from __future__ import annotations

import argparse
import copy
import json
import pathlib
import sys
from typing import Any

import numpy as np
import torch
from torch import nn

from ptbxl_baseline import LABELS, PTBXL, TinyECGCNN, evaluate, file_sha256, set_seed


def symmetric_round(value: torch.Tensor) -> torch.Tensor:
    return torch.where(value >= 0, torch.floor(value + 0.5), torch.ceil(value - 0.5))


def quantize(value: torch.Tensor, scale: float) -> torch.Tensor:
    return torch.clamp(symmetric_round(value / scale), -128, 127).to(torch.int8)


def scale_for(value: torch.Tensor) -> float:
    peak = float(value.detach().abs().max().cpu())
    return max(peak / 127.0, 1e-8)


def fake_quant(value: torch.Tensor, scale: float) -> torch.Tensor:
    return quantize(value, scale).to(value.dtype) * scale


def calibration_scales(model: nn.Module, loader: list[tuple[torch.Tensor, torch.Tensor]]) -> dict[str, float]:
    maxima: dict[str, float] = {"input": 0.0}
    hooks = []

    def observe(name: str):
        def hook(_module: nn.Module, _inputs: tuple[Any, ...], output: Any):
            if isinstance(output, torch.Tensor):
                maxima[name] = max(maxima.get(name, 0.0), float(output.detach().abs().max().cpu()))
            return output

        return hook

    for name, module in model.named_modules():
        if isinstance(module, (nn.Conv1d, nn.ReLU, nn.MaxPool1d, nn.AdaptiveAvgPool1d, nn.Linear)):
            hooks.append(module.register_forward_hook(observe(name)))
    model.eval()
    with torch.no_grad():
        for signal, _target in loader:
            maxima["input"] = max(maxima["input"], float(signal.abs().max()))
            model(signal)
    for hook in hooks:
        hook.remove()
    return {name: max(value / 127.0, 1e-8) for name, value in maxima.items()}


def quantized_eval_model(model: TinyECGCNN, activation_scales: dict[str, float], weight_scales: dict[str, float]) -> nn.Module:
    quantized = copy.deepcopy(model).cpu().eval()
    with torch.no_grad():
        for name, parameter in quantized.named_parameters():
            if name.endswith("weight") or name.endswith("bias"):
                parameter.copy_(quantize(parameter, weight_scales[name]).to(parameter.dtype) * weight_scales[name])
    for name, module in quantized.named_modules():
        if isinstance(module, (nn.Conv1d, nn.ReLU, nn.MaxPool1d, nn.AdaptiveAvgPool1d, nn.Linear)) and name in activation_scales:
            module.register_forward_hook(lambda _m, _i, output, scale=activation_scales[name]: fake_quant(output, scale))
    # The deployment interface is signed INT8.  Quantize the raw signal before
    # the first convolution as well; without this pre-hook the exported
    # ``input_int8`` vector and the evaluated PTQ model describe different
    # computations and cannot be compared layer by layer with RTL.
    first_module = quantized.features[0]
    first_module.register_forward_pre_hook(
        lambda _m, inputs, scale=activation_scales["input"]: (fake_quant(inputs[0], scale),)
    )
    return quantized


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=pathlib.Path)
    parser.add_argument("--registry", required=True, type=pathlib.Path)
    parser.add_argument("--checkpoint", required=True, type=pathlib.Path)
    parser.add_argument("--output", required=True, type=pathlib.Path)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--calibration-samples", type=int, default=16)
    parser.add_argument("--eval-samples", type=int, default=16)
    args = parser.parse_args()
    set_seed(args.seed)
    args.output.mkdir(parents=True, exist_ok=True)
    registry = json.loads(args.registry.read_text(encoding="utf-8"))
    manifest = args.registry.parent / registry["manifest"]["path"]

    train_set = PTBXL(args.root, manifest, "train")
    val_set = PTBXL(args.root, manifest, "val")
    test_set = PTBXL(args.root, manifest, "test")
    calibration_rows = train_set.rows[: args.calibration_samples]
    if not calibration_rows:
        raise RuntimeError("no calibration rows available")

    def one_loader(dataset: PTBXL, limit: int) -> list[tuple[torch.Tensor, torch.Tensor]]:
        rows = dataset.rows[:limit]
        return [dataset[index] for index in range(len(rows))]

    calibration_loader = [(signal.unsqueeze(0), target.unsqueeze(0)) for signal, target in one_loader(train_set, args.calibration_samples)]
    model = TinyECGCNN().cpu().eval()
    checkpoint = torch.load(args.checkpoint, map_location="cpu", weights_only=False)
    model.load_state_dict(checkpoint["model"])
    activation_scales = calibration_scales(model, calibration_loader)
    weight_scales = {name: scale_for(parameter) for name, parameter in model.named_parameters() if name.endswith("weight") or name.endswith("bias")}
    quantized = quantized_eval_model(model, activation_scales, weight_scales)

    val_loader = [(signal.unsqueeze(0), target.unsqueeze(0)) for signal, target in one_loader(val_set, args.eval_samples)]
    test_loader = [(signal.unsqueeze(0), target.unsqueeze(0)) for signal, target in one_loader(test_set, args.eval_samples)]
    fp32_val, _, _ = evaluate(model, val_loader, torch.device("cpu"))
    int8_val, _, _ = evaluate(quantized, val_loader, torch.device("cpu"))
    fp32_test, _, _ = evaluate(model, test_loader, torch.device("cpu"))
    int8_test, _, _ = evaluate(quantized, test_loader, torch.device("cpu"))

    int8_state = {name: quantize(parameter, weight_scales[name]) for name, parameter in model.named_parameters() if name in weight_scales}
    torch.save({"state_dict_int8": int8_state, "weight_scales": weight_scales, "activation_scales": activation_scales, "registry_sha256": file_sha256(args.registry)}, args.output / "weights_int8.pt")
    first_signal, _first_target = val_loader[0]
    with torch.no_grad():
        fp32_logits = model(first_signal).numpy()
        int8_logits = quantized(first_signal).numpy()
    np.savez(args.output / "golden_vectors.npz", input_float=first_signal.numpy(), input_int8=quantize(first_signal, activation_scales["input"]).numpy(), fp32_logits=fp32_logits, int8_logits=int8_logits)
    contract = {
        "schema_version": "0.1",
        "method": "static_ptq_per_tensor_symmetric",
        "rounding": "sign_symmetric_nearest_half_away_from_zero",
        "clip": [-128, 127],
        "input_scale": activation_scales["input"],
        "weight_scales": weight_scales,
        "activation_scales": activation_scales,
        "labels": list(LABELS),
        "registry_sha256": file_sha256(args.registry),
        "checkpoint_sha256": file_sha256(args.checkpoint),
    }
    (args.output / "quantization_contract.json").write_text(json.dumps(contract, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    metrics = {"fp32_val": fp32_val, "int8_val": int8_val, "fp32_test": fp32_test, "int8_test": int8_test, "macro_auroc_delta_val": (int8_val["macro_auroc"] - fp32_val["macro_auroc"]) if int8_val["macro_auroc"] is not None and fp32_val["macro_auroc"] is not None else None, "macro_f1_delta_val": int8_val["macro_f1"] - fp32_val["macro_f1"]}
    (args.output / "metrics_int8.json").write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(metrics, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
