"""Audit a deterministic Icentia11k cohort using native WFDB annotations only."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[2]
TRAIN_EC57 = PROJECT_ROOT / "train" / "ec57"
if str(TRAIN_EC57) not in sys.path:
    sys.path.insert(0, str(TRAIN_EC57))

from build_registry import assign_icentia_split


DATABASE = "Icentia11k"
DATABASE_VERSION = "1.0"
PN_DIR = "icentia11k-continuous-ecg/1.0"
NATIVE_BEAT_SYMBOLS = {"N", "S", "V", "Q"}


def select_by_digest(values: Iterable[str], count: int) -> list[str]:
    if count <= 0:
        raise ValueError("selection count must be positive")
    unique = sorted(set(str(value) for value in values))
    if len(unique) < count:
        raise ValueError(f"requested {count} items from only {len(unique)} unique values")
    return sorted(unique, key=lambda value: (hashlib.sha256(value.encode("utf-8")).hexdigest(), value))[:count]


def select_readable_records(
    values: Iterable[str],
    *,
    count: int,
    read_annotation: Callable[[str], Any],
    split: str,
    patient_id: str,
) -> tuple[list[tuple[str, Any]], list[dict[str, str]]]:
    """Select the first ``count`` readable records in deterministic digest order."""
    if count <= 0:
        raise ValueError("selection count must be positive")
    ordered = select_by_digest(values, len(set(str(value) for value in values)))
    selected: list[tuple[str, Any]] = []
    exclusions: list[dict[str, str]] = []
    for record_id in ordered:
        try:
            annotation = read_annotation(record_id)
        except Exception as exc:
            exclusions.append(
                {
                    "split": split,
                    "patient_id": patient_id,
                    "record_id": record_id,
                    "error": repr(exc),
                }
            )
            continue
        selected.append((record_id, annotation))
        if len(selected) == count:
            break
    return selected, exclusions


def build_patient_cohort(
    patient_ids: Iterable[str], *, patients_per_split: int | Mapping[str, int]
) -> dict[str, list[str]]:
    grouped = {"train": [], "validation": [], "internal_test": []}
    for patient_id in patient_ids:
        patient = str(patient_id).strip("/").split("/")[-1]
        grouped[assign_icentia_split(patient)].append(patient)
    if isinstance(patients_per_split, Mapping):
        expected = set(grouped)
        if set(patients_per_split) != expected:
            raise ValueError(f"split-specific patient counts require exactly {sorted(expected)}")
        counts = {split: int(patients_per_split[split]) for split in grouped}
    else:
        counts = {split: int(patients_per_split) for split in grouped}
    return {split: select_by_digest(patients, counts[split]) for split, patients in grouped.items()}


def summarize_symbols(symbols: Iterable[str]) -> dict[str, dict[str, int]]:
    counts = Counter(str(symbol) for symbol in symbols)
    native = {key: counts[key] for key in sorted(NATIVE_BEAT_SYMBOLS) if counts[key]}
    other = {key: value for key, value in sorted(counts.items()) if key not in NATIVE_BEAT_SYMBOLS}
    return {"native_beat_counts": native, "other_symbol_counts": other}


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def run_audit(
    output_dir: str | Path,
    *,
    run_id: str,
    patients_per_split: int | Mapping[str, int],
    segments_per_patient: int,
) -> dict[str, object]:
    import wfdb

    output = Path(output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    patient_dirs = wfdb.get_record_list(PN_DIR)
    cohort = build_patient_cohort(patient_dirs, patients_per_split=patients_per_split)
    records: list[dict[str, object]] = []
    errors: list[dict[str, str]] = []
    exclusions: list[dict[str, str]] = []
    aggregate_native: Counter[str] = Counter()
    aggregate_other: Counter[str] = Counter()
    for split in ("train", "validation", "internal_test"):
        for patient_id in cohort[split]:
            prefix = patient_id[:3]
            patient_dir = f"{PN_DIR}/{prefix}/{patient_id}"
            try:
                available_records = wfdb.get_record_list(patient_dir)
            except Exception as exc:
                errors.append({"split": split, "patient_id": patient_id, "record_id": "", "error": repr(exc)})
                continue
            selected_records, patient_exclusions = select_readable_records(
                available_records,
                count=segments_per_patient,
                read_annotation=lambda record_id: wfdb.rdann(record_id, "atr", pn_dir=patient_dir),
                split=split,
                patient_id=patient_id,
            )
            exclusions.extend(patient_exclusions)
            if len(selected_records) != segments_per_patient:
                errors.append(
                    {
                        "split": split,
                        "patient_id": patient_id,
                        "record_id": "",
                        "error": (
                            f"only {len(selected_records)} readable records available; "
                            f"required {segments_per_patient}"
                        ),
                    }
                )
            for record_id, annotation in selected_records:
                symbol_summary = summarize_symbols(annotation.symbol)
                aggregate_native.update(symbol_summary["native_beat_counts"])
                aggregate_other.update(symbol_summary["other_symbol_counts"])
                records.append(
                    {
                        "database": DATABASE,
                        "database_version": DATABASE_VERSION,
                        "split": split,
                        "patient_id": patient_id,
                        "record_id": record_id,
                        "annotation_count": len(annotation.sample),
                        **symbol_summary,
                    }
                )
            print(
                f"ICENTIA_AUDIT split={split} patient={patient_id} records={len(records)} "
                f"exclusions={len(exclusions)} errors={len(errors)}",
                flush=True,
            )
    summary: dict[str, object] = {
        "run_id": run_id,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "database": DATABASE,
        "database_version": DATABASE_VERSION,
        "pn_dir": PN_DIR,
        "patients_per_split": patients_per_split,
        "segments_per_patient": segments_per_patient,
        "cohort": cohort,
        "record_count": len(records),
        "exclusion_count": len(exclusions),
        "error_count": len(errors),
        "native_beat_counts": dict(sorted(aggregate_native.items())),
        "other_symbol_counts": dict(sorted(aggregate_other.items())),
        "records": records,
        "exclusions": exclusions,
        "errors": errors,
        "signals_downloaded": False,
        "locked_databases_accessed": False,
    }
    summary_path = output / "annotation_audit.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "sha256_manifest.txt").write_text(
        f"{_sha256_file(summary_path)}  annotation_audit.json\n", encoding="ascii"
    )
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit native Icentia11k annotation availability")
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--patients-per-split", type=int, default=24)
    parser.add_argument("--train-patients", type=int)
    parser.add_argument("--validation-patients", type=int)
    parser.add_argument("--internal-test-patients", type=int)
    parser.add_argument("--segments-per-patient", type=int, default=3)
    args = parser.parse_args(argv)
    patients_per_split: int | dict[str, int] = args.patients_per_split
    if any(
        value is not None
        for value in (args.train_patients, args.validation_patients, args.internal_test_patients)
    ):
        patients_per_split = {
            "train": args.train_patients or args.patients_per_split,
            "validation": args.validation_patients or args.patients_per_split,
            "internal_test": args.internal_test_patients or args.patients_per_split,
        }
    summary = run_audit(
        args.output_dir,
        run_id=args.run_id,
        patients_per_split=patients_per_split,
        segments_per_patient=args.segments_per_patient,
    )
    print(json.dumps({key: value for key, value in summary.items() if key not in {"records", "cohort"}}, ensure_ascii=False, indent=2))
    return 0 if not summary["errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
