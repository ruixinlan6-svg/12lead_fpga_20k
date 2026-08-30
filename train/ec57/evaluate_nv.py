"""Standalone evaluation script for trained TinyECGCNN_NV models on test split."""

import os
import sys
import json
import argparse
import numpy as np
import torch
from typing import Dict, Any

from train.ec57.model_nv import TinyECGCNN_NV, count_parameters, count_macs
from train.ec57.train_nv import BeatDataset, evaluate_model_at_threshold, compute_sha256
from train.ec57.metrics import compute_patient_level_metrics, patient_bootstrap_ci


def evaluate_checkpoint(
    checkpoint_path: str,
    config_path: str,
    test_data: Dict[str, np.ndarray],
    threshold: float,
    output_dir: str,
    device_str: str = "cpu"
) -> Dict[str, Any]:
    """Evaluates a saved checkpoint on test data at a specific threshold."""
    os.makedirs(output_dir, exist_ok=True)

    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    device = torch.device(device_str if (torch.cuda.is_available() and "cuda" in device_str) else "cpu")

    model = TinyECGCNN_NV().to(device)
    state_dict = torch.load(checkpoint_path, map_location=device)
    model.load_state_dict(state_dict)
    model.eval()

    use_features = config["model"].get("use_features", True)
    test_ds = BeatDataset(
        waveforms=test_data["waveforms"],
        features=test_data["features"],
        labels=test_data["labels"],
        patient_ids=test_data["patient_ids"],
        use_features=use_features,
        is_training=False
    )
    test_loader = torch.utils.data.DataLoader(test_ds, batch_size=1024, shuffle=False)

    patient_counts, f1, loss = evaluate_model_at_threshold(model, test_loader, threshold=threshold, device=device)
    metrics = compute_patient_level_metrics(patient_counts)
    bootstrap_ci = patient_bootstrap_ci(patient_counts, n_resamples=10000, seed=20260827)
    metrics["patient_bootstrap_ci_10k"] = bootstrap_ci
    metrics["test_loss"] = loss
    metrics["test_veb_f1"] = f1
    metrics["evaluated_threshold"] = threshold
    metrics["parameter_count"] = count_parameters(model)
    metrics["macs_per_beat"] = count_macs(model)

    out_json = os.path.join(output_dir, "evaluation_report.json")
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)

    # Manifest
    manifest_path = os.path.join(output_dir, "sha256_manifest.txt")
    with open(manifest_path, "w", encoding="utf-8") as f:
        f.write(f"{compute_sha256(out_json)}  evaluation_report.json\n")

    return metrics


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate TinyECGCNN_NV checkpoint on test data")
    parser.add_argument("--checkpoint", type=str, required=True, help="Path to model_fp32.pt")
    parser.add_argument("--config", type=str, required=True, help="Path to config.json")
    parser.add_argument("--threshold", type=float, default=0.5, help="Decision threshold")
    parser.add_argument("--output-dir", type=str, required=True, help="Output directory")
    args = parser.parse_args()
    print("evaluate_nv CLI ready")
