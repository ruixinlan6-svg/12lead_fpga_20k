#!/usr/bin/env python3
"""Create a deterministic PTB-XL registry and patient-level split manifest."""

from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import json
import pathlib
import sys
from collections import Counter, defaultdict


LABELS = ("NORM", "MI", "STTC", "CD", "HYP")


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_diagnostic_classes(path: pathlib.Path) -> dict[str, str]:
    mapping: dict[str, str] = {}
    with path.open(encoding="utf-8", newline="") as stream:
        # PTB-XL 1.0.3 stores this table as comma-separated CSV and leaves
        # the first (SCP code) header cell empty.
        reader = csv.DictReader(stream, delimiter=",")
        for row in reader:
            if str(row.get("diagnostic", "")).strip() != "1.0":
                continue
            diagnostic_class = str(row.get("diagnostic_class", "")).strip()
            code = str(row.get("scp_code") or row.get("", "")).strip()
            if code and diagnostic_class in LABELS:
                mapping[code] = diagnostic_class
    return mapping


def parse_codes(raw: str) -> dict[str, float]:
    value = ast.literal_eval(raw)
    if not isinstance(value, dict):
        raise ValueError(f"scp_codes is not a dictionary: {raw[:80]}")
    return {str(code): float(score) for code, score in value.items()}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=pathlib.Path)
    parser.add_argument("--output", required=True, type=pathlib.Path)
    parser.add_argument("--available-only", action="store_true", help="keep only records whose .hea and .dat are already present")
    parser.add_argument("--max-per-split", type=int, default=None, help="keep at most N records in each train/val/test split")
    args = parser.parse_args()

    metadata = args.root / "ptbxl_database.csv"
    statements = args.root / "scp_statements.csv"
    records_file = args.root / "RECORDS"
    for path in (metadata, statements, records_file):
        if not path.exists():
            raise FileNotFoundError(f"missing {path}; run download_ptbxl.py first")

    code_to_class = read_diagnostic_classes(statements)
    rows: list[dict] = []
    skipped_without_diagnostic = 0
    label_counter = Counter()
    patients_by_fold: defaultdict[int, set[str]] = defaultdict(set)

    with metadata.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        for row in reader:
            labels = sorted({code_to_class[code] for code in parse_codes(row["scp_codes"]) if code in code_to_class}, key=LABELS.index)
            if not labels:
                skipped_without_diagnostic += 1
                continue
            fold = int(row["strat_fold"])
            patient_id = str(row["patient_id"])
            record = str(row["filename_lr"])
            if not record.endswith("_lr"):
                raise ValueError(f"unexpected low-resolution filename: {record}")
            if args.available_only and not all((args.root / (record + extension)).is_file() for extension in (".hea", ".dat")):
                continue
            entry = {
                "ecg_id": int(row["ecg_id"]),
                "patient_id": patient_id,
                "fold": fold,
                "record": record,
                "labels": labels,
                "label_vector": [int(label in labels) for label in LABELS],
            }
            rows.append(entry)

    rows.sort(key=lambda item: item["ecg_id"])
    if args.max_per_split is not None:
        if args.max_per_split < 1:
            raise ValueError("--max-per-split must be positive")
        kept = []
        split_counts = Counter()
        for entry in rows:
            split = "train" if entry["fold"] <= 8 else "val" if entry["fold"] == 9 else "test" if entry["fold"] == 10 else "unused"
            if split != "unused" and split_counts[split] < args.max_per_split:
                kept.append(entry)
                split_counts[split] += 1
        rows = kept
    # Recompute statistics after optional availability/subset filters so the
    # registry describes the actual manifest rather than the source metadata.
    patients_by_fold = defaultdict(set)
    label_counter = Counter()
    for entry in rows:
        patients_by_fold[entry["fold"]].add(entry["patient_id"])
        label_counter.update(entry["labels"])
    duplicate_patients = []
    for left_fold, left_patients in patients_by_fold.items():
        for right_fold, right_patients in patients_by_fold.items():
            if left_fold < right_fold:
                overlap = sorted(left_patients & right_patients)
                if overlap:
                    duplicate_patients.append({"fold_a": left_fold, "fold_b": right_fold, "count": len(overlap)})
    if duplicate_patients:
        raise RuntimeError(f"patient leakage across official folds: {duplicate_patients[:3]}")

    args.output.mkdir(parents=True, exist_ok=True)
    manifest = args.output / "split_manifest.jsonl"
    with manifest.open("w", encoding="utf-8", newline="\n") as stream:
        for entry in rows:
            stream.write(json.dumps(entry, sort_keys=True, separators=(",", ":")) + "\n")

    registry = {
        "schema_version": "0.1",
        "dataset": "PTB-XL",
        "version": "1.0.3",
        "source": "https://physionet.org/files/ptb-xl/1.0.3/",
        "license": "PhysioNet Credentialed Health Data License 1.5.0; verify current terms before redistribution",
        "signal": {"sampling_rate_hz": 100, "duration_s": 10, "lead_order": ["I", "II", "III", "aVR", "aVL", "aVF", "V1", "V2", "V3", "V4", "V5", "V6"], "unit": "mV from WFDB physical read"},
        "task": {"type": "five-diagnostic-superclass-multilabel", "label_order": list(LABELS), "split_rule": "folds 1-8 train, 9 validation, 10 test"},
        "counts": {"records_with_diagnostic_labels": len(rows), "skipped_without_diagnostic_labels": skipped_without_diagnostic, "patients": len({entry["patient_id"] for entry in rows}), "by_fold": dict(sorted(Counter(entry["fold"] for entry in rows).items())), "by_label": dict(label_counter)},
        "source_sha256": {name: sha256(args.root / name) for name in ("ptbxl_database.csv", "scp_statements.csv", "RECORDS")},
        "manifest": {"path": manifest.name, "sha256": sha256(manifest)},
        "raw_data_root": str(args.root),
        "subset": {"available_only": args.available_only, "max_per_split": args.max_per_split},
    }
    # JSON is valid YAML 1.2, so this file remains dependency-free.
    (args.output / "data_registry.yaml").write_text(json.dumps(registry, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(registry, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
