"""False positive taxonomy and breakdown analysis tool for LUDB QRS detection."""

from __future__ import annotations

import csv
import json
import math
import sys
from pathlib import Path
from typing import Dict, List, Tuple

# Add train/ec57 to sys.path
ROOT_DIR = Path(__file__).resolve().parents[2]
TRAIN_EC57_DIR = ROOT_DIR / "train" / "ec57"
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
if str(TRAIN_EC57_DIR) not in sys.path:
    sys.path.insert(0, str(TRAIN_EC57_DIR))

from ludb_io import load_ludb_record, CANONICAL_LEADS
from evaluate_ludb import select_and_fuse_record
from evaluate_qrs import evaluate_record


def classify_false_positive(
    fp_index: int,
    ref_indices: List[int],
    signals: Dict[str, List[float]],
    fused_indices: List[int]
) -> Tuple[str, str]:
    """Classify a single false positive into standard ECG QRS taxonomy."""
    # 1. Startup Transient: first 250 samples (1.0 s)
    if fp_index < 250:
        return (
            "startup_transient",
            f"Detected at sample {fp_index} (<1.0s) during filter and adaptive threshold settling"
        )

    # 2. Duplicate detection / refractory breach (<300 ms from a true beat)
    min_dist_ref = min(abs(fp_index - r) for r in ref_indices) if ref_indices else 9999
    closest_ref = min(ref_indices, key=lambda r: abs(fp_index - r)) if ref_indices else -1
    
    # 3. Cross-window boundary artifact: within 10 samples of 500, 1000, 1500, 2000
    for bound in (500, 1000, 1500, 2000):
        if abs(fp_index - bound) <= 10:
            return (
                "cross_window_boundary",
                f"Detected at sample {fp_index} near SQI 2-second window boundary {bound}"
            )

    # Check relationship to previous true QRS
    prior_refs = [r for r in ref_indices if r < fp_index]
    if prior_refs:
        last_ref = prior_refs[-1]
        delta_samples = fp_index - last_ref
        delta_ms = delta_samples * 4.0  # 250 Hz -> 4ms/sample

        # 4. T-wave misdetection (typically 120ms - 380ms after true QRS)
        if 30 <= delta_samples <= 95:  # 120ms .. 380ms
            return (
                "t_wave_misdetection",
                f"Occurred {delta_ms:.0f}ms after true R-peak at {last_ref} (typical T-wave window)"
            )

        # 5. Duplicate pulse within 120ms
        if delta_samples < 30:
            return (
                "duplicate_refractory",
                f"Double detection only {delta_ms:.0f}ms after R-peak at {last_ref}"
            )

    # 6. Baseline drift / noise check on Lead II / V1
    lead_ii = signals.get("II", signals.get("I", []))
    if lead_ii and 0 <= fp_index < len(lead_ii):
        win_start = max(0, fp_index - 50)
        win_end = min(len(lead_ii), fp_index + 50)
        segment = lead_ii[win_start:win_end]
        if segment:
            mean_val = sum(segment) / len(segment)
            variance = sum((x - mean_val) ** 2 for x in segment) / len(segment)
            std_dev = math.sqrt(variance)
            if std_dev > 400:  # High variance noise
                return ("emg_noise", f"High noise standard deviation ({std_dev:.1f} LSB) in local window")

    # 7. Default to baseline wander / morphology artifact
    return ("baseline_wander", f"Detected at sample {fp_index} with nearest true beat at {closest_ref} (dist {min_dist_ref*4}ms)")


def run_taxonomy_analysis(data_root: str | Path, output_file: str | Path) -> dict:
    data_root = Path(data_root).resolve()
    from ludb_io import discover_ludb_records
    records = discover_ludb_records(data_root, expected_count=200)

    categories = {
        "startup_transient": [],
        "t_wave_misdetection": [],
        "duplicate_refractory": [],
        "cross_window_boundary": [],
        "emg_noise": [],
        "baseline_wander": []
    }

    total_fp_count = 0
    detailed_fp_rows = []

    for record_id in records:
        loaded = load_ludb_record(data_root, record_id)
        ref_indices = [ref.target_sample_index for ref in loaded.reference_qrs]
        float_res = select_and_fuse_record(loaded.signals_lsb_250, fixed=False)
        detected = float_res.peak_indices

        # Find which detected peaks are False Positives (distance > 150ms / 37.5 samples to all refs)
        TOL_SAMPLES = 37.5
        unmatched_detected = list(detected)
        
        # 1-to-1 matching
        matched_detected = set()
        for ref in ref_indices:
            candidates = [d for d in detected if abs(d - ref) <= TOL_SAMPLES and d not in matched_detected]
            if candidates:
                closest = min(candidates, key=lambda d: abs(d - ref))
                matched_detected.add(closest)

        fps = [d for d in detected if d not in matched_detected]
        for fp in fps:
            cat, desc = classify_false_positive(fp, ref_indices, loaded.signals_lsb_250, detected)
            categories[cat].append({
                "record_id": record_id,
                "sample_index": fp,
                "description": desc
            })
            detailed_fp_rows.append({
                "record_id": record_id,
                "fp_sample_index": fp,
                "category": cat,
                "description": desc
            })
            total_fp_count += 1

    summary = {
        "total_fp_count": total_fp_count,
        "breakdown": {
            cat: {
                "count": len(items),
                "percentage": round(len(items) / total_fp_count * 100.0, 2) if total_fp_count else 0
            }
            for cat, items in categories.items()
        }
    }

    # Save detailed CSV
    output_path = Path(output_file).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["record_id", "fp_sample_index", "category", "description"])
        writer.writeheader()
        writer.writerows(detailed_fp_rows)

    json_path = output_path.with_suffix(".json")
    json_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    return summary


if __name__ == "__main__":
    summary = run_taxonomy_analysis("data/ludb/1.0.1", "docs/reports/20260829-0940-m1a-fixed-reference-repair/false_positive_taxonomy.csv")
    print(json.dumps(summary, indent=2))
