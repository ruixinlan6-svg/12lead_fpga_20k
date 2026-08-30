"""QRS reference evaluation and M1 evidence-package generation."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class EvaluationError(ValueError):
    """Raised for invalid evaluation inputs or unsafe denominator use."""


@dataclass(frozen=True)
class QRSCounts:
    qtp: int
    qfn: int
    qfp: int

    @property
    def reference_count(self) -> int:
        return self.qtp + self.qfn

    @property
    def output_count(self) -> int:
        return self.qtp + self.qfp


def metric_percentage(numerator: int, denominator: int) -> float | str:
    if numerator < 0 or denominator < 0 or numerator > denominator:
        raise EvaluationError("invalid metric numerator/denominator")
    if denominator == 0:
        return "N/A"
    return numerator / denominator * 100.0


def match_qrs_peaks(
    reference_indices: Sequence[int], detected_indices: Sequence[int], *, tolerance_ms: float = 150.0, sample_rate_hz: int = 250
) -> QRSCounts:
    if sample_rate_hz <= 0 or tolerance_ms < 0:
        raise EvaluationError("invalid matching configuration")
    reference = sorted(int(index) for index in reference_indices)
    detected = sorted(int(index) for index in detected_indices)
    tolerance_samples = tolerance_ms * sample_rate_hz / 1000.0
    used: set[int] = set()
    true_positive = 0
    false_negative = 0
    for reference_index in reference:
        candidates = [
            (abs(detected_index - reference_index), position, detected_index)
            for position, detected_index in enumerate(detected)
            if position not in used and abs(detected_index - reference_index) <= tolerance_samples
        ]
        if not candidates:
            false_negative += 1
            continue
        _, position, _ = min(candidates)
        used.add(position)
        true_positive += 1
    false_positive = len(detected) - len(used)
    return QRSCounts(true_positive, false_negative, false_positive)


def counts_to_metrics(counts: QRSCounts) -> dict[str, int | float | str]:
    return {
        "QTP": counts.qtp,
        "QFN": counts.qfn,
        "QFP": counts.qfp,
        "qrs_se_percent": metric_percentage(counts.qtp, counts.qtp + counts.qfn),
        "qrs_plus_p_percent": metric_percentage(counts.qtp, counts.qtp + counts.qfp),
    }


def annotation_support_span(
    reference_indices: Sequence[int], *, sample_rate_hz: int, tolerance_ms: float
) -> tuple[float, float]:
    """Return exact inclusive LUDB annotation-support bounds in sample units."""
    if sample_rate_hz <= 0 or tolerance_ms < 0:
        raise EvaluationError("invalid annotation-support configuration")
    if not reference_indices:
        raise EvaluationError("annotation support requires at least one reference QRS")
    reference = sorted(int(index) for index in reference_indices)
    tolerance_samples = tolerance_ms * sample_rate_hz / 1000.0
    return reference[0] - tolerance_samples, reference[-1] + tolerance_samples


def evaluate_record(
    record_id: str,
    reference_indices: Sequence[int],
    detected_indices: Sequence[int],
    *,
    sample_rate_hz: int = 250,
    learning_period_s: float = 300.0,
    evaluation_span: tuple[float, float] | None = None,
) -> dict[str, object]:
    if learning_period_s < 0:
        raise EvaluationError("learning period cannot be negative")
    learning_samples = int(round(learning_period_s * sample_rate_hz))
    reference = [index for index in reference_indices if index >= learning_samples]
    detected = [index for index in detected_indices if index >= learning_samples]
    if evaluation_span is not None:
        span_start, span_stop = evaluation_span
        reference = [index for index in reference if span_start <= index <= span_stop]
        detected = [index for index in detected if span_start <= index <= span_stop]
    counts = match_qrs_peaks(reference, detected, sample_rate_hz=sample_rate_hz)
    return {"record_id": record_id, "learning_period_s": learning_period_s, **counts_to_metrics(counts)}


def evaluate_records(
    records: Iterable[tuple[str, Sequence[int], Sequence[int]]],
    *,
    sample_rate_hz: int = 250,
    learning_period_s: float = 300.0,
) -> dict[str, object]:
    per_record = [
        evaluate_record(
            record_id,
            reference,
            detected,
            sample_rate_hz=sample_rate_hz,
            learning_period_s=learning_period_s,
        )
        for record_id, reference, detected in records
    ]
    totals = {"QTP": 0, "QFN": 0, "QFP": 0}
    for result in per_record:
        for key in totals:
            totals[key] += int(result[key])
    gross = counts_to_metrics(QRSCounts(totals["QTP"], totals["QFN"], totals["QFP"]))
    record_se = [result["qrs_se_percent"] for result in per_record if result["qrs_se_percent"] != "N/A"]
    record_plus_p = [result["qrs_plus_p_percent"] for result in per_record if result["qrs_plus_p_percent"] != "N/A"]
    average_se: float | str = sum(record_se) / len(record_se) if record_se else "N/A"
    average_plus_p: float | str = sum(record_plus_p) / len(record_plus_p) if record_plus_p else "N/A"
    return {
        "per_record": per_record,
        "gross": gross,
        "average": {"qrs_se_percent": average_se, "qrs_plus_p_percent": average_plus_p},
    }


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def generate_reference_evidence(
    output_dir: str | Path,
    *,
    run_id: str,
    ludb_present: bool = False,
    synthetic_peaks: Sequence[int] = (200, 500, 800),
) -> list[Path]:
    """Write an honest M1 evidence package without opening any database."""
    from build_registry import build_registry
    from qrs_detector import detect_qrs_fixed, detect_qrs_float

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    reference_peaks = [int(index) for index in synthetic_peaks]
    if (
        not reference_peaks
        or reference_peaks != sorted(reference_peaks)
        or len(reference_peaks) != len(set(reference_peaks))
        or reference_peaks[0] < 3
    ):
        raise EvaluationError("synthetic_peaks must be non-empty, unique, ordered, and at least three samples from start")

    signal_length = reference_peaks[-1] + 200
    synthetic_signal = [0] * signal_length
    pulse = ((-3, 80), (-2, 220), (-1, 700), (0, 1200), (1, 700), (2, 220), (3, 80))
    for peak in reference_peaks:
        if peak + 3 >= signal_length:
            raise EvaluationError("synthetic peak is outside the generated signal")
        for offset, value in pulse:
            synthetic_signal[peak + offset] += value
    float_result = detect_qrs_float(synthetic_signal)
    fixed_result = detect_qrs_fixed(synthetic_signal)
    evaluation = evaluate_records(
        [("synthetic-qrs", reference_peaks, float_result.peak_indices)],
        sample_rate_hz=250,
        learning_period_s=0,
    )

    registry_manifest_hash = ""
    patient_leakage_count = 0
    with tempfile.TemporaryDirectory() as data_dir_name, tempfile.TemporaryDirectory() as registry_dir_name:
        data_dir = Path(data_dir_name)
        registry_dir = Path(registry_dir_name)
        payload = b"synthetic registry execution; no ECG database bytes"
        raw_path = data_dir / "synthetic.dat"
        raw_path.write_bytes(payload)
        digest = hashlib.sha256(payload).hexdigest()
        record = {
            "record_id": "synthetic-record",
            "patient_id": "synthetic-patient",
            "split": "train",
            "duration_s": signal_length / 250,
            "raw_files": [
                {"relative_path": "synthetic.dat", "size_bytes": len(payload), "sha256": digest}
            ],
            "record_sha256": digest,
        }
        registry_outputs = build_registry(
            {"LUDB": data_dir},
            registry_dir,
            usage="qrs_development",
            records_by_database={"LUDB": [record]},
        )
        registry_manifests = [path for path in registry_outputs if path.name.endswith("dataset_manifest.json")]
        if len(registry_manifests) != 1:
            raise EvaluationError("synthetic registry execution did not emit exactly one manifest")
        registry_manifest_hash = _sha256_file(registry_manifests[0])
        ownership: dict[str, str] = {}
        for split in ("train", "validation", "internal_test"):
            split_path = registry_dir / f"{split}_patients.txt"
            for line in split_path.read_text(encoding="utf-8").splitlines():
                if not line:
                    continue
                patient = line.split("\t", 1)[-1]
                if patient in ownership and ownership[patient] != split:
                    patient_leakage_count += 1
                ownership[patient] = split

    contract_paths = [
        PROJECT_ROOT / "contracts" / "ec57_hybrid_io_contract.json",
        PROJECT_ROOT / "contracts" / "ec57_hybrid_metrics_contract.json",
        PROJECT_ROOT / "contracts" / "ec57_label_mapping_v1.json",
    ]
    manifest = {
        "run_id": run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "database_accessed": False,
        "ludb_present": bool(ludb_present),
        "ludb_evaluation_status": "not_evaluated" if not ludb_present else "not_run_in_m1_guarded_evidence_generation",
        "database_roots": "redacted; no database root was opened by this M1 run",
        "contract_sha256": {path.as_posix(): _sha256_file(path) for path in contract_paths},
        "synthetic_registry_manifest_sha256": registry_manifest_hash,
    }
    config = {
        "sample_rate_hz": 250,
        "qrs_bandpass_hz": [5.0, 25.0],
        "synthetic_learning_period_s": 0,
        "locked_database_learning_period_s": 300,
        "match_window_ms": 150,
        "sqi_window_samples": 500,
        "refractory_period_samples": 50,
        "searchback_rr_multiplier": 1.66,
        "synthetic_only": True,
    }
    per_record_header = [
        "record_id",
        "status",
        "reason",
        "QTP",
        "QFN",
        "QFP",
        "qrs_se_percent",
        "qrs_plus_p_percent",
    ]
    per_record_row = [
        "__LUDB_NOT_EVALUATED__",
        "not_evaluated",
        "local lawful LUDB root not present/used in M1",
        "",
        "",
        "",
        "N/A",
        "N/A",
    ]
    mismatch_positions = [
        index
        for index in range(max(len(float_result.peak_indices), len(fixed_result.peak_indices)))
        if (
            index >= len(float_result.peak_indices)
            or index >= len(fixed_result.peak_indices)
            or float_result.peak_indices[index] != fixed_result.peak_indices[index]
        )
    ]
    failures_header = ["case_id", "status", "reason", "source_sample_count"]
    failures_row = [
        "synthetic-qrs",
        "pass" if not mismatch_positions else "failed",
        "float/fixed detector execution" if not mismatch_positions else "float/fixed timestamp mismatch",
        str(signal_length),
    ]
    float_fixed = {
        "synthetic_case": "m1_synthetic_qrs",
        "reference_peak_indices": reference_peaks,
        "float_peak_indices": float_result.peak_indices,
        "fixed_peak_indices": fixed_result.peak_indices,
        "first_mismatch": mismatch_positions[0] if mismatch_positions else None,
        "mismatch_count": len(mismatch_positions),
        "status": "pass" if not mismatch_positions else "failed",
    }
    summary = {
        "run_id": run_id,
        "status": "synthetic_reference_only",
        "registry_executed": True,
        "detector_executed": True,
        "evaluator_executed": True,
        "patient_leakage_count": patient_leakage_count,
        "timestamp_error_gate_ms": 2,
        "float_fixed_qrs_timestamp_mismatch": len(mismatch_positions),
        "synthetic_evaluation": evaluation,
        "ludb_qrs_se": "not_evaluated",
        "ludb_qrs_plus_p": "not_evaluated",
        "notes": "No score is fabricated for LUDB or any locked database.",
    }
    root_registry = {
        "run_id": run_id,
        "database_roots_opened": False,
        "path_policy": "paths are intentionally omitted from this report",
        "registered_databases": [
            {"database": "Icentia11k", "role": "development/internal", "root_supplied": False},
            {"database": "LUDB", "role": "development", "root_supplied": False},
            {"database": "INCART", "role": "locked", "root_supplied": False},
            {"database": "MIT-BIH Arrhythmia", "role": "locked", "root_supplied": False},
            {"database": "AHA Ventricular Arrhythmia", "role": "locked", "root_supplied": False},
            {"database": "MIT-BIH Noise Stress Test", "role": "locked", "root_supplied": False},
        ],
        "repository_candidate_scan": "not performed; only a temporary synthetic registry root was opened",
    }
    outputs: dict[str, str] = {
        "config.json": json.dumps(config, ensure_ascii=False, indent=2) + "\n",
        "manifest_hashes.json": json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        "float_fixed_qrs_diff.json": json.dumps(float_fixed, ensure_ascii=False, indent=2) + "\n",
        "summary.json": json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        "data_root_registry.json": json.dumps(root_registry, ensure_ascii=False, indent=2) + "\n",
    }
    written: list[Path] = []
    for name, content in outputs.items():
        path = output_dir / name
        path.write_text(content, encoding="utf-8")
        written.append(path)
    for name, header, row in (
        ("ludb_per_record_metrics.csv", per_record_header, per_record_row),
        ("failed_samples.csv", failures_header, failures_row),
    ):
        path = output_dir / name
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(header)
            writer.writerow(row)
        written.append(path)
    return written


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate guarded synthetic M1 QRS evidence")
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--ludb-present", action="store_true")
    args = parser.parse_args(argv)
    generate_reference_evidence(args.output_dir, run_id=args.run_id, ludb_present=args.ludb_present)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
