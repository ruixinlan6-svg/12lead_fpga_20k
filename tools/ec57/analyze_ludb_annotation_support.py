"""Diagnostic comparison of full-record and LUDB annotation-support QRS counts."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Sequence


ROOT_DIR = Path(__file__).resolve().parents[2]
TRAIN_EC57_DIR = ROOT_DIR / "train" / "ec57"
if str(TRAIN_EC57_DIR) not in sys.path:
    sys.path.insert(0, str(TRAIN_EC57_DIR))

from evaluate_qrs import match_qrs_peaks
from evaluate_ludb import select_and_fuse_record
from ludb_io import discover_ludb_records, load_ludb_record


class AnnotationSupportError(ValueError):
    """Raised when an annotation-support interval cannot be derived safely."""


def annotation_support(reference_indices: Sequence[int], *, tolerance_samples: int) -> tuple[int, int]:
    """Return the inclusive support around the first and last reference QRS."""
    if tolerance_samples < 0:
        raise AnnotationSupportError("tolerance_samples must be non-negative")
    if not reference_indices:
        raise AnnotationSupportError("annotation support requires at least one reference QRS")
    references = sorted(int(index) for index in reference_indices)
    return references[0] - tolerance_samples, references[-1] + tolerance_samples


def _counts_dict(counts: object) -> dict[str, int]:
    return {"QTP": int(counts.qtp), "QFN": int(counts.qfn), "QFP": int(counts.qfp)}


def dual_qrs_counts(
    reference_indices: Sequence[int],
    detected_indices: Sequence[int],
    *,
    sample_rate_hz: int,
    tolerance_ms: float,
) -> dict[str, object]:
    """Preserve full counts while separately scoring the annotated support."""
    if sample_rate_hz <= 0 or tolerance_ms < 0:
        raise AnnotationSupportError("invalid sampling rate or tolerance")
    tolerance_samples = int(tolerance_ms * sample_rate_hz / 1000.0 + 0.5)
    start, stop = annotation_support(reference_indices, tolerance_samples=tolerance_samples)
    references = [int(index) for index in reference_indices]
    detections = [int(index) for index in detected_indices]
    supported_detections = [index for index in detections if start <= index <= stop]
    unsupported = [index for index in detections if index < start or index > stop]
    full = match_qrs_peaks(references, detections, tolerance_ms=tolerance_ms, sample_rate_hz=sample_rate_hz)
    supported = match_qrs_peaks(
        references,
        supported_detections,
        tolerance_ms=tolerance_ms,
        sample_rate_hz=sample_rate_hz,
    )
    return {
        "full": _counts_dict(full),
        "annotation_support": _counts_dict(supported),
        "support_samples": [start, stop],
        "unsupported_detected_indices": unsupported,
    }


def aggregate_dual_reports(reports: Sequence[dict[str, object]]) -> dict[str, object]:
    """Aggregate full/support counts without merging their denominators."""
    totals = {
        "full": {"QTP": 0, "QFN": 0, "QFP": 0},
        "annotation_support": {"QTP": 0, "QFN": 0, "QFP": 0},
    }
    unsupported_count = 0
    for report in reports:
        for scope in totals:
            counts = report[scope]
            for key in totals[scope]:
                totals[scope][key] += int(counts[key])
        unsupported_count += len(report["unsupported_detected_indices"])

    summary: dict[str, object] = {"unsupported_detection_count": unsupported_count}
    for scope, counts in totals.items():
        qtp, qfn, qfp = counts["QTP"], counts["QFN"], counts["QFP"]
        per_record_se: list[float] = []
        per_record_plus_p: list[float] = []
        for report in reports:
            record_counts = report[scope]
            record_qtp = int(record_counts["QTP"])
            record_qfn = int(record_counts["QFN"])
            record_qfp = int(record_counts["QFP"])
            if record_qtp + record_qfn:
                per_record_se.append(record_qtp / (record_qtp + record_qfn) * 100.0)
            if record_qtp + record_qfp:
                per_record_plus_p.append(record_qtp / (record_qtp + record_qfp) * 100.0)
        summary[scope] = {
            "counts": counts,
            "qrs_se_percent": qtp / (qtp + qfn) * 100.0 if qtp + qfn else None,
            "qrs_plus_p_percent": qtp / (qtp + qfp) * 100.0 if qtp + qfp else None,
            "average_qrs_se_percent": sum(per_record_se) / len(per_record_se) if per_record_se else None,
            "average_qrs_plus_p_percent": sum(per_record_plus_p) / len(per_record_plus_p) if per_record_plus_p else None,
        }
    return summary


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def run_analysis(data_root: str | Path, output_dir: str | Path, *, run_id: str) -> dict[str, object]:
    """Run the diagnostic dual-scope comparison on all 200 LUDB records."""
    data_root = Path(data_root).resolve()
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    records = discover_ludb_records(data_root, expected_count=200)
    fixed_reports: list[dict[str, object]] = []
    float_reports: list[dict[str, object]] = []
    per_record: list[dict[str, object]] = []
    for position, record_id in enumerate(records, start=1):
        loaded = load_ludb_record(data_root, record_id)
        references = [reference.target_sample_index for reference in loaded.reference_qrs]
        fixed_peaks = select_and_fuse_record(loaded.signals_lsb_250, fixed=True).peak_indices
        float_peaks = select_and_fuse_record(loaded.signals_lsb_250, fixed=False).peak_indices
        fixed = dual_qrs_counts(references, fixed_peaks, sample_rate_hz=250, tolerance_ms=150.0)
        floating = dual_qrs_counts(references, float_peaks, sample_rate_hz=250, tolerance_ms=150.0)
        fixed_reports.append(fixed)
        float_reports.append(floating)
        per_record.append({"record_id": record_id, "fixed": fixed, "float": floating})
        if position % 10 == 0:
            print(f"LUDB_SUPPORT_PROGRESS {position}/200", flush=True)

    summary = {
        "run_id": run_id,
        "status": "diagnostic_only_contract_unchanged",
        "record_count": len(records),
        "sample_rate_hz": 250,
        "matching_tolerance_ms": 150.0,
        "support_rule": "inclusive [first_reference-150ms, last_reference+150ms]",
        "fixed": aggregate_dual_reports(fixed_reports),
        "float": aggregate_dual_reports(float_reports),
        "detector_outputs_modified": False,
        "shared_contract_modified": False,
        "locked_databases_accessed": False,
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output_dir / "per_record.json").write_text(json.dumps(per_record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest_lines = []
    for path in sorted(output_dir.iterdir(), key=lambda item: item.name):
        if path.is_file() and path.name != "sha256_manifest.txt":
            manifest_lines.append(f"{_sha256_file(path)}  {path.name}")
    (output_dir / "sha256_manifest.txt").write_text("\n".join(manifest_lines) + "\n", encoding="ascii")
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare full-record and LUDB annotation-support QRS metrics")
    parser.add_argument("--data-root", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args(argv)
    print(json.dumps(run_analysis(args.data_root, args.output_dir, run_id=args.run_id), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
