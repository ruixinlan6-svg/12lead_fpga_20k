"""Prepares 160-sample beat windows and 4 scalar features from 15-second 250 Hz public training cache.

Processes:
  1. Runs QRS detector on each 15-second segment (3,750 samples @ 250 Hz).
  2. Extracts 160-point beat windows [R - 64, R + 96) around each R peak.
  3. Computes 4 scalar auxiliary features:
       f1: RR_pre / RR_med8
       f2: QRS width in samples
       f3: Amp_peak / Amp_med8
       f4: Lead SQI score
  4. Saves normalized train_beats.npz and val_beats.npz with patient/record isolation.
"""

import os
import sys
import json
import time

# Ensure project root is in sys.path
_cur_dir = os.path.dirname(os.path.abspath(__file__))
_proj_root = os.path.abspath(os.path.join(_cur_dir, "..", ".."))
if _proj_root not in sys.path:
    sys.path.insert(0, _proj_root)

import numpy as np
from typing import Dict, List, Tuple, Any

from train.ec57.qrs_detector import CausalPureIntegerQRSDetector
from train.ec57.beat_dataset import (
    extract_beat_window,
    normalize_waveform_int8,
    normalize_scalar_features_int8
)
from train.ec57.sqi import evaluate_sqi_fixed


def process_segment(
    raw_sig_float: np.ndarray,
    seg_label: int,
    record_id: str,
    scale_ref: float = 500.0
) -> List[Dict[str, Any]]:
    """Processes a single 15-second signal segment into individual beat samples."""
    # Convert signal to integer LSB (1 LSB = 5 uV)
    sig_lsb = np.round(raw_sig_float).astype(np.int32)
    sig_len = len(sig_lsb)

    # 1. Run QRS detector
    detector = CausalPureIntegerQRSDetector(sample_rate_hz=250)
    for s in sig_lsb:
        detector.step(int(s))

    detected_peaks = detector.accepted_peaks
    if not detected_peaks:
        # Fallback: find peak of max amplitude in the central region [500, 3250]
        central_region = np.abs(sig_lsb[500:3250])
        if len(central_region) > 0:
            detected_peaks = [500 + int(np.argmax(central_region))]
        else:
            detected_peaks = [1875]

    # Map segment label to binary VEB label (1: VEB if label in {1, 3}, 0: non_VEB if label in {0, 2})
    is_veb = 1 if seg_label in (1, 3) else 0

    beats = []
    rr_history = []
    amp_history = []

    # SQI of the 15-second segment
    sqi_res = evaluate_sqi_fixed(sig_lsb[:500].tolist(), qrs_candidate_count=len(detected_peaks))
    sqi_val = 1.0 if sqi_res.valid else 0.0

    for i, r_idx in enumerate(detected_peaks):
        if r_idx < 64 or r_idx >= sig_len - 96:
            continue

        # Extract 160-point window
        window_raw = extract_beat_window(sig_lsb, r_index=r_idx)
        window_int8 = normalize_waveform_int8(window_raw, scale_ref=scale_ref)

        # 4 auxiliary features
        # f1: RR_pre / RR_med8
        if i > 0:
            curr_rr = r_idx - detected_peaks[i - 1]
            rr_history.append(curr_rr)
            if len(rr_history) > 8:
                rr_history.pop(0)
            med_rr = float(np.median(rr_history))
            f1_rr_ratio = (curr_rr / med_rr) if med_rr > 0 else 1.0
        else:
            f1_rr_ratio = 1.0

        # f2: QRS width (approximated via energy footprint around R-peak)
        r_local = 64
        qrs_slice = np.abs(window_raw[max(0, r_local - 15):min(160, r_local + 16)])
        threshold_qrs = 0.3 * np.max(qrs_slice) if len(qrs_slice) > 0 else 10.0
        f2_qrs_width = float(np.sum(qrs_slice >= threshold_qrs))

        # f3: Amp_peak / Amp_med8
        peak_amp = float(np.max(np.abs(window_raw)))
        amp_history.append(peak_amp)
        if len(amp_history) > 8:
            amp_history.pop(0)
        med_amp = float(np.median(amp_history))
        f3_amp_ratio = (peak_amp / med_amp) if med_amp > 0 else 1.0

        # f4: Lead SQI score
        f4_sqi = sqi_val

        raw_features = np.array([f1_rr_ratio, f2_qrs_width, f3_amp_ratio, f4_sqi], dtype=np.float32)

        # Beat-level labeling:
        # In a Normal (0) or Brady/Tachy (2) segment, all beats are non-VEB (0).
        # In an Arrhythmia / PVC segment (1 or 3), the ectopic premature/wide beats are VEB (1),
        # while the normal sinus baseline beats within the same segment are non-VEB (0).
        if seg_label in (1, 3):
            # Premature coupling (RR < 0.85) or compensatory/pause (RR > 1.30) or wide complex (width >= 18)
            is_ectopic = (f1_rr_ratio <= 0.85) or (f1_rr_ratio >= 1.35) or (f2_qrs_width >= 18.0) or (f3_amp_ratio >= 1.4)
            beat_label = 1 if is_ectopic else 0
        else:
            beat_label = 0

        beats.append({
            "waveform": window_int8,
            "raw_features": raw_features,
            "label": beat_label,
            "record_id": record_id,
            "r_index": r_idx
        })

    return beats


def build_beat_cache(
    input_cache_dir: str,
    output_dir: str,
    max_train_samples: int = 15000,
    max_val_samples: int = 4000
) -> Dict[str, str]:
    """Extracts beat dataset from raw 15-second segments and saves train_beats.npz and val_beats.npz."""
    os.makedirs(output_dir, exist_ok=True)
    t0 = time.time()

    split_paths = {}

    for split, max_n in [("train", max_train_samples), ("val", max_val_samples)]:
        npz_file = os.path.join(input_cache_dir, f"{split}.npz")
        if not os.path.exists(npz_file):
            raise FileNotFoundError(f"Missing {npz_file}")

        print(f"Loading {npz_file}...")
        raw_data = np.load(npz_file)
        windows = raw_data["windows"]
        labels = raw_data["labels"]
        record_ids = raw_data["record_ids"]

        n_segs = min(len(labels), max_n)
        print(f"Processing {n_segs} segments for {split} split...")

        all_waveforms = []
        all_raw_features = []
        all_labels = []
        all_pids = []

        for idx in range(n_segs):
            if idx % 2000 == 0 and idx > 0:
                print(f"  {split}: {idx}/{n_segs} segments processed ({len(all_labels)} beats extracted)...")

            seg_beats = process_segment(
                raw_sig_float=windows[idx],
                seg_label=int(labels[idx]),
                record_id=str(record_ids[idx])
            )
            for b in seg_beats:
                all_waveforms.append(b["waveform"])
                all_raw_features.append(b["raw_features"])
                all_labels.append(b["label"])
                all_pids.append(b["record_id"])

        all_waveforms = np.array(all_waveforms, dtype=np.int8)
        all_raw_features = np.array(all_raw_features, dtype=np.float32)
        all_labels = np.array(all_labels, dtype=np.int64)
        all_pids = np.array(all_pids)

        print(f"{split} extracted: {len(all_labels)} beats. VEB count: {np.sum(all_labels == 1)}, non-VEB count: {np.sum(all_labels == 0)}")

        # Normalize features on train split statistics
        if split == "train":
            feature_medians = np.median(all_raw_features, axis=0)
            q75, q25 = np.percentile(all_raw_features, [75, 25], axis=0)
            feature_iqrs = np.maximum(q75 - q25, 1e-3)
            # Save normalization json
            norm_dict = {
                "waveform_scale_ref": 500.0,
                "feature_medians": feature_medians.tolist(),
                "feature_iqrs": feature_iqrs.tolist()
            }
            with open(os.path.join(output_dir, "normalization.json"), "w", encoding="utf-8") as f:
                json.dump(norm_dict, f, indent=2)

        # Normalize scalar features to int8
        norm_features = np.array([
            normalize_scalar_features_int8(f, feature_medians, feature_iqrs)
            for f in all_raw_features
        ], dtype=np.int8)

        out_path = os.path.join(output_dir, f"{split}_beats.npz")
        np.savez_compressed(
            out_path,
            waveforms=all_waveforms,
            features=norm_features,
            labels=all_labels,
            patient_ids=all_pids
        )
        split_paths[split] = out_path
        print(f"Saved {out_path} ({os.path.getsize(out_path) / 1024 / 1024:.2f} MB)")

    print(f"Beat cache creation completed in {time.time() - t0:.1f}s")
    return split_paths


if __name__ == "__main__":
    input_dir = r"C:\Users\Administrator\Desktop\LRX\ecg_ti_pipeline_3\cache_public_only_wfdb_v7_dev_15s_250hz"
    output_dir = r"C:\Users\Administrator\Desktop\LRX\ecg_ti_pipeline_3\cache_ec57_beats_v1"
    build_beat_cache(input_dir, output_dir, max_train_samples=20000, max_val_samples=5000)
