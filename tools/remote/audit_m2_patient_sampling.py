"""Audit train-only patient concentration for the production M2 epoch sampler."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from train.ec57.train_nv import build_epoch_sample_indices


def gini(values: np.ndarray) -> float:
    values = np.asarray(values, dtype=np.float64)
    if values.ndim != 1 or values.size == 0 or np.any(values < 0):
        raise ValueError("gini requires a non-empty one-dimensional non-negative array")
    total = float(values.sum())
    if total == 0.0:
        return 0.0
    ordered = np.sort(values)
    ranks = np.arange(1, ordered.size + 1, dtype=np.float64)
    return float((2.0 * np.sum(ranks * ordered) / (ordered.size * total)) - (ordered.size + 1.0) / ordered.size)


def distribution_summary(counts: np.ndarray) -> dict:
    counts = np.asarray(counts, dtype=np.int64)
    total = int(counts.sum())
    descending = np.sort(counts)[::-1]
    return {
        "patients": int(counts.size),
        "total": total,
        "min": int(counts.min()),
        "median": float(np.median(counts)),
        "p90": float(np.percentile(counts, 90)),
        "p95": float(np.percentile(counts, 95)),
        "p99": float(np.percentile(counts, 99)),
        "max": int(counts.max()),
        "p99_median_ratio": float(np.percentile(counts, 99) / max(1.0, float(np.median(counts)))),
        "top1_share": float(descending[:1].sum() / total),
        "top5_share": float(descending[:5].sum() / total),
        "top10_share": float(descending[:10].sum() / total),
        "gini": gini(counts),
    }


def patient_rows(labels: np.ndarray, patient_ids: np.ndarray, indices: np.ndarray) -> list[dict]:
    selected_labels = labels[indices]
    selected_patients = patient_ids[indices]
    rows = []
    for patient in sorted(np.unique(selected_patients).astype(str)):
        mask = selected_patients.astype(str) == patient
        patient_labels = selected_labels[mask]
        rows.append({
            "patient_id": patient,
            "total": int(mask.sum()),
            "negative": int(np.sum(patient_labels == 0)),
            "veb": int(np.sum(patient_labels == 1)),
        })
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--train-npz", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--epoch", type=int, default=0)
    parser.add_argument("--max-beats-per-patient", type=int, default=10000)
    parser.add_argument("--max-negative-to-positive", type=int, default=4)
    args = parser.parse_args()

    train_path = Path(args.train_npz)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    with np.load(train_path, allow_pickle=False) as arrays:
        labels = np.asarray(arrays["labels"], dtype=np.int64)
        patient_ids = np.asarray(arrays["patient_ids"]).astype(str)
    if labels.ndim != 1 or patient_ids.ndim != 1 or labels.shape != patient_ids.shape:
        raise ValueError("labels and patient_ids must be aligned one-dimensional arrays")
    if not np.all(np.isin(labels, [0, 1])):
        raise ValueError("labels must be binary 0/1")

    selected = build_epoch_sample_indices(
        labels,
        patient_ids,
        seed=args.seed,
        epoch=args.epoch,
        max_beats_per_patient=args.max_beats_per_patient,
        max_negative_per_positive=args.max_negative_to_positive,
    )
    replay = build_epoch_sample_indices(
        labels,
        patient_ids,
        seed=args.seed,
        epoch=args.epoch,
        max_beats_per_patient=args.max_beats_per_patient,
        max_negative_per_positive=args.max_negative_to_positive,
    )
    if not np.array_equal(selected, replay):
        raise RuntimeError("production sampler replay is not deterministic")
    if selected.ndim != 1 or np.any(selected < 0) or np.any(selected >= labels.size):
        raise RuntimeError("production sampler returned invalid indices")

    all_indices = np.arange(labels.size, dtype=np.int64)
    raw_rows = patient_rows(labels, patient_ids, all_indices)
    selected_rows = patient_rows(labels, patient_ids, selected)
    raw_counts = np.asarray([row["total"] for row in raw_rows], dtype=np.int64)
    selected_counts = np.asarray([row["total"] for row in selected_rows], dtype=np.int64)
    report = {
        "scope": "train_only",
        "validation_loaded": False,
        "internal_test_loaded": False,
        "train_npz_name": train_path.name,
        "train_npz_sha256": hashlib.sha256(train_path.read_bytes()).hexdigest(),
        "seed": args.seed,
        "epoch": args.epoch,
        "max_beats_per_patient": args.max_beats_per_patient,
        "max_negative_to_positive": args.max_negative_to_positive,
        "raw": distribution_summary(raw_counts),
        "selected": distribution_summary(selected_counts),
        "raw_class_counts": {"negative": int(np.sum(labels == 0)), "veb": int(np.sum(labels == 1))},
        "selected_class_counts": {
            "negative": int(np.sum(labels[selected] == 0)),
            "veb": int(np.sum(labels[selected] == 1)),
        },
        "patients_over_cap_raw": int(np.sum(raw_counts > args.max_beats_per_patient)),
        "selected_patient_rows": sorted(selected_rows, key=lambda row: (-row["total"], row["patient_id"])),
    }
    report_path = output_dir / "patient_sampling_audit.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    digest = hashlib.sha256(report_path.read_bytes()).hexdigest()
    (output_dir / "sha256_manifest.txt").write_text(
        f"{digest}  {report_path.name}\n", encoding="utf-8"
    )
    print(json.dumps({key: report[key] for key in ("scope", "raw", "selected", "raw_class_counts", "selected_class_counts", "patients_over_cap_raw")}, indent=2))


if __name__ == "__main__":
    main()
