"""Training and threshold calibration script for TinyECGCNN_NV (Non-VEB vs VEB).

Implements Section 6 (M2):
  1. Loads candidate configuration (A, B, or C).
  2. Applies data augmentations (gain, baseline wander, Gaussian noise).
  3. Trains with AdamW, weighted Cross-Entropy, and validation VEB F1 early stopping.
  4. Scans decision threshold [0.001, 0.999] on validation split (gate: +P >= 95%, FPR <= 0.25%, max Se).
  5. Evaluates on test split with full Wilson CI and patient-level metrics.
  6. Exports model_fp32.pt, config.json, normalization.json, decision_threshold.json, metrics.json, and SHA-256 manifests.
"""

import os
import sys
import json
import math
import hashlib
import argparse
import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader
from typing import Dict, List, Tuple, Optional, Any

from train.ec57.model_nv import TinyECGCNN_NV, count_parameters, count_macs
from train.ec57.metrics import (
    VEBConfusionCounts,
    compute_patient_level_metrics,
    wilson_score_interval,
    patient_bootstrap_ci
)


def compute_sha256(filepath: str) -> str:
    """Computes SHA-256 hash of a file."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


class BeatDataset(Dataset):
    """In-memory or array-backed beat dataset with augmentation support."""

    def __init__(
        self,
        waveforms: np.ndarray,       # [N, 160] float32 or int8
        features: np.ndarray,        # [N, 4] float32 or int8
        labels: np.ndarray,          # [N] int64 (0: non_VEB, 1: VEB)
        patient_ids: np.ndarray,     # [N] str or int
        use_features: bool = True,
        augmentation_cfg: Optional[Dict[str, Any]] = None,
        is_training: bool = False
    ):
        self.waveforms = np.asarray(waveforms, dtype=np.float32)
        self.features = np.asarray(features, dtype=np.float32) if use_features else np.zeros_like(features, dtype=np.float32)
        self.labels = np.asarray(labels, dtype=np.int64)
        self.patient_ids = np.asarray(patient_ids)
        self.use_features = use_features
        self.aug_cfg = augmentation_cfg or {}
        self.is_training = is_training

    def __len__(self) -> int:
        return len(self.labels)

    def __getitem__(self, idx: int) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor, str]:
        wave = self.waveforms[idx].copy()
        feat = self.features[idx].copy()
        label = self.labels[idx]
        pat_id = str(self.patient_ids[idx])

        if self.is_training and self.aug_cfg:
            # 1. Gain augmentation (0.8 - 1.2)
            gain_range = self.aug_cfg.get("gain_range", [0.8, 1.2])
            gain = np.random.uniform(gain_range[0], gain_range[1])
            wave = wave * gain

            # 2. Baseline wander (0.05 - 0.5 Hz)
            bw_cfg = self.aug_cfg.get("baseline_wander")
            if isinstance(bw_cfg, dict) and bw_cfg.get("enabled", False):
                f_min, f_max = bw_cfg.get("freq_hz_range", [0.05, 0.5])
                max_uv = bw_cfg.get("max_peak_uv", 100.0)
                # 5 uV per LSB -> 20 LSB max
                max_lsb = max_uv / 5.0
                freq = np.random.uniform(f_min, f_max)
                phase = np.random.uniform(0, 2 * np.pi)
                t = np.arange(160, dtype=np.float32) / 250.0
                amp = np.random.uniform(0, max_lsb)
                wander = amp * np.sin(2 * np.pi * freq * t + phase)
                wave = wave + wander

            # 3. Gaussian noise (12 - 30 dB SNR)
            gn_cfg = self.aug_cfg.get("gaussian_noise")
            if isinstance(gn_cfg, dict) and gn_cfg.get("enabled", False):
                snr_min, snr_max = gn_cfg.get("snr_db_range", [12.0, 30.0])
                snr_db = np.random.uniform(snr_min, snr_max)
                sig_pwr = np.mean(wave ** 2) + 1e-8
                noise_pwr = sig_pwr / (10.0 ** (snr_db / 10.0))
                noise = np.random.normal(0, np.sqrt(noise_pwr), size=160).astype(np.float32)
                wave = wave + noise

        # Unsqueeze waveform to [1, 160]
        x_wave = torch.from_numpy(wave).unsqueeze(0).float()
        x_feat = torch.from_numpy(feat).float()
        y = torch.tensor(label, dtype=torch.long)

        return x_wave, x_feat, y, pat_id


def evaluate_model_at_threshold(
    model: nn.Module,
    dataloader: DataLoader,
    threshold: float,
    device: torch.device
) -> Tuple[Dict[str, VEBConfusionCounts], float, float]:
    """
    Evaluates model across dataloader at a given VEB probability threshold.
    Returns (patient_confusion_map, overall_veb_f1, total_loss).
    """
    model.eval()
    criterion = nn.CrossEntropyLoss()
    patient_counts: Dict[str, VEBConfusionCounts] = {}
    total_loss = 0.0
    total_samples = 0

    all_preds: List[int] = []
    all_targets: List[int] = []

    with torch.no_grad():
        for x_wave, x_feat, y, pat_ids in dataloader:
            x_wave = x_wave.to(device)
            x_feat = x_feat.to(device)
            y = y.to(device)

            logits = model(x_wave, x_feat)
            loss = criterion(logits, y)
            total_loss += loss.item() * len(y)
            total_samples += len(y)

            probs = torch.softmax(logits, dim=1)[:, 1].cpu().numpy()
            targets = y.cpu().numpy()
            preds = (probs >= threshold).astype(np.int64)

            for p, t, pid in zip(preds, targets, pat_ids):
                if pid not in patient_counts:
                    patient_counts[pid] = VEBConfusionCounts()
                c = patient_counts[pid]
                if t == 1:
                    if p == 1:
                        c.vtp += 1
                    else:
                        c.vfn += 1
                else:
                    if p == 1:
                        c.vfp += 1
                    else:
                        c.vtn += 1

            all_preds.extend(preds.tolist())
            all_targets.extend(targets.tolist())

    # Overall Gross F1 score for VEB
    gross_vtp = sum(c.vtp for c in patient_counts.values())
    gross_vfn = sum(c.vfn for c in patient_counts.values())
    gross_vfp = sum(c.vfp for c in patient_counts.values())

    precision = (gross_vtp / (gross_vtp + gross_vfp)) if (gross_vtp + gross_vfp) > 0 else 0.0
    recall = (gross_vtp / (gross_vtp + gross_vfn)) if (gross_vtp + gross_vfn) > 0 else 0.0
    f1 = (2.0 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0

    avg_loss = total_loss / max(1, total_samples)
    return patient_counts, f1, avg_loss


def scan_optimal_threshold(
    model: nn.Module,
    val_loader: DataLoader,
    device: torch.device,
    scan_range: Tuple[float, float] = (0.001, 0.999),
    scan_step: float = 0.001,
    min_veb_plus_p: float = 0.95,
    max_veb_fpr: float = 0.0025
) -> Tuple[float, Dict[str, Any]]:
    """
    Scans decision threshold on validation set according to Section 6.2 priority:
      1. Filter thresholds with VEB +P >= 95.0% and VEB FPR <= 0.25%.
      2. Maximize VEB Se.
      3. If tie, maximize VEB +P.
      4. If tie, pick threshold closest to 0.5.
    """
    model.eval()
    all_probs: List[float] = []
    all_targets: List[int] = []
    all_pids: List[str] = []

    with torch.no_grad():
        for x_wave, x_feat, y, pat_ids in val_loader:
            x_wave = x_wave.to(device)
            x_feat = x_feat.to(device)
            logits = model(x_wave, x_feat)
            probs = torch.softmax(logits, dim=1)[:, 1].cpu().numpy()
            all_probs.extend(probs.tolist())
            all_targets.extend(y.numpy().tolist())
            all_pids.extend(pat_ids)

    probs_arr = np.array(all_probs)
    targets_arr = np.array(all_targets)

    thresholds = np.arange(scan_range[0], scan_range[1] + scan_step / 2.0, scan_step)
    candidate_thresholds = []

    for th in thresholds:
        preds = (probs_arr >= th).astype(np.int64)
        vtp = int(np.sum((targets_arr == 1) & (preds == 1)))
        vfn = int(np.sum((targets_arr == 1) & (preds == 0)))
        vfp = int(np.sum((targets_arr == 0) & (preds == 1)))
        vtn = int(np.sum((targets_arr == 0) & (preds == 0)))

        se = (vtp / (vtp + vfn) * 100.0) if (vtp + vfn) > 0 else 0.0
        plus_p = (vtp / (vtp + vfp) * 100.0) if (vtp + vfp) > 0 else 0.0
        fpr = (vfp / (vtn + vfp) * 100.0) if (vtn + vfp) > 0 else 0.0

        meets_gate = (plus_p >= min_veb_plus_p * 100.0) and (fpr <= max_veb_fpr * 100.0)

        candidate_thresholds.append({
            "threshold": float(round(th, 4)),
            "vtp": vtp,
            "vfn": vfn,
            "vfp": vfp,
            "vtn": vtn,
            "se_percent": se,
            "plus_p_percent": plus_p,
            "fpr_percent": fpr,
            "meets_gate": meets_gate
        })

    # Filter matching candidates
    valid_candidates = [c for c in candidate_thresholds if c["meets_gate"]]

    if valid_candidates:
        # Sort by: -se_percent, -plus_p_percent, abs(threshold - 0.5)
        valid_candidates.sort(key=lambda c: (-c["se_percent"], -c["plus_p_percent"], abs(c["threshold"] - 0.5)))
        best = valid_candidates[0]
        chosen_th = best["threshold"]
    else:
        # Fallback: maximize F1
        candidate_thresholds.sort(key=lambda c: (
            -((2 * c["se_percent"] * c["plus_p_percent"]) / max(c["se_percent"] + c["plus_p_percent"], 1e-8)),
            abs(c["threshold"] - 0.5)
        ))
        best = candidate_thresholds[0]
        chosen_th = best["threshold"]

    summary = {
        "selected_threshold": chosen_th,
        "selected_metrics": best,
        "valid_threshold_count": len(valid_candidates),
        "total_thresholds_scanned": len(candidate_thresholds),
        "scan_step": scan_step
    }
    return chosen_th, summary


def train_single_run(
    config: Dict[str, Any],
    train_data: Dict[str, np.ndarray],
    val_data: Dict[str, np.ndarray],
    test_data: Dict[str, np.ndarray],
    output_dir: str,
    seed: int = 17,
    device_str: str = "cuda"
) -> Dict[str, Any]:
    """Executes a single end-to-end training and evaluation run with seed."""
    os.makedirs(output_dir, exist_ok=True)

    # Set seeds
    torch.manual_seed(seed)
    np.random.seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)

    device = torch.device(device_str if (torch.cuda.is_available() and "cuda" in device_str) else "cpu")

    use_features = config["model"]["use_features"]
    aug_cfg = config.get("augmentation", {})

    train_ds = BeatDataset(
        waveforms=train_data["waveforms"],
        features=train_data["features"],
        labels=train_data["labels"],
        patient_ids=train_data["patient_ids"],
        use_features=use_features,
        augmentation_cfg=aug_cfg,
        is_training=True
    )
    val_ds = BeatDataset(
        waveforms=val_data["waveforms"],
        features=val_data["features"],
        labels=val_data["labels"],
        patient_ids=val_data["patient_ids"],
        use_features=use_features,
        is_training=False
    )
    test_ds = BeatDataset(
        waveforms=test_data["waveforms"],
        features=test_data["features"],
        labels=test_data["labels"],
        patient_ids=test_data["patient_ids"],
        use_features=use_features,
        is_training=False
    )

    batch_size = config["training"]["batch_size"]
    train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True, drop_last=False)
    val_loader = DataLoader(val_ds, batch_size=batch_size, shuffle=False)
    test_loader = DataLoader(test_ds, batch_size=batch_size, shuffle=False)

    model = TinyECGCNN_NV().to(device)

    # Optimizer and Loss
    lr = config["training"]["lr"]
    wd = config["training"]["weight_decay"]
    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=wd)

    veb_weight = config["training"].get("veb_class_weight", 2.5)
    class_weights = torch.tensor([1.0, float(veb_weight)], dtype=torch.float32).to(device)
    criterion = nn.CrossEntropyLoss(weight=class_weights)

    max_epochs = config["training"]["max_epochs"]
    patience = config["training"]["early_stopping_patience"]

    use_scheduler = config["training"].get("scheduler") == "cosine"
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=max_epochs, eta_min=1e-5) if use_scheduler else None

    best_val_f1 = -1.0
    best_epoch = -1
    best_model_state = None
    epochs_no_improve = 0

    history = []

    for epoch in range(1, max_epochs + 1):
        model.train()
        train_loss = 0.0
        train_samples = 0

        for x_wave, x_feat, y, _ in train_loader:
            x_wave = x_wave.to(device)
            x_feat = x_feat.to(device)
            y = y.to(device)

            optimizer.zero_grad()
            logits = model(x_wave, x_feat)
            loss = criterion(logits, y)
            loss.backward()
            optimizer.step()

            train_loss += loss.item() * len(y)
            train_samples += len(y)

        if scheduler is not None:
            scheduler.step()

        avg_train_loss = train_loss / max(1, train_samples)

        # Validation evaluation at default 0.5 threshold
        _, val_f1, avg_val_loss = evaluate_model_at_threshold(model, val_loader, threshold=0.5, device=device)

        history.append({
            "epoch": epoch,
            "train_loss": avg_train_loss,
            "val_loss": avg_val_loss,
            "val_veb_f1": val_f1
        })

        if val_f1 > best_val_f1 + 1e-4:
            best_val_f1 = val_f1
            best_epoch = epoch
            best_model_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}
            epochs_no_improve = 0
        else:
            epochs_no_improve += 1
            if epochs_no_improve >= patience:
                break

    # Restore best checkpoint
    if best_model_state is not None:
        model.load_state_dict(best_model_state)

    # Optimal threshold scanning on validation set
    th_cfg = config.get("threshold_search", {})
    min_plus_p = th_cfg.get("min_veb_plus_p", 0.95)
    max_fpr = th_cfg.get("max_veb_fpr", 0.0025)
    optimal_th, th_summary = scan_optimal_threshold(
        model, val_loader, device=device,
        min_veb_plus_p=min_plus_p, max_veb_fpr=max_fpr
    )

    # Final evaluation on test set at optimal threshold
    test_patient_counts, test_f1, test_loss = evaluate_model_at_threshold(
        model, test_loader, threshold=optimal_th, device=device
    )
    test_metrics = compute_patient_level_metrics(test_patient_counts)
    bootstrap_ci = patient_bootstrap_ci(test_patient_counts, n_resamples=10000, seed=20260827)
    test_metrics["patient_bootstrap_ci_10k"] = bootstrap_ci
    test_metrics["test_loss"] = test_loss
    test_metrics["test_veb_f1"] = test_f1

    # Save artifacts
    model_path = os.path.join(output_dir, "model_fp32.pt")
    torch.save(model.state_dict(), model_path)

    config_out_path = os.path.join(output_dir, "config.json")
    with open(config_out_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)

    threshold_out_path = os.path.join(output_dir, "decision_threshold.json")
    with open(threshold_out_path, "w", encoding="utf-8") as f:
        json.dump(th_summary, f, indent=2)

    metrics_out_path = os.path.join(output_dir, "metrics.json")
    with open(metrics_out_path, "w", encoding="utf-8") as f:
        json.dump({
            "seed": seed,
            "best_epoch": best_epoch,
            "total_epochs": len(history),
            "best_val_veb_f1": best_val_f1,
            "optimal_threshold": optimal_th,
            "test_metrics": test_metrics,
            "history": history,
            "parameter_count": count_parameters(model),
            "macs_per_beat": count_macs(model)
        }, f, indent=2)

    # Compute hashes
    model_hash = compute_sha256(model_path)
    with open(os.path.join(output_dir, "model_sha256.txt"), "w", encoding="utf-8") as f:
        f.write(f"{model_hash}  model_fp32.pt\n")

    manifest_lines = []
    for fname in ["config.json", "decision_threshold.json", "metrics.json", "model_fp32.pt", "model_sha256.txt"]:
        fpath = os.path.join(output_dir, fname)
        if os.path.exists(fpath):
            manifest_lines.append(f"{compute_sha256(fpath)}  {fname}\n")
    with open(os.path.join(output_dir, "manifest_sha256.txt"), "w", encoding="utf-8") as f:
        f.writelines(manifest_lines)

    return {
        "seed": seed,
        "optimal_threshold": optimal_th,
        "test_metrics": test_metrics,
        "model_sha256": model_hash
    }
