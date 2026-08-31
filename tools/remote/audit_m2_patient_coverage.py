"""Read-only audit of source-cohort versus supervised-cache patient coverage."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Mapping, Sequence

import numpy as np


SPLITS = ("train", "validation", "internal_test")
NATIVE_SYMBOLS = ("N", "Q", "S", "V")


def _native_counts_for_patient(
    records: Sequence[Mapping[str, object]], *, split: str, patient_id: str
) -> dict[str, int]:
    counts = {symbol: 0 for symbol in NATIVE_SYMBOLS}
    for row in records:
        if str(row.get("split")) != split or str(row.get("patient_id")) != patient_id:
            continue
        native = row.get("native_beat_counts", {})
        if not isinstance(native, Mapping):
            raise ValueError(f"invalid native_beat_counts for {split}/{patient_id}")
        for symbol in NATIVE_SYMBOLS:
            counts[symbol] += int(native.get(symbol, 0))
    return counts


def audit_patient_coverage(
    annotation_audit: Mapping[str, object],
    patient_ids_by_split: Mapping[str, np.ndarray],
) -> dict[str, object]:
    cohort = annotation_audit.get("cohort")
    records = annotation_audit.get("records")
    if not isinstance(cohort, Mapping) or not isinstance(records, list):
        raise ValueError("annotation audit must contain cohort and records")
    if set(patient_ids_by_split) != set(SPLITS):
        raise ValueError(f"patient cache must contain exactly {list(SPLITS)}")

    split_reports: dict[str, object] = {}
    for split in SPLITS:
        expected_ordered = [str(value) for value in cohort.get(split, [])]
        if len(expected_ordered) != len(set(expected_ordered)):
            raise ValueError(f"duplicate patient in annotation cohort: {split}")
        expected = set(expected_ordered)
        actual = {str(value) for value in np.asarray(patient_ids_by_split[split]).tolist()}
        missing = sorted(expected - actual)
        unexpected = sorted(actual - expected)
        missing_counts = {
            patient: _native_counts_for_patient(records, split=split, patient_id=patient)
            for patient in missing
        }
        missing_q_only = all(
            counts["Q"] > 0 and sum(counts[symbol] for symbol in ("N", "S", "V")) == 0
            for counts in missing_counts.values()
        )
        accepted = not unexpected and (
            (split == "train" and missing_q_only) or (split != "train" and not missing)
        )
        split_reports[split] = {
            "source_patient_count": len(expected),
            "cache_patient_count": len(actual),
            "missing_patients": missing,
            "unexpected_patients": unexpected,
            "missing_patient_native_counts": missing_counts,
            "missing_patients_q_only": missing_q_only,
            "accepted": accepted,
        }
    return {
        "accepted": all(bool(report["accepted"]) for report in split_reports.values()),
        "splits": split_reports,
    }


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit M2 source/cache patient coverage")
    parser.add_argument("--annotation-audit", required=True, type=Path)
    parser.add_argument("--train-npz", required=True, type=Path)
    parser.add_argument("--validation-npz", required=True, type=Path)
    parser.add_argument("--internal-test-npz", required=True, type=Path)
    args = parser.parse_args(argv)

    audit_path = args.annotation_audit.resolve()
    annotation_audit = json.loads(audit_path.read_text(encoding="utf-8"))
    patient_ids_by_split: dict[str, np.ndarray] = {}
    paths = {
        "train": args.train_npz.resolve(),
        "validation": args.validation_npz.resolve(),
        "internal_test": args.internal_test_npz.resolve(),
    }
    for split, path in paths.items():
        with np.load(path, allow_pickle=False) as archive:
            patient_ids_by_split[split] = np.asarray(archive["patient_ids"])
    report = audit_patient_coverage(annotation_audit, patient_ids_by_split)
    report["annotation_audit_path"] = str(audit_path)
    report["annotation_audit_sha256"] = _sha256_file(audit_path)
    report["npz_sha256"] = {split: _sha256_file(path) for split, path in paths.items()}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
