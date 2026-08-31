"""Read-only signal-integrity audit for an accepted Icentia cohort."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np


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


def extract_contiguous_runs(indices: Iterable[int]) -> list[dict[str, int]]:
    ordered = sorted(set(int(index) for index in indices))
    if not ordered:
        return []
    runs: list[dict[str, int]] = []
    start = previous = ordered[0]
    for index in ordered[1:]:
        if index != previous + 1:
            runs.append({"start": start, "stop_exclusive": previous + 1, "length": previous - start + 1})
            start = index
        previous = index
    runs.append({"start": start, "stop_exclusive": previous + 1, "length": previous - start + 1})
    return runs


def analyze_signal_integrity(
    physical_signal: np.ndarray,
    digital_signal: np.ndarray,
    *,
    beat_samples: Iterable[int],
    beat_symbols: Iterable[str],
) -> dict[str, object]:
    physical = np.asarray(physical_signal)
    digital = np.asarray(digital_signal)
    if physical.ndim != 1 or digital.ndim != 1 or physical.shape != digital.shape:
        raise ValueError("physical and digital signals must be equal-length vectors")
    bad = np.flatnonzero(~np.isfinite(physical))
    affected_beats: list[dict[str, object]] = []
    affected_counts: Counter[str] = Counter()
    for sample, symbol in zip(beat_samples, beat_symbols):
        native_symbol = str(symbol)
        if native_symbol not in NATIVE_BEAT_SYMBOLS:
            continue
        beat_sample = int(sample)
        left = int(np.searchsorted(bad, beat_sample - 404, side="left"))
        right = int(np.searchsorted(bad, beat_sample + 96, side="left"))
        if right > left:
            affected_beats.append({"sample_index": beat_sample, "symbol": native_symbol})
            affected_counts[native_symbol] += 1
    return {
        "nonfinite_sample_count": int(len(bad)),
        "missing_runs": extract_contiguous_runs(bad),
        "digital_values_at_nonfinite": sorted({int(value) for value in digital[bad]}),
        "affected_beats": affected_beats,
        "affected_native_symbol_counts": dict(sorted(affected_counts.items())),
    }


def run_audit(
    annotation_audit: str | Path,
    source_manifest: str | Path,
    source_root: str | Path,
    output_dir: str | Path,
    *,
    run_id: str,
) -> dict[str, object]:
    import wfdb

    annotation_path = Path(annotation_audit).resolve()
    source_manifest_path = Path(source_manifest).resolve()
    source = Path(source_root).resolve()
    output = Path(output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    cohort = json.loads(annotation_path.read_text(encoding="utf-8"))
    source_inventory = json.loads(source_manifest_path.read_text(encoding="utf-8"))
    if cohort.get("database") != "Icentia11k" or cohort.get("database_version") != "1.0":
        raise ValueError("annotation audit is not Icentia11k 1.0")
    if int(cohort.get("error_count", -1)) != 0 or not cohort.get("records"):
        raise ValueError("annotation audit is incomplete or contains errors")
    if int(source_inventory.get("record_count", -1)) != len(cohort["records"]):
        raise ValueError("source manifest record count differs from annotation audit")
    expected_hashes = {
        str(item["relative_path"]): str(item["sha256"])
        for item in source_inventory.get("source_files", [])
    }

    reports: list[dict[str, object]] = []
    errors: list[dict[str, str]] = []
    affected_symbol_counts: Counter[str] = Counter()
    missing_run_length_counts: Counter[int] = Counter()
    split_missing_counts: Counter[str] = Counter()
    for position, row in enumerate(cohort["records"], start=1):
        split = str(row["split"])
        patient_id = str(row["patient_id"])
        record_id = str(row["record_id"])
        dat_relative = source_relative_files(patient_id, record_id)[1]
        record_base = source / patient_id[:3] / patient_id / record_id
        try:
            actual_dat_hash = _sha256_file(source / dat_relative)
            expected_dat_hash = expected_hashes.get(dat_relative)
            if expected_dat_hash is None or actual_dat_hash != expected_dat_hash:
                raise ValueError(f"source dat hash mismatch: {dat_relative}")
            physical_record = wfdb.rdrecord(str(record_base), physical=True)
            digital_record = wfdb.rdrecord(str(record_base), physical=False)
            if (
                float(physical_record.fs) != 250.0
                or int(physical_record.n_sig) != 1
                or int(digital_record.n_sig) != 1
                or int(physical_record.sig_len) != int(digital_record.sig_len)
            ):
                raise ValueError("unexpected Icentia signal contract")
            annotation = wfdb.rdann(str(record_base), "atr")
            integrity = analyze_signal_integrity(
                np.asarray(physical_record.p_signal[:, 0]),
                np.asarray(digital_record.d_signal[:, 0]),
                beat_samples=annotation.sample,
                beat_symbols=annotation.symbol,
            )
            for symbol, count in integrity["affected_native_symbol_counts"].items():
                affected_symbol_counts[str(symbol)] += int(count)
            for run in integrity["missing_runs"]:
                missing_run_length_counts[int(run["length"])] += 1
            split_missing_counts[split] += int(integrity["nonfinite_sample_count"])
            reports.append(
                {
                    "split": split,
                    "patient_id": patient_id,
                    "record_id": record_id,
                    "dat_relative_path": dat_relative,
                    "dat_sha256": actual_dat_hash,
                    "sample_rate_hz": float(physical_record.fs),
                    "signal_length": int(physical_record.sig_len),
                    **integrity,
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
            f"ICENTIA_SIGNAL_AUDIT {position}/{len(cohort['records'])} "
            f"affected_records={sum(int(item['nonfinite_sample_count']) > 0 for item in reports)} "
            f"errors={len(errors)}",
            flush=True,
        )

    summary: dict[str, object] = {
        "run_id": run_id,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "database": "Icentia11k",
        "database_version": "1.0",
        "annotation_audit_sha256": _sha256_file(annotation_path),
        "source_manifest_sha256": _sha256_file(source_manifest_path),
        "record_count": len(reports),
        "expected_record_count": len(cohort["records"]),
        "source_file_count": int(source_inventory.get("source_file_count", 0)),
        "dat_hash_count": len(reports),
        "clean_record_count": sum(int(item["nonfinite_sample_count"]) == 0 for item in reports),
        "affected_record_count": sum(int(item["nonfinite_sample_count"]) > 0 for item in reports),
        "nonfinite_sample_count": sum(int(item["nonfinite_sample_count"]) for item in reports),
        "split_nonfinite_sample_counts": dict(sorted(split_missing_counts.items())),
        "missing_run_length_counts": {
            str(length): count for length, count in sorted(missing_run_length_counts.items())
        },
        "affected_native_symbol_counts": dict(sorted(affected_symbol_counts.items())),
        "error_count": len(errors),
        "records": reports,
        "errors": errors,
        "locked_databases_accessed": False,
        "signals_modified": False,
        "cache_built": False,
        "gpu_training_started": False,
        "internal_test_model_evaluated": False,
    }
    summary_path = output / "signal_integrity_audit.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "sha256_manifest.txt").write_text(
        f"{_sha256_file(summary_path)}  signal_integrity_audit.json\n", encoding="ascii"
    )
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit Icentia signal missing-value integrity")
    parser.add_argument("--annotation-audit", required=True, type=Path)
    parser.add_argument("--source-manifest", required=True, type=Path)
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args(argv)
    summary = run_audit(
        args.annotation_audit,
        args.source_manifest,
        args.source_root,
        args.output_dir,
        run_id=args.run_id,
    )
    print(json.dumps({key: value for key, value in summary.items() if key not in {"records"}}, ensure_ascii=False, indent=2))
    return 0 if summary["error_count"] == 0 and summary["record_count"] == summary["expected_record_count"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
