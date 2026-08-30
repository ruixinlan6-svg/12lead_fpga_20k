"""Full LUDB 1.0.1 development evaluation for the frozen M1 QRS path."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Sequence

from evaluate_qrs import QRSCounts, annotation_support_span, counts_to_metrics, evaluate_record
from ludb_io import (
    CANONICAL_LEADS,
    LUDB_LICENSE,
    LUDB_SOURCE_URL,
    LUDB_VERSION,
    TARGET_RATE_HZ,
    build_sha256_inventory,
    discover_ludb_records,
    load_ludb_record,
    verify_published_sha256s,
)
from qrs_detector import detect_qrs_fixed, detect_qrs_float, fuse_qrs_leads
from sqi import evaluate_sqi_fixed, evaluate_sqi_float


SQI_WINDOW_SAMPLES = 500
FUSION_MARGIN_SAMPLES = 20


@dataclass(frozen=True)
class WindowSelection:
    start_sample: int
    stop_sample: int
    selected_leads: tuple[str, ...]
    status: str
    fused_peak_count: int


@dataclass(frozen=True)
class FusedRecord:
    peak_indices: list[int]
    windows: tuple[WindowSelection, ...]


class LUDBEvaluationError(ValueError):
    """Raised when evaluation inputs or output accounting are invalid."""


def _round_half_away_from_zero(value: float) -> int:
    if value < 0:
        return -int(abs(value) + 0.5)
    return int(value + 0.5)


def _fixed_int16(values: Sequence[float | int]) -> list[int]:
    converted: list[int] = []
    for value in values:
        quantized = _round_half_away_from_zero(float(value))
        converted.append(min(max(quantized, -32768), 32767))
    return converted


def _select_window_leads(
    signal_by_lead: Mapping[str, Sequence[float | int]],
    peaks_by_lead: Mapping[str, Sequence[int]],
    *,
    start: int,
    stop: int,
    fixed: bool,
) -> list[str]:
    qualities = {}
    for lead in CANONICAL_LEADS:
        window = signal_by_lead[lead][start:stop]
        candidate_count = sum(start <= peak < stop for peak in peaks_by_lead[lead])
        if fixed:
            quality = evaluate_sqi_fixed(window, qrs_candidate_count=candidate_count)
        else:
            quality = evaluate_sqi_float(window, qrs_candidate_count=candidate_count)
        qualities[lead] = quality
    valid = [lead for lead in CANONICAL_LEADS if qualities[lead].valid]
    valid.sort(key=lambda lead: (qualities[lead].ranking_key, CANONICAL_LEADS.index(lead)))
    return valid[:3]


def select_and_fuse_record(
    signals_by_lead: Mapping[str, Sequence[float | int]],
    *,
    fixed: bool,
) -> FusedRecord:
    if set(signals_by_lead) != set(CANONICAL_LEADS):
        raise LUDBEvaluationError("evaluation requires exactly the canonical 12 leads")
    lengths = {len(signals_by_lead[lead]) for lead in CANONICAL_LEADS}
    if len(lengths) != 1:
        raise LUDBEvaluationError("all LUDB leads must have the same target length")
    signal_length = lengths.pop()
    if signal_length == 0 or signal_length % SQI_WINDOW_SAMPLES:
        raise LUDBEvaluationError("target signal length must be a non-zero multiple of 500 samples")
    if fixed:
        working: dict[str, Sequence[float | int]] = {
            lead: _fixed_int16(signals_by_lead[lead]) for lead in CANONICAL_LEADS
        }
        peaks_by_lead = {
            lead: detect_qrs_fixed(working[lead], sample_rate_hz=TARGET_RATE_HZ).peak_indices
            for lead in CANONICAL_LEADS
        }
    else:
        working = {lead: [float(value) for value in signals_by_lead[lead]] for lead in CANONICAL_LEADS}
        peaks_by_lead = {
            lead: detect_qrs_float(working[lead], sample_rate_hz=TARGET_RATE_HZ).peak_indices
            for lead in CANONICAL_LEADS
        }
    fused_all: list[int] = []
    windows: list[WindowSelection] = []
    for start in range(0, signal_length, SQI_WINDOW_SAMPLES):
        stop = start + SQI_WINDOW_SAMPLES
        selected = _select_window_leads(working, peaks_by_lead, start=start, stop=stop, fixed=fixed)
        candidate_map = {
            lead: [
                peak
                for peak in peaks_by_lead[lead]
                if start - FUSION_MARGIN_SAMPLES <= peak < stop + FUSION_MARGIN_SAMPLES
            ]
            for lead in selected
        }
        fused = fuse_qrs_leads(candidate_map, selected)
        in_window = [peak for peak in fused.peak_indices if start <= peak < stop]
        for p in in_window:
            if not fused_all or p - fused_all[-1] >= 50:
                fused_all.append(p)
        windows.append(
            WindowSelection(
                start_sample=start,
                stop_sample=stop,
                selected_leads=tuple(selected),
                status=fused.status,
                fused_peak_count=len(in_window),
            )
        )
    return FusedRecord(peak_indices=sorted(set(fused_all)), windows=tuple(windows))


def _timestamp_mismatches(float_peaks: Sequence[int], fixed_peaks: Sequence[int]) -> list[dict[str, int | None]]:
    mismatches: list[dict[str, int | None]] = []
    for position in range(max(len(float_peaks), len(fixed_peaks))):
        float_peak = int(float_peaks[position]) if position < len(float_peaks) else None
        fixed_peak = int(fixed_peaks[position]) if position < len(fixed_peaks) else None
        if float_peak != fixed_peak:
            mismatches.append({"position": position, "float_peak": float_peak, "fixed_peak": fixed_peak})
    return mismatches


def evaluate_loaded_record(
    *,
    record_id: str,
    signals_lsb_250: Mapping[str, Sequence[float | int]],
    reference_indices_250: Sequence[int],
    max_mapping_error_ms: float,
) -> dict[str, object]:
    float_result = select_and_fuse_record(signals_lsb_250, fixed=False)
    fixed_result = select_and_fuse_record(signals_lsb_250, fixed=True)
    support_span = annotation_support_span(
        reference_indices_250,
        sample_rate_hz=TARGET_RATE_HZ,
        tolerance_ms=150.0,
    )
    float_metrics = evaluate_record(
        record_id,
        reference_indices_250,
        float_result.peak_indices,
        sample_rate_hz=TARGET_RATE_HZ,
        learning_period_s=0,
        evaluation_span=None,
    )
    fixed_metrics = evaluate_record(
        record_id,
        reference_indices_250,
        fixed_result.peak_indices,
        sample_rate_hz=TARGET_RATE_HZ,
        learning_period_s=0,
        evaluation_span=None,
    )
    float_support_metrics = evaluate_record(
        record_id,
        reference_indices_250,
        float_result.peak_indices,
        sample_rate_hz=TARGET_RATE_HZ,
        learning_period_s=0,
        evaluation_span=support_span,
    )
    fixed_support_metrics = evaluate_record(
        record_id,
        reference_indices_250,
        fixed_result.peak_indices,
        sample_rate_hz=TARGET_RATE_HZ,
        learning_period_s=0,
        evaluation_span=support_span,
    )
    mismatches = _timestamp_mismatches(float_result.peak_indices, fixed_result.peak_indices)
    return {
        "record_id": record_id,
        "status": "evaluated",
        # Default alias points to fixed path
        "QTP": fixed_metrics["QTP"],
        "QFN": fixed_metrics["QFN"],
        "QFP": fixed_metrics["QFP"],
        "qrs_se_percent": fixed_metrics["qrs_se_percent"],
        "qrs_plus_p_percent": fixed_metrics["qrs_plus_p_percent"],
        # Explicit independent metrics
        "float_QTP": float_metrics["QTP"],
        "float_QFN": float_metrics["QFN"],
        "float_QFP": float_metrics["QFP"],
        "float_qrs_se_percent": float_metrics["qrs_se_percent"],
        "float_qrs_plus_p_percent": float_metrics["qrs_plus_p_percent"],
        "fixed_QTP": fixed_metrics["QTP"],
        "fixed_QFN": fixed_metrics["QFN"],
        "fixed_QFP": fixed_metrics["QFP"],
        "fixed_qrs_se_percent": fixed_metrics["qrs_se_percent"],
        "fixed_qrs_plus_p_percent": fixed_metrics["qrs_plus_p_percent"],
        "fixed_full": fixed_metrics,
        "float_full": float_metrics,
        "fixed_annotation_support": fixed_support_metrics,
        "float_annotation_support": float_support_metrics,
        "support_start_sample": support_span[0],
        "support_stop_sample": support_span[1],
        "support_fixed_QTP": fixed_support_metrics["QTP"],
        "support_fixed_QFN": fixed_support_metrics["QFN"],
        "support_fixed_QFP": fixed_support_metrics["QFP"],
        "support_fixed_qrs_se_percent": fixed_support_metrics["qrs_se_percent"],
        "support_fixed_qrs_plus_p_percent": fixed_support_metrics["qrs_plus_p_percent"],
        "support_float_QTP": float_support_metrics["QTP"],
        "support_float_QFN": float_support_metrics["QFN"],
        "support_float_QFP": float_support_metrics["QFP"],
        "support_float_qrs_se_percent": float_support_metrics["qrs_se_percent"],
        "support_float_qrs_plus_p_percent": float_support_metrics["qrs_plus_p_percent"],
        "gate_scope": "fixed_annotation_support",
        "full_record_metrics_role": "required_diagnostic",
        "reference_count": len(reference_indices_250),
        "float_output_count": len(float_result.peak_indices),
        "fixed_output_count": len(fixed_result.peak_indices),
        "max_mapping_error_ms": float(max_mapping_error_ms),
        "float_fixed_mismatch_count": len(mismatches),
        "float_fixed_first_mismatch": mismatches[0] if mismatches else None,
        "float_peak_indices": float_result.peak_indices,
        "fixed_peak_indices": fixed_result.peak_indices,
        "float_windows": [asdict(window) for window in float_result.windows],
        "fixed_windows": [asdict(window) for window in fixed_result.windows],
    }


def _aggregate_report_scope(
    reports: Sequence[Mapping[str, object]], scope_key: str
) -> tuple[dict[str, int | float | str], dict[str, float | str]]:
    scoped = [report[scope_key] for report in reports]
    totals = QRSCounts(
        qtp=sum(int(result["QTP"]) for result in scoped),
        qfn=sum(int(result["QFN"]) for result in scoped),
        qfp=sum(int(result["QFP"]) for result in scoped),
    )
    gross = counts_to_metrics(totals)
    se_values = [float(result["qrs_se_percent"]) for result in scoped if result["qrs_se_percent"] != "N/A"]
    ppv_values = [
        float(result["qrs_plus_p_percent"]) for result in scoped if result["qrs_plus_p_percent"] != "N/A"
    ]
    average: dict[str, float | str] = {
        "qrs_se_percent": sum(se_values) / len(se_values) if se_values else "N/A",
        "qrs_plus_p_percent": sum(ppv_values) / len(ppv_values) if ppv_values else "N/A",
    }
    return gross, average


def _m1_gate_passes(gross: Mapping[str, object], average: Mapping[str, object]) -> bool:
    metric_values = (
        gross["qrs_se_percent"],
        gross["qrs_plus_p_percent"],
        average["qrs_se_percent"],
        average["qrs_plus_p_percent"],
    )
    return (
        all(isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 99.5 for value in metric_values)
        and int(gross["QFN"]) <= 9
        and int(gross["QFP"]) <= 9
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _package_versions() -> dict[str, str]:
    versions: dict[str, str] = {"python": platform.python_version()}
    for package_name in ("wfdb", "numpy", "scipy"):
        try:
            package = __import__(package_name)
            versions[package_name] = str(getattr(package, "__version__", "unknown"))
        except ImportError:
            versions[package_name] = "not_installed"
    return versions


def run_ludb_evaluation(data_root: str | Path, output_dir: str | Path, *, run_id: str) -> dict[str, object]:
    data_root = Path(data_root).resolve()
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    records = discover_ludb_records(data_root, expected_count=200)
    published_verification = verify_published_sha256s(data_root)
    inventory = build_sha256_inventory(data_root)
    reports: list[dict[str, object]] = []
    errors: list[dict[str, str]] = []
    diffs: list[dict[str, object]] = []
    annotation_counts: dict[str, dict[str, int]] = {}
    for position, record_id in enumerate(records, start=1):
        try:
            loaded = load_ludb_record(data_root, record_id)
            reference_indices = [reference.target_sample_index for reference in loaded.reference_qrs]
            max_mapping_error = max((reference.mapping_error_ms for reference in loaded.reference_qrs), default=0.0)
            report = evaluate_loaded_record(
                record_id=record_id,
                signals_lsb_250=loaded.signals_lsb_250,
                reference_indices_250=reference_indices,
                max_mapping_error_ms=max_mapping_error,
            )
            reports.append(report)
            annotation_counts[record_id] = loaded.annotation_counts_by_lead
            if int(report["float_fixed_mismatch_count"]):
                diffs.append(
                    {
                        "record_id": record_id,
                        "mismatch_count": report["float_fixed_mismatch_count"],
                        "first_mismatch": report["float_fixed_first_mismatch"],
                    }
                )
        except Exception as exc:
            errors.append({"record_id": record_id, "error_type": type(exc).__name__, "reason": str(exc)})
        if position % 10 == 0 or position == len(records):
            print(f"LUDB_PROGRESS {position}/{len(records)} evaluated={len(reports)} errors={len(errors)}", flush=True)

    totals_float = QRSCounts(
        qtp=sum(int(report["float_QTP"]) for report in reports),
        qfn=sum(int(report["float_QFN"]) for report in reports),
        qfp=sum(int(report["float_QFP"]) for report in reports),
    )
    gross_float = counts_to_metrics(totals_float)
    se_float_vals = [float(report["float_qrs_se_percent"]) for report in reports if report["float_qrs_se_percent"] != "N/A"]
    ppv_float_vals = [float(report["float_qrs_plus_p_percent"]) for report in reports if report["float_qrs_plus_p_percent"] != "N/A"]
    average_float = {
        "qrs_se_percent": sum(se_float_vals) / len(se_float_vals) if se_float_vals else "N/A",
        "qrs_plus_p_percent": sum(ppv_float_vals) / len(ppv_float_vals) if ppv_float_vals else "N/A",
    }

    totals_fixed = QRSCounts(
        qtp=sum(int(report["fixed_QTP"]) for report in reports),
        qfn=sum(int(report["fixed_QFN"]) for report in reports),
        qfp=sum(int(report["fixed_QFP"]) for report in reports),
    )
    gross_fixed = counts_to_metrics(totals_fixed)
    se_fixed_vals = [float(report["fixed_qrs_se_percent"]) for report in reports if report["fixed_qrs_se_percent"] != "N/A"]
    ppv_fixed_vals = [float(report["fixed_qrs_plus_p_percent"]) for report in reports if report["fixed_qrs_plus_p_percent"] != "N/A"]
    average_fixed = {
        "qrs_se_percent": sum(se_fixed_vals) / len(se_fixed_vals) if se_fixed_vals else "N/A",
        "qrs_plus_p_percent": sum(ppv_fixed_vals) / len(ppv_fixed_vals) if ppv_fixed_vals else "N/A",
    }

    gross_fixed_support, average_fixed_support = _aggregate_report_scope(reports, "fixed_annotation_support")
    gross_float_support, average_float_support = _aggregate_report_scope(reports, "float_annotation_support")

    total_mismatches = sum(int(report["float_fixed_mismatch_count"]) for report in reports)
    maximum_mapping_error = max((float(report["max_mapping_error_ms"]) for report in reports), default=0.0)
    metrics_pass = _m1_gate_passes(gross_fixed_support, average_fixed_support)
    accepted = (
        len(records) == 200
        and len(reports) == 200
        and not errors
        and metrics_pass
        and maximum_mapping_error <= 2.0 + 1e-12
    )
    summary: dict[str, object] = {
        "run_id": run_id,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "database": "LUDB",
        "database_version": LUDB_VERSION,
        "role": "qrs_development_only",
        "record_count_discovered": len(records),
        "record_count_evaluated": len(reports),
        "record_count_failed": len(errors),
        "gross": gross_fixed,
        "average": average_fixed,
        "gross_float": gross_float,
        "average_float": average_float,
        "gross_fixed": gross_fixed,
        "average_fixed": average_fixed,
        "gate_scope": "fixed_annotation_support",
        "gate_metrics": {"gross": gross_fixed_support, "average": average_fixed_support},
        "gross_fixed_annotation_support": gross_fixed_support,
        "average_fixed_annotation_support": average_fixed_support,
        "gross_float_annotation_support": gross_float_support,
        "average_float_annotation_support": average_float_support,
        "full_record_metrics_role": "required_diagnostic",
        "float_reference_role": "independent_diagnostic",
        "bit_exact_chain": ["integer_python_reference", "rtl_simulation", "QN88_SRAM_FPGA"],
        "float_fixed_timestamp_mismatch_count": total_mismatches,
        "max_annotation_mapping_error_ms": maximum_mapping_error,
        "thresholds": {"qrs_se_percent_min": 99.5, "qrs_plus_p_percent_min": 99.5},
        "accepted": accepted,
        "decision": "接受" if accepted else "回到训练",
        "milestone": "M1-reference-accepted" if accepted else "M1-reference-open",
        "locked_databases_accessed": False,
    }
    config = {
        "run_id": run_id,
        "source_rate_hz": 500,
        "target_rate_hz": 250,
        "record_duration_s": 10,
        "learning_period_s": 0,
        "canonical_leads": list(CANONICAL_LEADS),
        "sqi_window_samples": SQI_WINDOW_SAMPLES,
        "sqi_windows_per_record": 5,
        "selected_valid_leads": 3,
        "lead_fusion": "inclusive 2-of-3 within 20 target samples (80 ms)",
        "reference_construction": "median of independently annotated lead-specific WFDB N peaks clustered within 150 ms",
        "match_tolerance_ms": 150,
        "gate_scope": "fixed_annotation_support",
        "annotation_support_rule": "inclusive [first_reference-150ms, last_reference+150ms] using exact time-domain bounds",
        "full_record_metrics": "required_diagnostic",
        "float_reference_role": "independent_diagnostic",
        "signal_interface": "signed int16, 1 LSB = 5 microvolts",
    }
    source_metadata = {
        "database": "Lobachevsky University Electrocardiography Database",
        "version": LUDB_VERSION,
        "official_fixed_version_url": LUDB_SOURCE_URL,
        "download_archive_url": "https://physionet.org/content/ludb/get-zip/1.0.1/",
        "doi": "10.13026/eegm-h675",
        "license": LUDB_LICENSE,
        "license_summary": "Open data; attribution is required. See the bundled LICENSE.txt for controlling terms.",
        "published_sha256_verification": published_verification,
    }
    json_outputs = {
        "config.json": config,
        "source_metadata.json": source_metadata,
        "environment.json": {"platform": platform.platform(), "packages": _package_versions(), "gpu_used": False},
        "summary.json": summary,
        "ludb_raw_file_manifest.json": {"database": "LUDB", "version": LUDB_VERSION, "files": inventory},
        "annotation_counts_by_record.json": annotation_counts,
        "float_fixed_qrs_diff.json": {"mismatch_count": total_mismatches, "records": diffs},
        "evaluation_errors.json": errors,
    }
    for name, payload in json_outputs.items():
        (output_dir / name).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    per_record_columns = [
        "record_id",
        "status",
        "QTP",
        "QFN",
        "QFP",
        "qrs_se_percent",
        "qrs_plus_p_percent",
        "float_QTP",
        "float_QFN",
        "float_QFP",
        "float_qrs_se_percent",
        "float_qrs_plus_p_percent",
        "fixed_QTP",
        "fixed_QFN",
        "fixed_QFP",
        "fixed_qrs_se_percent",
        "fixed_qrs_plus_p_percent",
        "support_start_sample",
        "support_stop_sample",
        "support_fixed_QTP",
        "support_fixed_QFN",
        "support_fixed_QFP",
        "support_fixed_qrs_se_percent",
        "support_fixed_qrs_plus_p_percent",
        "support_float_QTP",
        "support_float_QFN",
        "support_float_QFP",
        "support_float_qrs_se_percent",
        "support_float_qrs_plus_p_percent",
        "reference_count",
        "float_output_count",
        "fixed_output_count",
        "max_mapping_error_ms",
        "float_fixed_mismatch_count",
    ]
    with (output_dir / "ludb_per_record_metrics.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=per_record_columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(reports)
    failure_columns = ["record_id", "status", "QFN", "QFP", "float_fixed_mismatch_count", "reason"]
    with (output_dir / "failed_samples.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=failure_columns, extrasaction="ignore")
        writer.writeheader()
        for report in reports:
            if int(report["QFN"]) or int(report["QFP"]) or int(report["float_fixed_mismatch_count"]):
                writer.writerow({**report, "reason": "QRS miss/false-positive or float/fixed mismatch"})
        for error in errors:
            writer.writerow({**error, "status": "evaluation_error"})
    manifest_lines = []
    for path in sorted(output_dir.iterdir(), key=lambda item: item.name):
        if path.is_file() and path.name != "sha256_manifest.txt":
            manifest_lines.append(f"{_sha256_file(path)}  {path.name}")
    (output_dir / "sha256_manifest.txt").write_text("\n".join(manifest_lines) + "\n", encoding="ascii")
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate all 200 LUDB 1.0.1 records for the M1 QRS gate")
    parser.add_argument("--data-root", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args(argv)
    summary = run_ludb_evaluation(args.data_root, args.output_dir, run_id=args.run_id)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
