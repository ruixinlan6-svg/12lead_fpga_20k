"""Build a deterministic same-patient finite-signal replacement audit."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[2]
TRAIN_EC57 = PROJECT_ROOT / "train" / "ec57"
TOOLS_REMOTE = PROJECT_ROOT / "tools" / "remote"
for path in (TRAIN_EC57, TOOLS_REMOTE):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from audit_icentia_annotations import PN_DIR, select_by_digest, summarize_symbols
from audit_icentia_duplicate_timestamps import find_same_sample_native_groups
from prepare_icentia_native_cache import WFDB_DOWNLOAD_DB, source_relative_files


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def select_first_valid_candidate(
    available_records: Iterable[str],
    *,
    already_selected: set[str],
    validate: Callable[[str], Any],
) -> tuple[str, Any, list[dict[str, object]]]:
    values = [str(value) for value in available_records]
    ordered = select_by_digest(values, len(set(values)))
    attempts: list[dict[str, object]] = []
    for record_id in ordered:
        if record_id in already_selected:
            continue
        try:
            payload = validate(record_id)
        except Exception as exc:
            attempts.append({"record_id": record_id, "accepted": False, "reason": repr(exc)})
            continue
        attempts.append(
            {"record_id": record_id, "accepted": True, "reason": "finite signal and valid annotation"}
        )
        return record_id, payload, attempts
    raise ValueError(f"no valid finite replacement; attempts={attempts}")


def run_replacement(
    annotation_audit: str | Path,
    signal_audit: str | Path,
    source_root: str | Path,
    output_dir: str | Path,
    *,
    run_id: str,
) -> dict[str, object]:
    import wfdb

    annotation_path = Path(annotation_audit).resolve()
    signal_path = Path(signal_audit).resolve()
    source = Path(source_root).resolve()
    output = Path(output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    base = json.loads(annotation_path.read_text(encoding="utf-8"))
    integrity = json.loads(signal_path.read_text(encoding="utf-8"))
    if base.get("database") != "Icentia11k" or int(base.get("error_count", -1)) != 0:
        raise ValueError("base annotation audit is not an accepted Icentia audit")
    if (
        int(integrity.get("error_count", -1)) != 0
        or int(integrity.get("record_count", -1)) != len(base.get("records", []))
    ):
        raise ValueError("signal-integrity audit is incomplete or contains errors")

    revised_records = [dict(row) for row in base["records"]]
    affected = [row for row in integrity["records"] if int(row["nonfinite_sample_count"]) > 0]
    replacements: list[dict[str, object]] = []
    errors: list[dict[str, str]] = []
    for affected_row in affected:
        split = str(affected_row["split"])
        patient_id = str(affected_row["patient_id"])
        removed_record = str(affected_row["record_id"])
        selected_for_patient = {
            str(row["record_id"]) for row in revised_records if str(row["patient_id"]) == patient_id
        }
        patient_dir = f"{PN_DIR}/{patient_id[:3]}/{patient_id}"
        try:
            available = wfdb.get_record_list(patient_dir)

            def validate_candidate(record_id: str) -> dict[str, object]:
                relative_files = source_relative_files(patient_id, record_id)
                wfdb.dl_files(
                    WFDB_DOWNLOAD_DB,
                    str(source),
                    relative_files,
                    keep_subdirs=True,
                    overwrite=False,
                )
                file_hashes = {
                    relative: _sha256_file(source / relative) for relative in relative_files
                }
                record_base = source / patient_id[:3] / patient_id / record_id
                annotation = wfdb.rdann(str(record_base), "atr")
                duplicate_groups = find_same_sample_native_groups(annotation.sample, annotation.symbol)
                if any(not bool(group["allowed_q_only"]) for group in duplicate_groups):
                    raise ValueError("candidate has non-Q-only duplicate annotation")
                record = wfdb.rdrecord(str(record_base), physical=True)
                if float(record.fs) != 250.0 or int(record.n_sig) != 1:
                    raise ValueError(f"candidate signal contract fs={record.fs}, n_sig={record.n_sig}")
                nonfinite_count = int(np.count_nonzero(~np.isfinite(record.p_signal[:, 0])))
                if nonfinite_count:
                    raise ValueError(f"candidate has {nonfinite_count} non-finite samples")
                symbol_summary = summarize_symbols(annotation.symbol)
                return {
                    "record_row": {
                        "database": "Icentia11k",
                        "database_version": "1.0",
                        "split": split,
                        "patient_id": patient_id,
                        "record_id": record_id,
                        "annotation_count": len(annotation.sample),
                        **symbol_summary,
                    },
                    "source_file_hashes": file_hashes,
                    "signal_length": int(record.sig_len),
                    "duplicate_groups": duplicate_groups,
                }

            chosen, payload, attempts = select_first_valid_candidate(
                available,
                already_selected=selected_for_patient,
                validate=validate_candidate,
            )
            replaced = False
            for index, row in enumerate(revised_records):
                if (
                    str(row["split"]) == split
                    and str(row["patient_id"]) == patient_id
                    and str(row["record_id"]) == removed_record
                ):
                    revised_records[index] = payload["record_row"]
                    replaced = True
                    break
            if not replaced:
                raise ValueError("affected record is absent from base annotation audit")
            replacements.append(
                {
                    "split": split,
                    "patient_id": patient_id,
                    "removed_record_id": removed_record,
                    "replacement_record_id": chosen,
                    "attempts": attempts,
                    "replacement_evidence": {
                        key: value for key, value in payload.items() if key != "record_row"
                    },
                }
            )
        except Exception as exc:
            errors.append(
                {
                    "split": split,
                    "patient_id": patient_id,
                    "record_id": removed_record,
                    "error": repr(exc),
                }
            )

    native_counts: Counter[str] = Counter()
    other_counts: Counter[str] = Counter()
    for row in revised_records:
        native_counts.update({str(key): int(value) for key, value in row["native_beat_counts"].items()})
        other_counts.update({str(key): int(value) for key, value in row["other_symbol_counts"].items()})
    held_out_equal: dict[str, bool] = {}
    for split in ("validation", "internal_test"):
        before = [
            (str(row["patient_id"]), str(row["record_id"]))
            for row in base["records"]
            if str(row["split"]) == split
        ]
        after = [
            (str(row["patient_id"]), str(row["record_id"]))
            for row in revised_records
            if str(row["split"]) == split
        ]
        held_out_equal[split] = before == after
        if not held_out_equal[split]:
            errors.append({"split": split, "patient_id": "", "record_id": "", "error": "held-out records changed"})

    summary: dict[str, object] = {
        "run_id": run_id,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "database": "Icentia11k",
        "database_version": "1.0",
        "pn_dir": PN_DIR,
        "base_annotation_audit_sha256": _sha256_file(annotation_path),
        "signal_integrity_audit_sha256": _sha256_file(signal_path),
        "patients_per_split": base["patients_per_split"],
        "segments_per_patient": base["segments_per_patient"],
        "cohort": base["cohort"],
        "record_count": len(revised_records),
        "replacement_count": len(replacements),
        "expected_replacement_count": len(affected),
        "source_file_count": len(revised_records) * 3,
        "error_count": len(errors),
        "native_beat_counts": dict(sorted(native_counts.items())),
        "other_symbol_counts": dict(sorted(other_counts.items())),
        "held_out_records_byte_equal": held_out_equal,
        "records": revised_records,
        "replacements": replacements,
        "errors": errors,
        "signals_downloaded_for_integrity_validation": True,
        "signals_modified": False,
        "locked_databases_accessed": False,
    }
    summary_path = output / "revised_annotation_audit.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "sha256_manifest.txt").write_text(
        f"{_sha256_file(summary_path)}  revised_annotation_audit.json\n", encoding="ascii"
    )
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a deterministic finite-record replacement audit")
    parser.add_argument("--annotation-audit", required=True, type=Path)
    parser.add_argument("--signal-audit", required=True, type=Path)
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args(argv)
    summary = run_replacement(
        args.annotation_audit,
        args.signal_audit,
        args.source_root,
        args.output_dir,
        run_id=args.run_id,
    )
    print(
        json.dumps(
            {key: value for key, value in summary.items() if key not in {"records", "cohort"}},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if summary["error_count"] == 0 and summary["replacement_count"] == summary["expected_replacement_count"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
