import os
import sys
import json
import time
import numpy as np
import pandas as pd
import wfdb
from scipy.signal import resample_poly

# Add base dir
base_dir = r"C:\Users\Administrator\Desktop\LRX\ecg_ti_pipeline_3"
if base_dir not in sys.path:
    sys.path.insert(0, base_dir)

from train.ec57.qrs_detector import CausalPureIntegerQRSDetector
from train.ec57.beat_dataset import (
    extract_beat_window,
    normalize_waveform_int8,
    normalize_scalar_features_int8
)
from train.ec57.sqi import evaluate_sqi_fixed

def build_ptbxl_beats(ptbxl_root, output_dir):
    os.makedirs(output_dir, exist_ok=True)
    df_path = os.path.join(ptbxl_root, "ptbxl_database.csv")
    df = pd.read_csv(df_path)
    print(f"Total PTB-XL records: {len(df)}")

    # Filter into clear categories:
    # 1. PVC records (contains 'PVC')
    # 2. PAC records (contains 'PAC')
    # 3. Normal records (contains 'NORM')
    pvc_mask = df['scp_codes'].str.contains('PVC', na=False)
    pac_mask = df['scp_codes'].str.contains('PAC', na=False)
    norm_mask = df['scp_codes'].str.contains('NORM', na=False) & ~pvc_mask & ~pac_mask

    print(f"PVC records: {pvc_mask.sum()}")
    print(f"PAC records: {pac_mask.sum()}")
    print(f"NORM records: {norm_mask.sum()}")

    # Select subsets for training/val/test
    selected_df = df[pvc_mask | pac_mask | norm_mask].copy()
    print(f"Selected records: {len(selected_df)}")

    # Map folds: 1-8 train, 9 val, 10 test
    splits = {
        "train": selected_df[selected_df['strat_fold'] <= 8],
        "val": selected_df[selected_df['strat_fold'] == 9],
        "test": selected_df[selected_df['strat_fold'] == 10]
    }

    t0 = time.time()
    for split_name, split_df in splits.items():
        print(f"\nProcessing {split_name} split ({len(split_df)} records)...")
        all_waveforms = []
        all_raw_features = []
        all_labels = []
        all_pids = []

        count = 0
        for _, row in split_df.iterrows():
            count += 1
            if count % 1000 == 0:
                print(f"  {split_name}: {count}/{len(split_df)} records ({len(all_labels)} beats)...")

            rec_path = os.path.join(ptbxl_root, row['filename_lr'])
            try:
                # Read Lead II (index 1 in standard 12-lead)
                record = wfdb.rdrecord(rec_path, channels=[1])
                sig_100 = record.p_signal[:, 0]  # in mV
            except Exception:
                continue

            # Resample from 100 Hz to 250 Hz (ratio 5/2)
            sig_250_mv = resample_poly(sig_100, 5, 2)
            # Convert to integer LSB (1 LSB = 5 uV -> 1 mV = 200 LSB)
            sig_lsb = np.round(sig_250_mv * 200.0).astype(np.int32)
            sig_len = len(sig_lsb)

            # QRS detection
            detector = CausalPureIntegerQRSDetector(sample_rate_hz=250)
            for s in sig_lsb:
                detector.step(int(s))
            peaks = detector.accepted_peaks
            if not peaks:
                continue

            is_pvc_rec = 'PVC' in str(row['scp_codes'])
            rr_hist = []
            amp_hist = []

            # SQI
            sqi_res = evaluate_sqi_fixed(sig_lsb[:500].tolist(), qrs_candidate_count=len(peaks))
            sqi_val = 1.0 if sqi_res.valid else 0.0

            for i, r_idx in enumerate(peaks):
                if r_idx < 64 or r_idx >= sig_len - 96:
                    continue

                window_raw = extract_beat_window(sig_lsb, r_index=r_idx)
                window_int8 = normalize_waveform_int8(window_raw, scale_ref=500.0)

                # Feature 1: RR_pre / RR_med8 (Prematurity)
                if i > 0:
                    curr_rr = r_idx - peaks[i - 1]
                    rr_hist.append(curr_rr)
                    if len(rr_hist) > 8:
                        rr_hist.pop(0)
                    med_rr = float(np.median(rr_hist))
                    f1_rr_pre = (curr_rr / med_rr) if med_rr > 0 else 1.0
                else:
                    f1_rr_pre = 1.0

                # Feature 2: RR_post / RR_med8 (Compensatory Pause)
                if i + 1 < len(peaks):
                    post_rr = peaks[i + 1] - r_idx
                    med_rr = float(np.median(rr_hist)) if len(rr_hist) > 0 else float(post_rr)
                    f2_rr_post = (post_rr / med_rr) if med_rr > 0 else 1.0
                else:
                    f2_rr_post = 1.0

                # Feature 3: QRS width in samples
                r_local = 64
                qrs_slice = np.abs(window_raw[max(0, r_local - 15):min(160, r_local + 16)])
                th_qrs = 0.3 * np.max(qrs_slice) if len(qrs_slice) > 0 else 10.0
                f3_qrs_width = float(np.sum(qrs_slice >= th_qrs))

                # Feature 4: Amp ratio (Amp_peak / Amp_med8)
                peak_amp = float(np.max(np.abs(window_raw)))
                amp_hist.append(peak_amp)
                if len(amp_hist) > 8:
                    amp_hist.pop(0)
                med_amp = float(np.median(amp_hist))
                f4_amp_ratio = (peak_amp / med_amp) if med_amp > 0 else 1.0

                raw_feats = np.array([f1_rr_pre, f2_rr_post, f3_qrs_width, f4_amp_ratio], dtype=np.float32)

                # Beat label:
                if is_pvc_rec:
                    # In a PVC record, the premature/aberrant beat with compensatory pause or wide QRS is VEB
                    is_veb = (f1_rr_pre <= 0.85 and f2_rr_post >= 1.05) or (f3_qrs_width >= 24.0 and f4_amp_ratio >= 1.3)
                    beat_label = 1 if is_veb else 0
                else:
                    beat_label = 0

                all_waveforms.append(window_int8)
                all_raw_features.append(raw_feats)
                all_labels.append(beat_label)
                all_pids.append(row['patient_id'])

        all_waveforms = np.array(all_waveforms, dtype=np.int8)
        all_raw_features = np.array(all_raw_features, dtype=np.float32)
        all_labels = np.array(all_labels, dtype=np.int64)
        all_pids = np.array(all_pids)

        print(f"{split_name} total beats: {len(all_labels)} (VEB: {np.sum(all_labels == 1)}, non-VEB: {np.sum(all_labels == 0)})")

        if split_name == "train":
            feature_medians = np.median(all_raw_features, axis=0)
            q75, q25 = np.percentile(all_raw_features, [75, 25], axis=0)
            feature_iqrs = np.maximum(q75 - q25, 1e-3)
            norm_dict = {
                "waveform_scale_ref": 500.0,
                "feature_medians": feature_medians.tolist(),
                "feature_iqrs": feature_iqrs.tolist()
            }
            with open(os.path.join(output_dir, "normalization.json"), "w", encoding="utf-8") as f:
                json.dump(norm_dict, f, indent=2)

        norm_features = np.array([
            normalize_scalar_features_int8(f, feature_medians, feature_iqrs)
            for f in all_raw_features
        ], dtype=np.int8)

        out_path = os.path.join(output_dir, f"{split_name}_beats.npz")
        np.savez_compressed(
            out_path,
            waveforms=all_waveforms,
            features=norm_features,
            labels=all_labels,
            patient_ids=all_pids
        )
        print(f"Saved {out_path} ({os.path.getsize(out_path) / 1024 / 1024:.2f} MB)")

    print(f"Done in {time.time() - t0:.1f}s")

if __name__ == "__main__":
    ptbxl_root = r"C:\Users\Administrator\Desktop\LRX\12lead_fpga_20k_m1\data\ptb-xl\1.0.3"
    output_dir = r"C:\Users\Administrator\Desktop\LRX\ecg_ti_pipeline_3\cache_ptbxl_beats_v1"
    build_ptbxl_beats(ptbxl_root, output_dir)
