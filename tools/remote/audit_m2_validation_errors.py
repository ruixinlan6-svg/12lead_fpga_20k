"""Validation-only error taxonomy for a rejected M2 VEB checkpoint."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Mapping, Sequence

import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from train.ec57.cache_provenance import validate_m2_cache_split
from train.ec57.model_nv import TinyECGCNN_NV


REQUIRED_ARRAYS = (
    "labels",
    "patient_ids",
    "record_ids",
    "sample_indices",
    "native_symbols",
    "source_file_sha256",
    "features",
)


def validate_development_split_name(split: str) -> str:
    normalized = str(split)
    if normalized not in {"train", "validation"}:
        raise ValueError("error audit split must be train or validation")
    return normalized


def _sorted_counts(values: np.ndarray) -> dict[str, int]:
    return dict(sorted(Counter(str(value) for value in values.tolist()).items()))


def _quantiles(values: np.ndarray) -> dict[str, float | None]:
    data = np.asarray(values, dtype=np.float64)
    if data.size == 0:
        return {name: None for name in ("min", "p25", "p50", "p75", "p90", "p95", "p99", "max")}
    points = np.quantile(data, [0.0, 0.25, 0.5, 0.75, 0.9, 0.95, 0.99, 1.0])
    return {
        name: float(value)
        for name, value in zip(("min", "p25", "p50", "p75", "p90", "p95", "p99", "max"), points)
    }


def _feature_quantiles(features: np.ndarray, mask: np.ndarray) -> list[dict[str, float | None]]:
    return [_quantiles(features[mask, index]) for index in range(features.shape[1])]


def summarize_validation_errors(
    arrays: Mapping[str, np.ndarray],
    probabilities: np.ndarray,
    *,
    thresholds: Sequence[float],
) -> tuple[dict[str, object], list[dict[str, object]]]:
    missing_keys = [key for key in REQUIRED_ARRAYS if key not in arrays]
    if missing_keys:
        raise ValueError(f"validation arrays missing required keys: {missing_keys}")
    labels = np.asarray(arrays["labels"], dtype=np.int64)
    probs = np.asarray(probabilities, dtype=np.float64)
    sample_count = len(labels)
    for key in REQUIRED_ARRAYS:
        if len(np.asarray(arrays[key])) != sample_count:
            raise ValueError("validation arrays and probabilities must be aligned")
    if probs.ndim != 1 or len(probs) != sample_count:
        raise ValueError("validation arrays and probabilities must be aligned")
    if not np.isfinite(probs).all() or np.any((probs < 0.0) | (probs > 1.0)):
        raise ValueError("probabilities must be finite and within [0,1]")
    if set(labels.tolist()) - {0, 1}:
        raise ValueError("validation labels must be binary")
    native_symbols = np.asarray(arrays["native_symbols"]).astype(str)
    if set(native_symbols.tolist()) - {"N", "S", "V"}:
        raise ValueError("validation native symbols must be N/S/V only")
    features = np.asarray(arrays["features"])
    if features.ndim != 2 or features.shape[1] != 4:
        raise ValueError("validation features must have shape [N,4]")

    threshold_values = sorted({float(value) for value in thresholds})
    if not threshold_values or any(not 0.0 <= value <= 1.0 for value in threshold_values):
        raise ValueError("diagnostic thresholds must be unique values within [0,1]")

    patient_ids = np.asarray(arrays["patient_ids"]).astype(str)
    record_ids = np.asarray(arrays["record_ids"]).astype(str)
    threshold_reports: dict[str, object] = {}
    errors_by_index: dict[int, dict[str, object]] = {}
    for threshold in threshold_values:
        key = f"{threshold:.3f}"
        predicted = probs >= threshold
        positive = labels == 1
        negative = ~positive
        masks = {
            "vtp": positive & predicted,
            "vfn": positive & ~predicted,
            "vfp": negative & predicted,
            "vtn": negative & ~predicted,
        }
        counts = {name: int(np.count_nonzero(mask)) for name, mask in masks.items()}
        vtp, vfn, vfp, vtn = (counts[name] for name in ("vtp", "vfn", "vfp", "vtn"))
        threshold_reports[key] = {
            "threshold": threshold,
            "counts": counts,
            "se_percent": 100.0 * vtp / (vtp + vfn) if vtp + vfn else None,
            "plus_p_percent": 100.0 * vtp / (vtp + vfp) if vtp + vfp else None,
            "fpr_percent": 100.0 * vfp / (vtn + vfp) if vtn + vfp else None,
            "false_positive_native_symbols": _sorted_counts(native_symbols[masks["vfp"]]),
            "false_negative_native_symbols": _sorted_counts(native_symbols[masks["vfn"]]),
            "false_positive_patients": _sorted_counts(patient_ids[masks["vfp"]]),
            "false_negative_patients": _sorted_counts(patient_ids[masks["vfn"]]),
            "false_positive_records": _sorted_counts(record_ids[masks["vfp"]]),
            "false_negative_records": _sorted_counts(record_ids[masks["vfn"]]),
            "probability_quantiles": {
                name: _quantiles(probs[mask]) for name, mask in masks.items()
            },
            "feature_quantiles": {
                name: _feature_quantiles(features, mask) for name, mask in masks.items()
            },
        }
        for index in np.flatnonzero(masks["vfp"] | masks["vfn"]).tolist():
            row = errors_by_index.setdefault(
                index,
                {
                    "cache_index": index,
                    "patient_id": patient_ids[index],
                    "record_id": record_ids[index],
                    "sample_index": int(np.asarray(arrays["sample_indices"])[index]),
                    "native_symbol": native_symbols[index],
                    "source_file_sha256": str(np.asarray(arrays["source_file_sha256"])[index]),
                    "veb_probability": float(probs[index]),
                    **{f"feature_{feature_index}": int(features[index, feature_index]) for feature_index in range(4)},
                },
            )
            row[f"error_at_{key}"] = "VFN" if labels[index] == 1 else "VFP"

    error_columns = [f"error_at_{threshold:.3f}" for threshold in threshold_values]
    rows: list[dict[str, object]] = []
    for index in sorted(errors_by_index):
        row = errors_by_index[index]
        for column in error_columns:
            row.setdefault(column, "")
        rows.append(row)
    report: dict[str, object] = {
        "sample_count": sample_count,
        "native_symbol_counts": _sorted_counts(native_symbols),
        "probability_quantiles_by_native_symbol": {
            symbol: _quantiles(probs[native_symbols == symbol]) for symbol in ("N", "S", "V")
        },
        "thresholds": threshold_reports,
        "unique_error_row_count": len(rows),
    }
    return report, rows


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _infer_probabilities(
    arrays: Mapping[str, np.ndarray],
    *,
    model_path: Path,
    input_divisor: float,
    device_name: str,
    batch_size: int,
) -> np.ndarray:
    import torch

    device = torch.device(device_name)
    model = TinyECGCNN_NV().to(device)
    try:
        state = torch.load(model_path, map_location=device, weights_only=True)
    except TypeError:
        state = torch.load(model_path, map_location=device)
    model.load_state_dict(state)
    model.eval()
    waveforms = np.asarray(arrays["waveforms"], dtype=np.float32)
    features = np.asarray(arrays["features"], dtype=np.float32)
    outputs: list[np.ndarray] = []
    with torch.no_grad():
        for start in range(0, len(waveforms), batch_size):
            stop = min(len(waveforms), start + batch_size)
            wave = torch.from_numpy(waveforms[start:stop] / input_divisor).unsqueeze(1).to(device)
            feat = torch.from_numpy(features[start:stop] / input_divisor).to(device)
            outputs.append(torch.softmax(model(wave, feat), dim=1)[:, 1].cpu().numpy())
    return np.concatenate(outputs).astype(np.float64)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit a rejected M2 checkpoint on a development split")
    npz_group = parser.add_mutually_exclusive_group(required=True)
    npz_group.add_argument("--npz", type=Path)
    npz_group.add_argument("--validation-npz", type=Path, help="Backward-compatible validation-only alias")
    parser.add_argument("--split", default="validation")
    parser.add_argument("--model", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--batch-size", type=int, default=4096)
    parser.add_argument("--threshold", action="append", required=True, type=float)
    args = parser.parse_args(argv)

    split = validate_development_split_name(args.split)
    if args.validation_npz is not None and split != "validation":
        raise ValueError("--validation-npz can only be used with split validation")
    split_path = (args.npz or args.validation_npz).resolve()
    model_path = args.model.resolve()
    config_path = args.config.resolve()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    with np.load(split_path, allow_pickle=False) as archive:
        arrays = {key: np.asarray(archive[key]) for key in archive.files}
    validate_m2_cache_split(arrays, split_name=split)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    input_divisor = float(config["data"]["fp32_input_divisor"])
    probabilities = _infer_probabilities(
        arrays,
        model_path=model_path,
        input_divisor=input_divisor,
        device_name=args.device,
        batch_size=args.batch_size,
    )
    report, rows = summarize_validation_errors(arrays, probabilities, thresholds=args.threshold)
    report.update(
        {
            "development_split_only": True,
            "evaluation_split": split,
            "internal_test_loaded": False,
            "model_sha256": _sha256_file(model_path),
            "config_sha256": _sha256_file(config_path),
            "split_npz_sha256": _sha256_file(split_path),
            "input_divisor": input_divisor,
            "device": args.device,
        }
    )
    summary_path = output / "summary.json"
    summary_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    errors_path = output / "errors.csv"
    fieldnames = list(rows[0]) if rows else ["cache_index"]
    with errors_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    artifact_paths = (summary_path, errors_path)
    manifest_lines = [f"{_sha256_file(path)}  {path.name}" for path in artifact_paths]
    (output / "sha256_manifest.txt").write_text("\n".join(manifest_lines) + "\n", encoding="ascii")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
