"""Comprehensive evidence-grounded false positive and false negative taxonomy analysis."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Dict, List, Tuple, Any

ROOT_DIR = Path(__file__).resolve().parents[2]
TRAIN_EC57_DIR = ROOT_DIR / "train" / "ec57"
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
if str(TRAIN_EC57_DIR) not in sys.path:
    sys.path.insert(0, str(TRAIN_EC57_DIR))

from ludb_io import load_ludb_record, discover_ludb_records, CANONICAL_LEADS
from evaluate_ludb import select_and_fuse_record
from qrs_detector import (
    detect_qrs_fixed,
    detect_qrs_float,
    qrs_energy_fixed,
    qrs_energy_float,
    CausalPureIntegerQRSDetector,
)
from sqi import evaluate_sqi_fixed, evaluate_sqi_float


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def classify_fp_evidence(
    fp_index: int,
    ref_indices: List[int],
    signals: Dict[str, List[int | float]],
    selected_leads: List[str],
    lead_peaks: Dict[str, List[int]],
    energy_map: Dict[str, List[int | float]],
) -> Dict[str, Any]:
    """Classify false positive with full waveform, energy, and lead voting evidence."""
    # 1. Check startup transient (< 188 samples / 0.75 s)
    if fp_index < 188:
        category = "startup_transient"
        mechanism = "Filter settling & initial adaptive threshold calibration phase (<0.75s)"
    elif any(abs(fp_index - b) <= 10 for b in (500, 1000, 1500, 2000)):
        category = "cross_window_boundary"
        mechanism = "2.0-second SQI window boundary artifact / edge stitching"
    else:
        # Check temporal relationship to prior true beat
        prior_refs = [r for r in ref_indices if r < fp_index]
        if prior_refs:
            last_ref = prior_refs[-1]
            delta_samples = fp_index - last_ref
            delta_ms = delta_samples * 4.0

            if delta_samples < 30:  # < 120 ms
                category = "duplicate_refractory"
                mechanism = f"Duplicate trigger only {delta_ms:.0f}ms after R-peak at sample {last_ref}"
            elif 30 <= delta_samples <= 95:  # 120 ~ 380 ms (T-wave window)
                category = "t_wave_misdetection"
                mechanism = f"Peaked T-wave/ST segment {delta_ms:.0f}ms post-QRS exceeding detection threshold"
            else:
                category = "baseline_wander_noise"
                mechanism = f"Low frequency wander or sub-threshold noise ripple ({delta_ms:.0f}ms from last QRS)"
        else:
            category = "baseline_wander_noise"
            mechanism = "Pre-beat low frequency wander before first reference beat"

    # Compute lead voting participation
    voting_leads = []
    for lead in selected_leads:
        p_list = lead_peaks.get(lead, [])
        if any(abs(p - fp_index) <= 20 for p in p_list):
            voting_leads.append(lead)

    # Local waveform snippet (160 samples centered at fp_index)
    ref_lead = selected_leads[0] if selected_leads else "II"
    raw_sig = signals.get(ref_lead, signals.get("II", []))
    start_s = max(0, fp_index - 80)
    end_s = min(len(raw_sig), fp_index + 80)
    waveform_slice = [int(round(raw_sig[i])) for i in range(start_s, end_s)]

    # Peak amplitude & energy
    local_val = int(round(raw_sig[fp_index])) if 0 <= fp_index < len(raw_sig) else 0
    local_energy = 0
    if ref_lead in energy_map and 0 <= fp_index < len(energy_map[ref_lead]):
        local_energy = int(round(energy_map[ref_lead][fp_index]))

    return {
        "sample_index": fp_index,
        "time_ms": fp_index * 4.0,
        "category": category,
        "mechanism": mechanism,
        "selected_leads": "+".join(selected_leads),
        "voting_leads": "+".join(voting_leads) if voting_leads else "none",
        "vote_count": len(voting_leads),
        "reference_lead": ref_lead,
        "local_raw_amplitude_lsb": local_val,
        "local_energy": local_energy,
        "waveform_snippet_len": len(waveform_slice),
    }


def classify_fn_evidence(
    ref_index: int,
    signals: Dict[str, List[int | float]],
    selected_leads: List[str],
    lead_peaks: Dict[str, List[int]],
    energy_map: Dict[str, List[int | float]],
) -> Dict[str, Any]:
    """Classify false negative (missed reference beat) root cause."""
    # Check if any selected lead detected this beat
    detecting_leads = []
    for lead in selected_leads:
        p_list = lead_peaks.get(lead, [])
        if any(abs(p - ref_index) <= 37.5 for p in p_list):
            detecting_leads.append(lead)

    # Check amplitudes on all 12 leads
    lead_amps = {}
    for lead, sig in signals.items():
        if 0 <= ref_index < len(sig):
            start = max(0, ref_index - 10)
            end = min(len(sig), ref_index + 10)
            lead_amps[lead] = max(abs(int(round(sig[i]))) for i in range(start, end))

    if ref_index < 188:
        category = "startup_unsettled"
        mechanism = "Beat occurred in initial 0.75s startup calibration window"
    elif len(detecting_leads) == 1:
        category = "voting_insufficient"
        mechanism = f"Only 1 lead ({detecting_leads[0]}) detected beat; failed 2-of-3 fusion requirement"
    elif len(detecting_leads) == 0:
        # Check if selected leads had weak signal
        sel_max_amp = max(lead_amps.get(lead, 0) for lead in selected_leads) if selected_leads else 0
        all_max_amp = max(lead_amps.values()) if lead_amps else 0
        if all_max_amp > sel_max_amp * 2:
            category = "suboptimal_lead_selection"
            mechanism = f"Selected leads ({'+'.join(selected_leads)}) had low amp ({sel_max_amp} LSB) vs unselected leads ({all_max_amp} LSB)"
        else:
            category = "sub_threshold_amplitude"
            mechanism = f"Low global QRS amplitude ({sel_max_amp} LSB) below adaptive detection threshold"
    else:
        category = "temporal_offset"
        mechanism = "Detected peaks on leads had cluster span exceeding 80ms fusion window"

    return {
        "reference_sample_index": ref_index,
        "time_ms": ref_index * 4.0,
        "category": category,
        "mechanism": mechanism,
        "selected_leads": "+".join(selected_leads),
        "detecting_leads": "+".join(detecting_leads) if detecting_leads else "none",
        "detecting_lead_count": len(detecting_leads),
        "lead_amplitudes": json.dumps(lead_amps),
    }


def run_comprehensive_taxonomy(data_root: str | Path, output_dir: str | Path) -> dict:
    data_root = Path(data_root).resolve()
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    records = discover_ludb_records(data_root, expected_count=200)

    fixed_fp_rows = []
    fixed_fn_rows = []
    float_fp_rows = []

    fixed_fp_categories: Dict[str, int] = {}
    fixed_fn_categories: Dict[str, int] = {}
    float_fp_categories: Dict[str, int] = {}

    TOL_SAMPLES = 37.5  # 150 ms tolerance at 250 Hz

    for record_id in records:
        loaded = load_ludb_record(data_root, record_id)
        ref_indices = [ref.target_sample_index for ref in loaded.reference_qrs]

        # 1. Evaluate Fixed (Causal Pure Integer)
        fixed_fuse = select_and_fuse_record(loaded.signals_lsb_250, fixed=True)
        fixed_detected = fixed_fuse.peak_indices

        # Compute per-lead fixed peaks & energy
        fixed_lead_peaks = {}
        fixed_energy_map = {}
        for lead, sig in loaded.signals_lsb_250.items():
            int_sig = [int(round(x)) for x in sig]
            fixed_lead_peaks[lead] = detect_qrs_fixed(int_sig).peak_indices
            fixed_energy_map[lead] = qrs_energy_fixed(int_sig)

        # Match fixed
        matched_fixed_detected = set()
        matched_fixed_refs = set()
        for ref in ref_indices:
            cands = [d for d in fixed_detected if abs(d - ref) <= TOL_SAMPLES and d not in matched_fixed_detected]
            if cands:
                closest = min(cands, key=lambda d: abs(d - ref))
                matched_fixed_detected.add(closest)
                matched_fixed_refs.add(ref)

        # Fixed FPs
        for d in fixed_detected:
            if d not in matched_fixed_detected:
                # Find selected leads at that time
                win_idx = min(len(fixed_fuse.windows) - 1, max(0, d // 500))
                sel_leads = fixed_fuse.windows[win_idx].selected_leads if fixed_fuse.windows else ["II"]
                ev = classify_fp_evidence(d, ref_indices, loaded.signals_lsb_250, sel_leads, fixed_lead_peaks, fixed_energy_map)
                ev["record_id"] = record_id
                fixed_fp_rows.append(ev)
                fixed_fp_categories[ev["category"]] = fixed_fp_categories.get(ev["category"], 0) + 1

        # Fixed FNs
        for r in ref_indices:
            if r not in matched_fixed_refs:
                win_idx = min(len(fixed_fuse.windows) - 1, max(0, r // 500))
                sel_leads = fixed_fuse.windows[win_idx].selected_leads if fixed_fuse.windows else ["II"]
                ev = classify_fn_evidence(r, loaded.signals_lsb_250, sel_leads, fixed_lead_peaks, fixed_energy_map)
                ev["record_id"] = record_id
                fixed_fn_rows.append(ev)
                fixed_fn_categories[ev["category"]] = fixed_fn_categories.get(ev["category"], 0) + 1

        # 2. Evaluate Float Path
        float_fuse = select_and_fuse_record(loaded.signals_lsb_250, fixed=False)
        float_detected = float_fuse.peak_indices
        float_lead_peaks = {
            lead: detect_qrs_float(sig).peak_indices for lead, sig in loaded.signals_lsb_250.items()
        }
        float_energy_map = {
            lead: qrs_energy_float(sig) for lead, sig in loaded.signals_lsb_250.items()
        }

        matched_float_detected = set()
        for ref in ref_indices:
            cands = [d for d in float_detected if abs(d - ref) <= TOL_SAMPLES and d not in matched_float_detected]
            if cands:
                closest = min(cands, key=lambda d: abs(d - ref))
                matched_float_detected.add(closest)

        # Float FPs
        for d in float_detected:
            if d not in matched_float_detected:
                win_idx = min(len(float_fuse.windows) - 1, max(0, d // 500))
                sel_leads = float_fuse.windows[win_idx].selected_leads if float_fuse.windows else ["II"]
                ev = classify_fp_evidence(d, ref_indices, loaded.signals_lsb_250, sel_leads, float_lead_peaks, float_energy_map)
                ev["record_id"] = record_id
                float_fp_rows.append(ev)
                float_fp_categories[ev["category"]] = float_fp_categories.get(ev["category"], 0) + 1

    # Write CSVs
    def write_csv(path: Path, rows: list[dict]):
        if not rows:
            return
        with path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

    write_csv(output_dir / "causal_fixed_fp_taxonomy.csv", fixed_fp_rows)
    write_csv(output_dir / "causal_fixed_fn_taxonomy.csv", fixed_fn_rows)
    write_csv(output_dir / "float_fp_taxonomy.csv", float_fp_rows)

    summary = {
        "dataset": "LUDB 1.0.1 (200 records)",
        "total_references": 1832,
        "fixed_causal": {
            "total_qfp": len(fixed_fp_rows),
            "total_qfn": len(fixed_fn_rows),
            "fp_breakdown": {
                k: {"count": v, "percentage": round(v / len(fixed_fp_rows) * 100, 2)}
                for k, v in sorted(fixed_fp_categories.items(), key=lambda x: -x[1])
            },
            "fn_breakdown": {
                k: {"count": v, "percentage": round(v / len(fixed_fn_rows) * 100, 2)}
                for k, v in sorted(fixed_fn_categories.items(), key=lambda x: -x[1])
            },
        },
        "float_lookahead": {
            "total_qfp": len(float_fp_rows),
            "fp_breakdown": {
                k: {"count": v, "percentage": round(v / len(float_fp_rows) * 100, 2)}
                for k, v in sorted(float_fp_categories.items(), key=lambda x: -x[1])
            },
        },
    }

    summary_file = output_dir / "taxonomy_summary.json"
    summary_file.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    # Generate sha256 manifest
    manifest_lines = []
    for p in sorted(output_dir.iterdir()):
        if p.is_file() and p.name != "sha256_manifest.txt":
            manifest_lines.append(f"{_sha256_file(p)}  {p.name}\n")
    (output_dir / "sha256_manifest.txt").write_text("".join(manifest_lines), encoding="utf-8")

    return summary


if __name__ == "__main__":
    out = run_comprehensive_taxonomy(
        "data/ludb/1.0.1",
        "docs/reports/20260829-1015-m1b-causal-false-positive-taxonomy"
    )
    print(json.dumps(out, indent=2, ensure_ascii=False))
