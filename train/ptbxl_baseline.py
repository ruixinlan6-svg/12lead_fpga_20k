#!/usr/bin/env python3
"""Small FP32 reference model for the PTB-XL five-superclass task."""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import random
import sys
from typing import Iterable

import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader, Dataset
import wfdb


LABELS = ("NORM", "MI", "STTC", "CD", "HYP")


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


class PTBXL(Dataset):
    def __init__(self, root: pathlib.Path, manifest: pathlib.Path, split: str):
        self.root = root
        self.rows = []
        with manifest.open(encoding="utf-8") as stream:
            for line in stream:
                entry = json.loads(line)
                fold = int(entry["fold"])
                entry_split = "train" if fold <= 8 else "val" if fold == 9 else "test" if fold == 10 else "unused"
                if entry_split == split:
                    self.rows.append(entry)
        if not self.rows:
            raise RuntimeError(f"empty split {split} in {manifest}")

    def __len__(self) -> int:
        return len(self.rows)

    def __getitem__(self, index: int):
        entry = self.rows[index]
        signal, _ = wfdb.rdsamp(str(self.root / entry["record"]))
        signal = np.asarray(signal, dtype=np.float32).T
        if signal.shape != (12, 1000):
            raise RuntimeError(f"unexpected signal shape {signal.shape} for {entry['record']}")
        signal = np.nan_to_num(signal, nan=0.0, posinf=5.0, neginf=-5.0)
        # Provisional hardware-friendly normalization: physical mV clipped to +/-5 mV.
        signal = np.clip(signal, -5.0, 5.0) / 5.0
        target = np.asarray(entry["label_vector"], dtype=np.float32)
        return torch.from_numpy(signal), torch.from_numpy(target)


class TinyECGCNN(nn.Module):
    def __init__(self, classes: int = 5):
        super().__init__()
        self.features = nn.Sequential(
            nn.Conv1d(12, 16, kernel_size=7, padding=3, bias=True),
            nn.ReLU(inplace=True),
            nn.MaxPool1d(2),
            nn.Conv1d(16, 32, kernel_size=7, padding=3, bias=True),
            nn.ReLU(inplace=True),
            nn.MaxPool1d(2),
            nn.Conv1d(32, 32, kernel_size=5, padding=2, bias=True),
            nn.ReLU(inplace=True),
            nn.AdaptiveAvgPool1d(1),
        )
        self.head = nn.Linear(32, classes)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.head(self.features(x).squeeze(-1))


def binary_auroc(y_true: np.ndarray, score: np.ndarray) -> float | None:
    positives = int(y_true.sum())
    negatives = int(y_true.size - positives)
    if positives == 0 or negatives == 0:
        return None
    order = np.argsort(-score, kind="mergesort")
    y = y_true[order]
    tpr = np.cumsum(y) / positives
    fpr = np.cumsum(1 - y) / negatives
    return float(np.trapz(np.r_[0.0, tpr], np.r_[0.0, fpr]))


def binary_auprc(y_true: np.ndarray, score: np.ndarray) -> float | None:
    positives = int(y_true.sum())
    if positives == 0:
        return None
    order = np.argsort(-score, kind="mergesort")
    y = y_true[order]
    recall = np.cumsum(y) / positives
    precision = np.cumsum(y) / np.arange(1, y.size + 1)
    return float(np.trapz(np.r_[0.0, precision], np.r_[0.0, recall]))


def summarize(target: np.ndarray, probability: np.ndarray) -> dict:
    per_class = {}
    aurocs, auprcs, f1s = [], [], []
    predicted = probability >= 0.5
    for index, label in enumerate(LABELS):
        y = target[:, index].astype(np.int32)
        p = probability[:, index]
        tp = int(np.logical_and(y == 1, predicted[:, index]).sum())
        fp = int(np.logical_and(y == 0, predicted[:, index]).sum())
        fn = int(np.logical_and(y == 1, ~predicted[:, index]).sum())
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        auroc = binary_auroc(y, p)
        auprc = binary_auprc(y, p)
        if auroc is not None:
            aurocs.append(auroc)
        if auprc is not None:
            auprcs.append(auprc)
        f1s.append(f1)
        per_class[label] = {"support": int(y.sum()), "tp": tp, "fp": fp, "fn": fn, "precision": precision, "recall": recall, "f1": f1, "auroc": auroc, "auprc": auprc}
    return {"macro_auroc": float(np.mean(aurocs)) if aurocs else None, "macro_auprc": float(np.mean(auprcs)) if auprcs else None, "macro_f1": float(np.mean(f1s)), "per_class": per_class}


@torch.no_grad()
def evaluate(model: nn.Module, loader: DataLoader, device: torch.device) -> tuple[dict, np.ndarray, np.ndarray]:
    model.eval()
    all_target, all_probability = [], []
    for signal, target in loader:
        logits = model(signal.to(device))
        all_target.append(target.numpy())
        all_probability.append(torch.sigmoid(logits).cpu().numpy())
    target = np.concatenate(all_target, axis=0)
    probability = np.concatenate(all_probability, axis=0)
    return summarize(target, probability), target, probability


def file_sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=pathlib.Path)
    parser.add_argument("--registry", required=True, type=pathlib.Path)
    parser.add_argument("--run-dir", required=True, type=pathlib.Path)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--epochs", type=int, default=8)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--num-workers", type=int, default=0)
    args = parser.parse_args()
    args.run_dir.mkdir(parents=True, exist_ok=True)
    set_seed(args.seed)
    device = torch.device(args.device if args.device.startswith("cuda") and torch.cuda.is_available() else "cpu")

    registry = json.loads(args.registry.read_text(encoding="utf-8"))
    manifest = args.registry.parent / registry["manifest"]["path"]
    train_set = PTBXL(args.root, manifest, "train")
    val_set = PTBXL(args.root, manifest, "val")
    test_set = PTBXL(args.root, manifest, "test")
    train_loader = DataLoader(train_set, batch_size=args.batch_size, shuffle=True, num_workers=args.num_workers, pin_memory=device.type == "cuda")
    val_loader = DataLoader(val_set, batch_size=args.batch_size, shuffle=False, num_workers=args.num_workers, pin_memory=device.type == "cuda")
    test_loader = DataLoader(test_set, batch_size=args.batch_size, shuffle=False, num_workers=args.num_workers, pin_memory=device.type == "cuda")

    model = TinyECGCNN().to(device)
    positive = np.zeros(len(LABELS), dtype=np.float64)
    for entry in train_set.rows:
        positive += np.asarray(entry["label_vector"], dtype=np.float64)
    negative = len(train_set) - positive
    pos_weight = torch.tensor(np.maximum(negative / np.maximum(positive, 1.0), 1.0), dtype=torch.float32, device=device)
    criterion = nn.BCEWithLogitsLoss(pos_weight=pos_weight)
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-4)
    best_val = -float("inf")
    best_path = args.run_dir / "checkpoint_best.pt"
    history = []
    for epoch in range(1, args.epochs + 1):
        model.train()
        losses = []
        for signal, target in train_loader:
            optimizer.zero_grad(set_to_none=True)
            loss = criterion(model(signal.to(device)), target.to(device))
            loss.backward()
            optimizer.step()
            losses.append(float(loss.detach().cpu()))
        val_metrics, _, _ = evaluate(model, val_loader, device)
        val_score = val_metrics["macro_auroc"] if val_metrics["macro_auroc"] is not None else -float("inf")
        history.append({"epoch": epoch, "train_loss": float(np.mean(losses)), "val": val_metrics})
        print(json.dumps(history[-1], sort_keys=True))
        if val_score > best_val:
            best_val = val_score
            torch.save({"model": model.state_dict(), "seed": args.seed, "epoch": epoch, "registry_sha256": file_sha256(args.registry)}, best_path)

    checkpoint = torch.load(best_path, map_location=device, weights_only=False)
    model.load_state_dict(checkpoint["model"])
    val_metrics, _, _ = evaluate(model, val_loader, device)
    test_metrics, _, _ = evaluate(model, test_loader, device)
    config = {"seed": args.seed, "epochs": args.epochs, "batch_size": args.batch_size, "device": str(device), "model": "TinyECGCNN", "normalization": "clip physical mV to [-5,5], divide by 5", "labels": list(LABELS), "registry_sha256": file_sha256(args.registry), "manifest_sha256": registry["manifest"]["sha256"]}
    (args.run_dir / "config.json").write_text(json.dumps(config, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (args.run_dir / "metrics.json").write_text(json.dumps({"config": config, "history": history, "best_epoch": checkpoint["epoch"], "val": val_metrics, "test": test_metrics}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"best_epoch": checkpoint["epoch"], "val": val_metrics, "test": test_metrics}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
