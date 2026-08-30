import os
import sys
import json
import argparse

# Ensure project root is in sys.path
_cur_dir = os.path.dirname(os.path.abspath(__file__))
_proj_root = os.path.abspath(os.path.join(_cur_dir, "..", ".."))
if _proj_root not in sys.path:
    sys.path.insert(0, _proj_root)

import numpy as np
import torch

from train.ec57.train_nv import train_single_run


def main():
    parser = argparse.ArgumentParser(description="Train TinyECGCNN_NV candidate on remote GPU")
    parser.add_argument("--config", type=str, required=True, help="Path to candidate config json")
    parser.add_argument("--cache-dir", type=str, default=r"C:\Users\Administrator\Desktop\LRX\ecg_ti_pipeline_3\cache_ec57_beats_v1", help="Path to beat cache directory")
    parser.add_argument("--output-dir", type=str, required=True, help="Run output directory")
    parser.add_argument("--seed", type=int, default=17, help="Random seed (17, 29, 43)")
    parser.add_argument("--device", type=str, default="cuda:0", help="Torch device string")
    args = parser.parse_args()

    with open(args.config, "r", encoding="utf-8") as f:
        config = json.load(f)

    print("==================================================")
    print(f"Candidate: {config.get('candidate_name')}")
    print(f"Seed:      {args.seed}")
    print(f"Device:    {args.device}")
    print(f"Output:    {args.output_dir}")
    print("==================================================")

    # 1. Load beat datasets
    train_npz = os.path.join(args.cache_dir, "train_beats.npz")
    val_npz = os.path.join(args.cache_dir, "val_beats.npz")

    if not os.path.exists(train_npz) or not os.path.exists(val_npz):
        raise FileNotFoundError(f"Beat cache not found at {args.cache_dir}. Run prepare_beat_cache.py first!")

    print(f"Loading {train_npz} and {val_npz}...")
    train_raw = np.load(train_npz)
    val_raw = np.load(val_npz)

    train_data = {
        "waveforms": train_raw["waveforms"],
        "features": train_raw["features"],
        "labels": train_raw["labels"],
        "patient_ids": train_raw["patient_ids"]
    }

    # Split val_raw into validation (50% patients) and internal_test (50% patients)
    val_pids = np.unique(val_raw["patient_ids"])
    rng = np.random.RandomState(42)
    shuffled_pids = rng.permutation(val_pids)
    split_pt = len(shuffled_pids) // 2
    val_set_pids = set(shuffled_pids[:split_pt])
    test_set_pids = set(shuffled_pids[split_pt:])

    val_mask = np.array([pid in val_set_pids for pid in val_raw["patient_ids"]])
    test_mask = np.array([pid in test_set_pids for pid in val_raw["patient_ids"]])

    val_data = {
        "waveforms": val_raw["waveforms"][val_mask],
        "features": val_raw["features"][val_mask],
        "labels": val_raw["labels"][val_mask],
        "patient_ids": val_raw["patient_ids"][val_mask]
    }
    test_data = {
        "waveforms": val_raw["waveforms"][test_mask],
        "features": val_raw["features"][test_mask],
        "labels": val_raw["labels"][test_mask],
        "patient_ids": val_raw["patient_ids"][test_mask]
    }

    print(f"Train samples: {len(train_data['labels'])} (VEB: {np.sum(train_data['labels']==1)})")
    print(f"Val samples:   {len(val_data['labels'])} (VEB: {np.sum(val_data['labels']==1)})")
    print(f"Test samples:  {len(test_data['labels'])} (VEB: {np.sum(test_data['labels']==1)})")

    # 2. Run training
    results = train_single_run(
        config=config,
        train_data=train_data,
        val_data=val_data,
        test_data=test_data,
        output_dir=args.output_dir,
        seed=args.seed,
        device_str=args.device
    )

    print("==================================================")
    print("Training finished successfully!")
    print(f"Optimal Threshold: {results['optimal_threshold']}")
    rates = results["test_metrics"]["gross_rates"]
    print(f"Test VEB Se:   {rates['veb_se_percent']:.3f}%" if rates['veb_se_percent'] is not None else "N/A")
    print(f"Test VEB +P:   {rates['veb_plus_p_percent']:.3f}%" if rates['veb_plus_p_percent'] is not None else "N/A")
    print(f"Test VEB FPR:  {rates['veb_fpr_percent']:.3f}%" if rates['veb_fpr_percent'] is not None else "N/A")
    print(f"Model SHA-256: {results['model_sha256']}")
    print("==================================================")


if __name__ == "__main__":
    main()
