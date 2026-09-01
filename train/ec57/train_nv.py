"""Training and threshold calibration script for TinyECGCNN_NV (Non-VEB vs VEB).

Implements Section 6 (M2):
  1. Loads candidate configuration (A, B, or C).
  2. Applies data augmentations (gain, baseline wander, Gaussian noise).
  3. Trains with AdamW, weighted Cross-Entropy, and validation VEB F1 early stopping.
  4. Scans decision threshold [0.001, 0.999] on validation split
     (gates: Se >= 90%, +P >= 95%, FPR <= 0.25%; then maximize Se).
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
import torch.nn.functional as F
from torch.utils.data import Dataset, DataLoader, Sampler
from typing import Dict, List, Tuple, Optional, Any, Sequence

from train.ec57.model_nv import (
    TinyECGCNN_NV,
    TinyECGCNN_NV_Depthwise,
    MediumECGCNN_NV,
    DualBranchECGCNN_NV,
    count_parameters,
    count_macs,
    estimate_model_deployment_resources,
)
from train.ec57.resource_budget import frozen_model_resource_limits
from train.ec57.metrics import (
    VEBConfusionCounts,
    compute_patient_level_metrics,
    wilson_score_interval,
    patient_bootstrap_ci
)


def asymmetric_focal_cross_entropy(
    logits: torch.Tensor,
    targets: torch.Tensor,
    *,
    class_weights: torch.Tensor,
    negative_gamma: float,
    reduction: str = "mean",
) -> torch.Tensor:
    """Apply focal modulation only to negative-class weighted CE terms."""
    gamma = float(negative_gamma)
    if not math.isfinite(gamma) or gamma < 0.0:
        raise ValueError("negative_gamma must be a finite non-negative value")
    if reduction not in {"none", "sum", "mean"}:
        raise ValueError("reduction must be none, sum or mean")
    losses = F.cross_entropy(logits, targets, weight=class_weights, reduction="none")
    probabilities = torch.softmax(logits, dim=1)
    target_probabilities = probabilities.gather(1, targets.unsqueeze(1)).squeeze(1)
    negative_mask = targets == 0
    focal_factors = torch.ones_like(losses)
    focal_factors[negative_mask] = (1.0 - target_probabilities[negative_mask]).pow(gamma)
    losses = losses * focal_factors
    if reduction == "none":
        return losses
    if reduction == "sum":
        return losses.sum()
    denominator = class_weights[targets].sum().clamp_min(torch.finfo(losses.dtype).tiny)
    return losses.sum() / denominator


class AsymmetricNegativeFocalCrossEntropyLoss(nn.Module):
    def __init__(self, class_weights: torch.Tensor, negative_gamma: float):
        super().__init__()
        self.register_buffer("class_weights", class_weights.detach().clone())
        self.negative_gamma = float(negative_gamma)

    def forward(self, logits: torch.Tensor, targets: torch.Tensor) -> torch.Tensor:
        return asymmetric_focal_cross_entropy(
            logits,
            targets,
            class_weights=self.class_weights,
            negative_gamma=self.negative_gamma,
        )


class AsymmetricMarginCrossEntropyLoss(nn.Module):
    """Cross-entropy with quadratic margin penalty on false positives."""

    def __init__(
        self,
        class_weights: torch.Tensor,
        fp_margin: float = 0.05,
        fp_penalty_weight: float = 2.0,
    ):
        super().__init__()
        self.register_buffer("class_weights", class_weights.detach().clone())
        self.fp_margin = float(fp_margin)
        self.fp_penalty_weight = float(fp_penalty_weight)

    def forward(self, logits: torch.Tensor, targets: torch.Tensor) -> torch.Tensor:
        ce_loss = F.cross_entropy(logits, targets, weight=self.class_weights, reduction="none")
        probs = F.softmax(logits, dim=1)
        p_veb = probs[:, 1]
        is_neg = targets == 0
        fp_violation = torch.clamp(p_veb - self.fp_margin, min=0.0)
        fp_penalty = self.fp_penalty_weight * (fp_violation ** 2)
        total_loss = ce_loss + torch.where(is_neg, fp_penalty, 0.0)
        return total_loss.mean()


class AsymmetricHardNegativeMiningLoss(nn.Module):
    """Cross-entropy with asymmetric margin penalty plus extra penalty on wide-QRS normal sinus beats."""

    def __init__(
        self,
        class_weights: torch.Tensor,
        fp_margin: float = 0.03,
        fp_penalty_weight: float = 3.0,
        wide_qrs_extra_weight: float = 5.0,
    ):
        super().__init__()
        self.register_buffer("class_weights", class_weights.detach().clone())
        self.fp_margin = float(fp_margin)
        self.fp_penalty_weight = float(fp_penalty_weight)
        self.wide_qrs_extra_weight = float(wide_qrs_extra_weight)

    def forward(self, logits: torch.Tensor, targets: torch.Tensor, features: Optional[torch.Tensor] = None) -> torch.Tensor:
        ce_loss = F.cross_entropy(logits, targets, weight=self.class_weights, reduction="none")
        probs = F.softmax(logits, dim=1)
        p_veb = probs[:, 1]
        is_neg = targets == 0
        fp_violation = torch.clamp(p_veb - self.fp_margin, min=0.0)
        fp_penalty = self.fp_penalty_weight * (fp_violation ** 2)

        if features is not None and features.shape[1] >= 6:
            qrs_width = features[:, 5]
            is_wide_neg = is_neg & (qrs_width > 0.0)
            fp_penalty = fp_penalty + torch.where(is_wide_neg, self.wide_qrs_extra_weight * (fp_violation ** 2), 0.0)

        total_loss = ce_loss + torch.where(is_neg, fp_penalty, 0.0)
        return total_loss.mean()


class CompensatoryConsistencyLoss(nn.Module):
    """Cross-entropy with compensatory consistency penalty on normal sinus rhythms without pause."""

    def __init__(
        self,
        class_weights: torch.Tensor,
        fp_margin: float = 0.02,
        fp_penalty_weight: float = 3.0,
        wide_qrs_extra_weight: float = 5.0,
        comp_neg_weight: float = 8.0,
    ):
        super().__init__()
        self.register_buffer("class_weights", class_weights.detach().clone())
        self.fp_margin = float(fp_margin)
        self.fp_penalty_weight = float(fp_penalty_weight)
        self.wide_qrs_extra_weight = float(wide_qrs_extra_weight)
        self.comp_neg_weight = float(comp_neg_weight)

    def forward(self, logits: torch.Tensor, targets: torch.Tensor, features: Optional[torch.Tensor] = None) -> torch.Tensor:
        ce_loss = F.cross_entropy(logits, targets, weight=self.class_weights, reduction="none")
        probs = F.softmax(logits, dim=1)
        p_veb = probs[:, 1]
        is_neg = targets == 0
        fp_violation = torch.clamp(p_veb - self.fp_margin, min=0.0)
        fp_penalty = self.fp_penalty_weight * (fp_violation ** 2)

        if features is not None and features.shape[1] >= 6:
            qrs_width = features[:, 5]
            comp_ratio = features[:, 2]

            # Wide QRS normal beat penalty (Bundle branch block)
            is_wide_neg = is_neg & (qrs_width > 0.0)
            fp_penalty = fp_penalty + torch.where(is_wide_neg, self.wide_qrs_extra_weight * (fp_violation ** 2), 0.0)

            # Low compensatory pause normal beat penalty (Sinus rhythm with regular pause)
            is_low_comp_neg = is_neg & (comp_ratio <= 0.0)
            fp_penalty = fp_penalty + torch.where(is_low_comp_neg, self.comp_neg_weight * (fp_violation ** 2), 0.0)

        total_loss = ce_loss + torch.where(is_neg, fp_penalty, 0.0)
        return total_loss.mean()


class ThresholdGateError(ValueError):
    """A fail-closed threshold rejection with auditable validation diagnostics."""

    def __init__(self, summary: Dict[str, Any]):
        super().__init__(
            "no validation threshold meets the frozen VEB Se, +P, and FPR gates; "
            "candidate must be rejected without internal-test evaluation"
        )
        self.summary = summary


class ModelResourceBudgetError(ValueError):
    """A fail-closed rejection before training an undeployable model."""

    def __init__(self, resources: Dict[str, int], violations: List[str]):
        super().__init__(
            "deployment resource budget exceeded: " + "; ".join(violations)
        )
        self.resources = resources
        self.violations = violations


def compute_sha256(filepath: str) -> str:
    """Computes SHA-256 hash of a file."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def build_epoch_sample_indices(
    labels: np.ndarray,
    patient_ids: np.ndarray,
    *,
    max_beats_per_patient: int,
    max_negative_per_positive: int,
    seed: int,
    epoch: int,
) -> np.ndarray:
    """Create one deterministic patient-capped, class-capped epoch index list."""
    labels = np.asarray(labels, dtype=np.int64)
    patient_ids = np.asarray(patient_ids).astype(str)
    if labels.ndim != 1 or patient_ids.shape != labels.shape:
        raise ValueError("labels and patient_ids must be aligned one-dimensional arrays")
    if max_beats_per_patient <= 0 or max_negative_per_positive <= 0:
        raise ValueError("epoch sampling caps must be positive")
    rng = np.random.RandomState(int(seed) + 1_000_003 * int(epoch))
    patient_capped: List[int] = []
    for patient_id in sorted(set(patient_ids.tolist())):
        patient_indices = np.flatnonzero(patient_ids == patient_id)
        positive = patient_indices[labels[patient_indices] == 1].copy()
        negative = patient_indices[labels[patient_indices] == 0].copy()
        rng.shuffle(positive)
        rng.shuffle(negative)
        keep_positive = positive[:max_beats_per_patient]
        remaining = max_beats_per_patient - len(keep_positive)
        patient_capped.extend(keep_positive.tolist())
        patient_capped.extend(negative[:remaining].tolist())

    capped = np.asarray(patient_capped, dtype=np.int64)
    positive = capped[labels[capped] == 1]
    negative = capped[labels[capped] == 0]
    rng.shuffle(negative)
    negative = negative[: max_negative_per_positive * len(positive)]
    selected = np.concatenate((positive, negative))
    rng.shuffle(selected)
    return selected


class EpochPatientCappedSampler(Sampler[int]):
    """Advance a reproducible capped sample selection each time an epoch starts."""

    def __init__(
        self,
        labels: np.ndarray,
        patient_ids: np.ndarray,
        *,
        max_beats_per_patient: int,
        max_negative_per_positive: int,
        seed: int,
    ) -> None:
        self.labels = np.asarray(labels, dtype=np.int64)
        self.patient_ids = np.asarray(patient_ids)
        self.max_beats_per_patient = int(max_beats_per_patient)
        self.max_negative_per_positive = int(max_negative_per_positive)
        self.seed = int(seed)
        self.epoch = 0
        self._length = len(self._indices(0))

    def _indices(self, epoch: int) -> np.ndarray:
        return build_epoch_sample_indices(
            self.labels,
            self.patient_ids,
            max_beats_per_patient=self.max_beats_per_patient,
            max_negative_per_positive=self.max_negative_per_positive,
            seed=self.seed,
            epoch=epoch,
        )

    def __iter__(self):
        indices = self._indices(self.epoch)
        self.epoch += 1
        return iter(indices.tolist())

    def __len__(self) -> int:
        return self._length


class BeatDataset(Dataset):
    """In-memory or array-backed beat dataset with augmentation support."""

    def __init__(
        self,
        waveforms: np.ndarray,       # [N, 160] float32 or int8
        features: np.ndarray,        # [N, 4] float32 or int8
        labels: np.ndarray,          # [N] int64 (0: non_VEB, 1: VEB)
        patient_ids: np.ndarray,     # [N] str or int
        record_ids: Optional[np.ndarray] = None,
        sample_indices: Optional[np.ndarray] = None,
        native_symbols: Optional[np.ndarray] = None,
        source_file_sha256: Optional[np.ndarray] = None,
        input_divisor: float = 1.0,
        use_features: bool = True,
        augmentation_cfg: Optional[Dict[str, Any]] = None,
        is_training: bool = False
    ):
        self.waveforms = np.asarray(waveforms, dtype=np.float32)
        self.features = np.asarray(features, dtype=np.float32) if use_features else np.zeros_like(features, dtype=np.float32)
        self.labels = np.asarray(labels, dtype=np.int64)
        self.patient_ids = np.asarray(patient_ids)
        sample_count = len(self.labels)
        self.record_ids = np.asarray(record_ids) if record_ids is not None else np.asarray(["unknown"] * sample_count)
        self.sample_indices = np.asarray(sample_indices, dtype=np.int64) if sample_indices is not None else np.arange(sample_count, dtype=np.int64)
        self.native_symbols = np.asarray(native_symbols) if native_symbols is not None else np.asarray(["unknown"] * sample_count)
        self.source_file_sha256 = np.asarray(source_file_sha256) if source_file_sha256 is not None else np.asarray(["unknown"] * sample_count)
        self.input_divisor = float(input_divisor)
        if not math.isfinite(self.input_divisor) or self.input_divisor <= 0.0:
            raise ValueError("input_divisor must be a positive finite value")
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
        x_wave = torch.from_numpy(wave / self.input_divisor).unsqueeze(0).float()
        x_feat = torch.from_numpy(feat / self.input_divisor).float()
        y = torch.tensor(label, dtype=torch.long)

        return x_wave, x_feat, y, pat_id

    def sample_metadata(self, idx: int) -> Dict[str, Any]:
        return {
            "patient_id": str(self.patient_ids[idx]),
            "record_id": str(self.record_ids[idx]),
            "sample_index": int(self.sample_indices[idx]),
            "native_symbol": str(self.native_symbols[idx]),
            "source_file_sha256": str(self.source_file_sha256[idx]),
        }


def evaluate_model_at_threshold(
    model: nn.Module,
    dataloader: DataLoader,
    threshold: float,
    device: torch.device,
    return_failures: bool = False,
    return_average_precision: bool = False,
):
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
    all_probs: List[float] = []
    failures: List[Dict[str, Any]] = []

    with torch.no_grad():
        for x_wave, x_feat, y, pat_ids in dataloader:
            batch_start = total_samples
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

            for offset, (p, t, pid, probability) in enumerate(zip(preds, targets, pat_ids, probs)):
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
                if return_failures and int(p) != int(t):
                    metadata = dataloader.dataset.sample_metadata(batch_start + offset)
                    metadata.update(
                        {
                            "target": int(t),
                            "prediction": int(p),
                            "veb_probability": float(probability),
                            "error_type": "VFN" if int(t) == 1 else "VFP",
                        }
                    )
                    failures.append(metadata)

            all_preds.extend(preds.tolist())
            all_targets.extend(targets.tolist())
            all_probs.extend(probs.tolist())

    # Overall Gross F1 score for VEB
    gross_vtp = sum(c.vtp for c in patient_counts.values())
    gross_vfn = sum(c.vfn for c in patient_counts.values())
    gross_vfp = sum(c.vfp for c in patient_counts.values())

    precision = (gross_vtp / (gross_vtp + gross_vfp)) if (gross_vtp + gross_vfp) > 0 else 0.0
    recall = (gross_vtp / (gross_vtp + gross_vfn)) if (gross_vtp + gross_vfn) > 0 else 0.0
    f1 = (2.0 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0

    avg_loss = total_loss / max(1, total_samples)
    if return_failures:
        return patient_counts, f1, avg_loss, failures
    if return_average_precision:
        return patient_counts, f1, avg_loss, binary_average_precision(all_targets, all_probs)
    return patient_counts, f1, avg_loss


def binary_average_precision(targets: Sequence[int], probabilities: Sequence[float]) -> float:
    """Threshold-grouped binary AP; deterministic even when probabilities tie."""
    labels = np.asarray(targets, dtype=np.int64)
    scores = np.asarray(probabilities, dtype=np.float64)
    if labels.ndim != 1 or scores.shape != labels.shape or len(labels) == 0:
        raise ValueError("average precision inputs must be aligned non-empty vectors")
    if set(labels.tolist()) - {0, 1}:
        raise ValueError("average precision targets must be binary")
    if not np.isfinite(scores).all():
        raise ValueError("average precision probabilities must be finite")
    positive_count = int(np.sum(labels == 1))
    if positive_count == 0:
        raise ValueError("average precision requires at least one positive")

    order = np.argsort(-scores, kind="stable")
    sorted_scores = scores[order]
    sorted_labels = labels[order]
    tp = 0
    fp = 0
    previous_recall = 0.0
    average_precision = 0.0
    position = 0
    while position < len(sorted_scores):
        stop = position + 1
        while stop < len(sorted_scores) and sorted_scores[stop] == sorted_scores[position]:
            stop += 1
        group = sorted_labels[position:stop]
        tp += int(np.sum(group == 1))
        fp += int(np.sum(group == 0))
        recall = tp / positive_count
        precision = tp / (tp + fp)
        average_precision += (recall - previous_recall) * precision
        previous_recall = recall
        position = stop
    return float(average_precision)


def evaluate_se_ge_90_plus_p(
    model: nn.Module,
    dataloader: DataLoader,
    device: torch.device,
    target_se: float = 0.90,
) -> Tuple[float, float, float]:
    """Computes max +P on dataloader subject to VEB Se >= target_se (90.0%).
    Returns (score, best_se, best_plus_p).
    If no threshold meets target_se, score is negative deficit to target_se.
    """
    model.eval()
    all_probs = []
    all_targets = []
    with torch.no_grad():
        for x_wave, x_feat, y, _ in dataloader:
            x_wave = x_wave.to(device)
            x_feat = x_feat.to(device)
            logits = model(x_wave, x_feat)
            probs = torch.softmax(logits, dim=1)[:, 1].cpu().numpy()
            all_probs.extend(probs.tolist())
            all_targets.extend(y.numpy().tolist())
    probs_arr = np.array(all_probs)
    targets_arr = np.array(all_targets)

    total_pos = int(np.sum(targets_arr == 1))
    if total_pos == 0:
        return 0.0, 0.0, 0.0

    best_plus_p = 0.0
    best_se = 0.0
    max_se_overall = 0.0
    target_pct = target_se * 100.0

    for th in np.arange(0.01, 0.99, 0.01):
        preds = (probs_arr >= th).astype(np.int64)
        tp = int(np.sum((targets_arr == 1) & (preds == 1)))
        fp = int(np.sum((targets_arr == 0) & (preds == 1)))
        se = (tp / total_pos) * 100.0
        plus_p = (tp / (tp + fp) * 100.0) if (tp + fp) > 0 else 0.0
        max_se_overall = max(max_se_overall, se)
        if se >= target_pct:
            if plus_p > best_plus_p:
                best_plus_p = plus_p
                best_se = se

    if best_se >= target_pct:
        score = best_plus_p
    else:
        score = -1.0 * (target_pct - max_se_overall)
    return float(score), float(best_se), float(best_plus_p)


def scan_optimal_threshold(
    model: nn.Module,
    val_loader: DataLoader,
    device: torch.device,
    scan_range: Tuple[float, float] = (0.001, 0.999),
    scan_step: float = 0.001,
    min_veb_plus_p: float = 0.95,
    max_veb_fpr: float = 0.0025,
    min_veb_se: float = 0.90,
) -> Tuple[float, Dict[str, Any]]:
    """
    Scans decision threshold on validation set according to Section 6.2 priority:
      1. Filter thresholds with VEB Se >= 90.0%, VEB +P >= 95.0%, and
         VEB FPR <= 0.25%.
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

        meets_gate = (
            se >= min_veb_se * 100.0
            and plus_p >= min_veb_plus_p * 100.0
            and fpr <= max_veb_fpr * 100.0
        )

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

    if not valid_candidates:
        def f1_percent(candidate: Dict[str, Any]) -> float:
            se = float(candidate["se_percent"])
            plus_p = float(candidate["plus_p_percent"])
            return (2.0 * se * plus_p / (se + plus_p)) if se + plus_p > 0 else 0.0

        under_fpr = [c for c in candidate_thresholds if c["fpr_percent"] <= max_veb_fpr * 100.0]
        under_plus_p = [c for c in candidate_thresholds if c["plus_p_percent"] >= min_veb_plus_p * 100.0]
        under_plus_p_and_fpr = [
            c for c in candidate_thresholds
            if c["plus_p_percent"] >= min_veb_plus_p * 100.0
            and c["fpr_percent"] <= max_veb_fpr * 100.0
        ]
        summary = {
            "status": "rejected",
            "checkpoint_freezable": False,
            "valid_threshold_count": 0,
            "total_thresholds_scanned": len(candidate_thresholds),
            "scan_step": scan_step,
            "frozen_min_veb_se_percent": min_veb_se * 100.0,
            "frozen_min_veb_plus_p_percent": min_veb_plus_p * 100.0,
            "frozen_max_veb_fpr_percent": max_veb_fpr * 100.0,
            "best_f1_diagnostic": max(candidate_thresholds, key=f1_percent),
            "best_se_under_fpr_gate": max(
                under_fpr,
                key=lambda c: (c["se_percent"], c["plus_p_percent"]),
                default=None,
            ),
            "best_se_under_plus_p_gate": max(
                under_plus_p,
                key=lambda c: (c["se_percent"], -c["fpr_percent"]),
                default=None,
            ),
            "best_se_under_plus_p_and_fpr_gates": max(
                under_plus_p_and_fpr,
                key=lambda c: c["se_percent"],
                default=None,
            ),
            "thresholds": candidate_thresholds,
        }
        raise ThresholdGateError(summary)

    # Sort by: -se_percent, -plus_p_percent, abs(threshold - 0.5)
    valid_candidates.sort(key=lambda c: (-c["se_percent"], -c["plus_p_percent"], abs(c["threshold"] - 0.5)))
    best = valid_candidates[0]
    chosen_th = best["threshold"]

    summary = {
        "selected_threshold": chosen_th,
        "selected_metrics": best,
        "valid_threshold_count": len(valid_candidates),
        "total_thresholds_scanned": len(candidate_thresholds),
        "scan_step": scan_step,
        "frozen_min_veb_se_percent": min_veb_se * 100.0,
        "frozen_min_veb_plus_p_percent": min_veb_plus_p * 100.0,
        "frozen_max_veb_fpr_percent": max_veb_fpr * 100.0,
    }
    return chosen_th, summary


def train_single_run(
    config: Dict[str, Any],
    train_data: Dict[str, np.ndarray],
    val_data: Dict[str, np.ndarray],
    test_data: Optional[Dict[str, np.ndarray]],
    normalization: Dict[str, Any],
    output_dir: str,
    seed: int = 17,
    device_str: str = "cuda",
    evaluate_internal_test: bool = False,
) -> Dict[str, Any]:
    """Train and select a validation candidate without opening internal_test."""
    if evaluate_internal_test or test_data is not None:
        raise ValueError(
            "the training path cannot receive or evaluate internal_test; "
            "use a separate one-shot frozen-checkpoint evaluator with an authorization receipt"
        )
    os.makedirs(output_dir, exist_ok=True)
    run_mode = str(config.get("run_mode", "formal"))
    is_formal_run = run_mode == "formal"

    # Set seeds
    torch.manual_seed(seed)
    np.random.seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)

    device = torch.device(device_str if (torch.cuda.is_available() and "cuda" in device_str) else "cpu")

    use_features = config["model"].get("use_features", True)
    model_cfg = config.get("model", {})
    num_features = int(model_cfg.get("num_features", 4))
    for split_name, split_data in (("train", train_data), ("validation", val_data)):
        actual_features = int(np.asarray(split_data["features"]).shape[1])
        if actual_features != num_features:
            raise ValueError(
                f"{split_name} cache has {actual_features} features but model config requires {num_features}"
            )
    normalization_names = normalization.get("feature_names")
    if num_features > 4:
        if normalization.get("feature_contract_id") != "qn88-ec57-hybrid-io-lookahead-v2":
            raise ValueError("lookahead training requires the v2 feature contract")
        if normalization.get("decision_latency_mode") != "next_valid_qrs":
            raise ValueError("lookahead training requires next_valid_qrs latency semantics")
        if not isinstance(normalization_names, list) or len(normalization_names) != num_features:
            raise ValueError("lookahead normalization is missing the exact feature order")
    aug_cfg = config.get("augmentation", {})
    input_divisor = float(config.get("data", {}).get("fp32_input_divisor", 1.0))

    train_ds = BeatDataset(
        waveforms=train_data["waveforms"],
        features=train_data["features"],
        labels=train_data["labels"],
        patient_ids=train_data["patient_ids"],
        record_ids=train_data.get("record_ids"),
        sample_indices=train_data.get("sample_indices"),
        native_symbols=train_data.get("native_symbols"),
        source_file_sha256=train_data.get("source_file_sha256"),
        input_divisor=input_divisor,
        use_features=use_features,
        augmentation_cfg=aug_cfg,
        is_training=True
    )
    val_ds = BeatDataset(
        waveforms=val_data["waveforms"],
        features=val_data["features"],
        labels=val_data["labels"],
        patient_ids=val_data["patient_ids"],
        record_ids=val_data.get("record_ids"),
        sample_indices=val_data.get("sample_indices"),
        native_symbols=val_data.get("native_symbols"),
        source_file_sha256=val_data.get("source_file_sha256"),
        input_divisor=input_divisor,
        use_features=use_features,
        is_training=False
    )
    batch_size = config["training"]["batch_size"]
    data_cfg = config.get("data", {})
    ratio_text = str(data_cfg.get("max_pos_neg_ratio", "1:4"))
    try:
        max_negative_per_positive = int(ratio_text.split(":", 1)[1])
    except (IndexError, ValueError) as error:
        raise ValueError(f"invalid max_pos_neg_ratio: {ratio_text}") from error
    train_sampler = EpochPatientCappedSampler(
        train_ds.labels,
        train_ds.patient_ids,
        max_beats_per_patient=int(data_cfg.get("max_beats_per_patient_epoch", 10000)),
        max_negative_per_positive=max_negative_per_positive,
        seed=seed,
    )
    train_loader = DataLoader(train_ds, batch_size=batch_size, sampler=train_sampler, drop_last=False)
    val_loader = DataLoader(val_ds, batch_size=batch_size, shuffle=False)

    temporal_pool_bins = int(model_cfg.get("temporal_pool_bins", 1))
    mlp_hidden_dim = int(model_cfg.get("mlp_hidden_dim", 0))
    dilation = int(model_cfg.get("dilation", 1))
    architecture = str(model_cfg.get("architecture", "TinyECGCNN_NV"))
    if architecture == "TinyECGCNN_NV":
        model = TinyECGCNN_NV(
            temporal_pool_bins=temporal_pool_bins,
            num_features=num_features,
            mlp_hidden_dim=mlp_hidden_dim,
            dilation=dilation,
            use_bilinear_gating=model_cfg.get("use_bilinear_gating", False),
        ).to(device)
    elif architecture == "MediumECGCNN_NV":
        model = MediumECGCNN_NV(
            temporal_pool_bins=temporal_pool_bins,
            num_features=num_features,
            mlp_hidden_dim=mlp_hidden_dim,
            dilation=dilation,
        ).to(device)
    elif architecture == "TinyECGCNN_NV_Depthwise":
        model = TinyECGCNN_NV_Depthwise(temporal_pool_bins=temporal_pool_bins, num_features=num_features).to(device)
    elif architecture == "DualBranchECGCNN_NV":
        model = DualBranchECGCNN_NV(
            temporal_pool_bins=temporal_pool_bins,
            num_features=num_features,
            morph_emb_dim=int(model_cfg.get("morph_emb_dim", 24)),
            timing_emb_dim=int(model_cfg.get("timing_emb_dim", 24)),
            dilation=dilation,
        ).to(device)
    else:
        raise ValueError(f"unsupported model architecture: {architecture}")

    deployment_resources = estimate_model_deployment_resources(
        model,
        input_len=int(model_cfg.get("input_length", 160)),
    )
    resource_limits = frozen_model_resource_limits()
    resource_violations = [
        f"{name}={deployment_resources[name]} > {limit}"
        for name, limit in resource_limits.items()
        if deployment_resources[name] > limit
    ]
    if resource_violations:
        error = ModelResourceBudgetError(deployment_resources, resource_violations)
        resource_failure = {
            "status": "rejected",
            "checkpoint_freezable": False,
            "run_mode": run_mode,
            "evaluation_scope": "pre_training_resource_gate",
            "resources": deployment_resources,
            "limits": resource_limits,
            "violations": resource_violations,
        }
        rejection_metrics = {
            "status": "rejected",
            "checkpoint_freezable": False,
            "run_mode": run_mode,
            "seed": seed,
            "evaluation_scope": "pre_training_resource_gate",
            "parameter_count": count_parameters(model),
            "deployment_resources": deployment_resources,
            "resource_gate_failure": resource_failure,
        }
        rejection_artifacts = {
            "config.json": config,
            "normalization.json": normalization,
            "resource_gate_failure.json": resource_failure,
            "metrics.json": rejection_metrics,
        }
        for filename, payload in rejection_artifacts.items():
            with open(os.path.join(output_dir, filename), "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2)
        with open(os.path.join(output_dir, "manifest_sha256.txt"), "w", encoding="utf-8") as handle:
            for filename in rejection_artifacts:
                handle.write(f"{compute_sha256(os.path.join(output_dir, filename))}  {filename}\n")
        raise error

    # Optimizer and Loss
    lr = config["training"]["lr"]
    wd = config["training"]["weight_decay"]
    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=wd)

    veb_weight = config["training"].get("veb_class_weight", 2.5)
    class_weights = torch.tensor([1.0, float(veb_weight)], dtype=torch.float32).to(device)
    loss_name = str(config["training"].get("loss", "weighted_cross_entropy"))
    if loss_name == "weighted_cross_entropy":
        criterion = nn.CrossEntropyLoss(weight=class_weights)
    elif loss_name == "asymmetric_negative_focal_cross_entropy":
        criterion = AsymmetricNegativeFocalCrossEntropyLoss(
            class_weights,
            float(config["training"].get("negative_focal_gamma", -1.0)),
        ).to(device)
    elif loss_name == "asymmetric_margin_cross_entropy":
        criterion = AsymmetricMarginCrossEntropyLoss(
            class_weights,
            fp_margin=float(config["training"].get("fp_margin", 0.05)),
            fp_penalty_weight=float(config["training"].get("fp_penalty_weight", 2.0)),
        ).to(device)
    elif loss_name == "asymmetric_hard_negative_mining":
        criterion = AsymmetricHardNegativeMiningLoss(
            class_weights,
            fp_margin=float(config["training"].get("fp_margin", 0.03)),
            fp_penalty_weight=float(config["training"].get("fp_penalty_weight", 3.0)),
            wide_qrs_extra_weight=float(config["training"].get("wide_qrs_extra_weight", 5.0)),
        ).to(device)
    elif loss_name == "compensatory_consistency":
        criterion = CompensatoryConsistencyLoss(
            class_weights,
            fp_margin=float(config["training"].get("fp_margin", 0.02)),
            fp_penalty_weight=float(config["training"].get("fp_penalty_weight", 3.5)),
            wide_qrs_extra_weight=float(config["training"].get("wide_qrs_extra_weight", 6.0)),
            comp_neg_weight=float(config["training"].get("comp_neg_weight", 8.0)),
        ).to(device)
    else:
        raise ValueError(f"unsupported training loss: {loss_name}")

    max_epochs = config["training"]["max_epochs"]
    patience = config["training"]["early_stopping_patience"]

    use_scheduler = config["training"].get("scheduler") == "cosine"
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=max_epochs, eta_min=1e-5) if use_scheduler else None

    checkpoint_metric = str(config["training"].get("early_stopping_metric", "val_veb_f1"))
    if checkpoint_metric not in {"val_veb_f1", "val_average_precision", "val_se_ge_90_plus_p"}:
        raise ValueError(f"unsupported early_stopping_metric: {checkpoint_metric}")
    best_val_score = -1e9
    best_val_f1 = -1.0
    best_val_average_precision = -1.0
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
            if isinstance(criterion, (AsymmetricHardNegativeMiningLoss, CompensatoryConsistencyLoss)):
                loss = criterion(logits, y, x_feat)
            else:
                loss = criterion(logits, y)
            loss.backward()
            optimizer.step()

            train_loss += loss.item() * len(y)
            train_samples += len(y)

        if scheduler is not None:
            scheduler.step()

        avg_train_loss = train_loss / max(1, train_samples)

        # Validation evaluation at default 0.5 threshold
        _, val_f1, avg_val_loss, val_average_precision = evaluate_model_at_threshold(
            model,
            val_loader,
            threshold=0.5,
            device=device,
            return_average_precision=True,
        )

        history.append({
            "epoch": epoch,
            "train_loss": avg_train_loss,
            "val_loss": avg_val_loss,
            "val_veb_f1": val_f1,
            "val_average_precision": val_average_precision,
        })

        if checkpoint_metric == "val_veb_f1":
            checkpoint_score = val_f1
        elif checkpoint_metric == "val_se_ge_90_plus_p":
            se_score, _, _ = evaluate_se_ge_90_plus_p(model, val_loader, device=device, target_se=0.90)
            checkpoint_score = se_score
        else:
            checkpoint_score = val_average_precision

        if checkpoint_score > best_val_score + 1e-4:
            best_val_score = checkpoint_score
            best_val_f1 = val_f1
            best_val_average_precision = val_average_precision
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
    min_se = th_cfg.get("min_veb_se", 0.90)
    min_plus_p = th_cfg.get("min_veb_plus_p", 0.95)
    max_fpr = th_cfg.get("max_veb_fpr", 0.0025)
    try:
        optimal_th, th_summary = scan_optimal_threshold(
            model, val_loader, device=device,
            min_veb_se=min_se, min_veb_plus_p=min_plus_p, max_veb_fpr=max_fpr
        )
    except ThresholdGateError as error:
        model_path = os.path.join(output_dir, "model_fp32.pt")
        torch.save(model.state_dict(), model_path)
        with open(os.path.join(output_dir, "config.json"), "w", encoding="utf-8") as handle:
            json.dump(config, handle, indent=2)
        with open(os.path.join(output_dir, "normalization.json"), "w", encoding="utf-8") as handle:
            json.dump(normalization, handle, indent=2)
        with open(os.path.join(output_dir, "threshold_gate_failure.json"), "w", encoding="utf-8") as handle:
            json.dump(error.summary, handle, indent=2)
        rejected_metrics = {
            "status": "rejected",
            "checkpoint_freezable": False,
            "run_mode": run_mode,
            "seed": seed,
            "evaluation_scope": "validation_only",
            "best_epoch": best_epoch,
            "total_epochs": len(history),
            "best_val_veb_f1": best_val_f1,
            "best_val_average_precision": best_val_average_precision,
            "checkpoint_selection_metric": checkpoint_metric,
            "best_checkpoint_score": best_val_score,
            "history": history,
            "parameter_count": count_parameters(model),
            "macs_per_beat": count_macs(model),
            "deployment_resources": deployment_resources,
            "threshold_gate_failure": {
                key: value for key, value in error.summary.items() if key != "thresholds"
            },
        }
        with open(os.path.join(output_dir, "metrics.json"), "w", encoding="utf-8") as handle:
            json.dump(rejected_metrics, handle, indent=2)
        model_hash = compute_sha256(model_path)
        with open(os.path.join(output_dir, "model_sha256.txt"), "w", encoding="utf-8") as handle:
            handle.write(f"{model_hash}  model_fp32.pt\n")
        rejected_names = [
            "config.json",
            "normalization.json",
            "threshold_gate_failure.json",
            "metrics.json",
            "model_fp32.pt",
            "model_sha256.txt",
        ]
        with open(os.path.join(output_dir, "manifest_sha256.txt"), "w", encoding="utf-8") as handle:
            for filename in rejected_names:
                handle.write(f"{compute_sha256(os.path.join(output_dir, filename))}  {filename}\n")
        raise

    if not is_formal_run:
        artifact_status = "smoke_only"
        checkpoint_freezable = False
    else:
        artifact_status = "validation_candidate"
        checkpoint_freezable = True
    th_summary = dict(th_summary)
    th_summary.update({
        "status": artifact_status,
        "checkpoint_freezable": checkpoint_freezable,
        "run_mode": run_mode,
    })

    # Save artifacts
    model_path = os.path.join(output_dir, "model_fp32.pt")
    torch.save(model.state_dict(), model_path)

    config_out_path = os.path.join(output_dir, "config.json")
    with open(config_out_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)

    normalization_out_path = os.path.join(output_dir, "normalization.json")
    with open(normalization_out_path, "w", encoding="utf-8") as f:
        json.dump(normalization, f, indent=2)

    threshold_out_path = os.path.join(output_dir, "decision_threshold.json")
    with open(threshold_out_path, "w", encoding="utf-8") as f:
        json.dump(th_summary, f, indent=2)

    metrics_out_path = os.path.join(output_dir, "metrics.json")
    metrics_payload = {
            "status": artifact_status,
            "checkpoint_freezable": checkpoint_freezable,
            "run_mode": run_mode,
            "seed": seed,
            "evaluation_scope": "validation_only",
            "best_epoch": best_epoch,
            "total_epochs": len(history),
            "best_val_veb_f1": best_val_f1,
            "best_val_average_precision": best_val_average_precision,
            "checkpoint_selection_metric": checkpoint_metric,
            "best_checkpoint_score": best_val_score,
            "optimal_threshold": optimal_th,
            "validation_threshold_search": th_summary,
            "history": history,
            "parameter_count": count_parameters(model),
            "macs_per_beat": count_macs(model),
            "deployment_resources": deployment_resources,
        }
    with open(metrics_out_path, "w", encoding="utf-8") as f:
        json.dump(metrics_payload, f, indent=2)

    # Compute hashes
    model_hash = compute_sha256(model_path)
    with open(os.path.join(output_dir, "model_sha256.txt"), "w", encoding="utf-8") as f:
        f.write(f"{model_hash}  model_fp32.pt\n")

    manifest_lines = []
    artifact_names = ["config.json", "normalization.json", "decision_threshold.json", "metrics.json", "model_fp32.pt", "model_sha256.txt"]
    for fname in artifact_names:
        fpath = os.path.join(output_dir, fname)
        if os.path.exists(fpath):
            manifest_lines.append(f"{compute_sha256(fpath)}  {fname}\n")
    with open(os.path.join(output_dir, "manifest_sha256.txt"), "w", encoding="utf-8") as f:
        f.writelines(manifest_lines)

    result = {
        "status": artifact_status,
        "checkpoint_freezable": checkpoint_freezable,
        "run_mode": run_mode,
        "seed": seed,
        "evaluation_scope": "validation_only",
        "optimal_threshold": optimal_th,
        "model_sha256": model_hash
    }
    return result
