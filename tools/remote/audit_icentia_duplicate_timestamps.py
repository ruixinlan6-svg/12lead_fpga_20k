"""Audit same-sample native beat annotations in an accepted Icentia cohort."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[2]
TRAIN_EC57 = PROJECT_ROOT / "train" / "ec57"
if str(TRAIN_EC57) not in sys.path:
    sys.path.insert(0, str(TRAIN_EC57))

from prepare_icentia_native_cache import source_relative_files


NATIVE_BEAT_SYMBOLS = {"N", "S", "V", "Q"}


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def find_same_sample_native_groups(
    samples: Iterable[int], symbols: Iterable[str]
) -> list[dict[str, object]]:
    grouped: dict[int, list[str]] = {}
    for sample, symbol in zip(samples, symbols):
        native_symbol = str(symbol)
        if native_symbol not in NATIVE_BEAT_SYMBOLS:
            continue
        grouped.setdefault(int(sample), []).append(native_symbol)
    return [
        {
            "sample_index": sample,
            "symbols": values,
            "allowed_q_only": set(values) == {"Q"},
        }
        for sample, values in grouped.items()
        if len(values) > 1
    ]


def run_audit(
    annotation_audit: str | Path,
    source_root: str | Path,
    output_dir: str | Path,
    *,
    run_id: str,
) -> dict[str, object]:
    import wfdb

    audit_path = Path(annotation_audit).resolve()
    source = Path(source_root).resolve()
    output = Path(output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    cohort_audit = json.loads(audit_path.read_text(encoding="utf-8"))
    if cohort_audit.get("database") != "Icentia11k" or cohort_audit.get("database_version") != "1.0":
        raise ValueError("annotation audit is not Icentia11k 1.0")
    if int(cohort_audit.get("error_count", -1)) != 0 or not cohort_audit.get("records"):
        raise ValueError("annotation audit is incomplete or contains errors")

    record_rows = list(cohort_audit["records"])
    relative_files = sorted(
        {
            relative
            for row in record_rows
            for relative in source_relative_files(str(row["patient_id"]), str(row["record_id"]))
        }
    )
    errors: list[dict[str, str]] = []
    source_files: list[dict[str, object]] = []
    for relative in relative_files:
        path = source / Path(relative)
        try:
            source_files.append(
                {
                    "relative_path": relative,
                    "size_bytes": path.stat().st_size,
                    "sha256": _sha256_file(path),
                }
            )
        except Exception as exc:
            errors.append({"relative_path": relative, "error": repr(exc)})

    duplicate_groups: list[dict[str, object]] = []
    for position, row in enumerate(record_rows, start=1):
        split = str(row["split"])
        patient_id = str(row["patient_id"])
        record_id = str(row["record_id"])
        record_base = source / patient_id[:3] / patient_id / record_id
        try:
            annotation = wfdb.rdann(str(record_base), "atr")
            native_sequence = [
                (int(sample), str(symbol))
                for sample, symbol in zip(annotation.sample, annotation.symbol)
                if str(symbol) in NATIVE_BEAT_SYMBOLS
            ]
            if any(right[0] < left[0] for left, right in zip(native_sequence, native_sequence[1:])):
                raise ValueError("decreasing native annotation timestamp")
            atr_relative = source_relative_files(patient_id, record_id)[0]
            atr_hash = next(
                item["sha256"] for item in source_files if item["relative_path"] == atr_relative
            )
            for group in find_same_sample_native_groups(annotation.sample, annotation.symbol):
                duplicate_groups.append(
                    {
                        "split": split,
                        "patient_id": patient_id,
                        "record_id": record_id,
                        "atr_sha256": atr_hash,
                        **group,
                    }
                )
        except Exception as exc:
            errors.append(
                {
                    "split": split,
                    "patient_id": patient_id,
                    "record_id": record_id,
                    "error": repr(exc),
                }
            )
        print(
            f"ICENTIA_DUPLICATE_AUDIT {position}/{len(record_rows)} "
            f"groups={len(duplicate_groups)} errors={len(errors)}",
            flush=True,
        )

    non_q_only = [group for group in duplicate_groups if not bool(group["allowed_q_only"])]
    summary: dict[str, object] = {
        "run_id": run_id,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "database": "Icentia11k",
        "database_version": "1.0",
        "annotation_audit_sha256": _sha256_file(audit_path),
        "record_count": len(record_rows),
        "source_file_count": len(source_files),
        "duplicate_group_count": len(duplicate_groups),
        "q_only_duplicate_group_count": len(duplicate_groups) - len(non_q_only),
        "non_q_only_duplicate_group_count": len(non_q_only),
        "error_count": len(errors),
        "duplicate_groups": duplicate_groups,
        "errors": errors,
        "source_files": source_files,
        "locked_databases_accessed": False,
    }
    summary_path = output / "duplicate_timestamp_audit.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "sha256_manifest.txt").write_text(
        f"{_sha256_file(summary_path)}  duplicate_timestamp_audit.json\n", encoding="ascii"
    )
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit duplicate native Icentia beat timestamps")
    parser.add_argument("--annotation-audit", required=True, type=Path)
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args(argv)
    summary = run_audit(
        args.annotation_audit,
        args.source_root,
        args.output_dir,
        run_id=args.run_id,
    )
    print(
        json.dumps(
            {key: value for key, value in summary.items() if key not in {"source_files", "duplicate_groups"}},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if summary["error_count"] == 0 and summary["non_q_only_duplicate_group_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
