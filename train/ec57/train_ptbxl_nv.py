import os
import sys
import json
import time
import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Dataset

# Add base dir
base_dir = r"C:\Users\Administrator\Desktop\LRX\ecg_ti_pipeline_3"
if base_dir not in sys.path:
    sys.path.insert(0, base_dir)

from train.ec57.metrics import VEBConfusionCounts, wilson_score_interval

class FocalLoss(nn.Module):
    """Binary Focal Loss for severe class imbalance."""
    def __init__(self, alpha=0.90, gamma=2.5):
        super().__init__()
        self.alpha = alpha
        self.gamma = gamma

    def forward(self, logits, targets):
        probs = torch.softmax(logits, dim=1)
        p_t = probs[torch.arange(len(targets)), targets]
        alpha_t = torch.where(targets == 1, self.alpha, 1.0 - self.alpha)
        loss = -alpha_t * ((1.0 - p_t) ** self.gamma) * torch.log(torch.clamp(p_t, min=1e-8))
        return loss.mean()

class TinyECGCNN_NV_MLP(nn.Module):
    """TinyECGCNN with 2-layer MLP fusion head (1,874 params, strictly within 2,048 budget)."""
    def __init__(self):
        super().__init__()
        self.conv1 = nn.Conv1d(1, 8, kernel_size=7, padding=3, bias=True)
        self.act1 = nn.ReLU()
        self.pool1 = nn.MaxPool1d(2, 2)

        self.conv2 = nn.Conv1d(8, 16, kernel_size=5, padding=2, bias=True)
        self.act2 = nn.ReLU()
        self.pool2 = nn.MaxPool1d(2, 2)

        self.conv3 = nn.Conv1d(16, 16, kernel_size=3, padding=1, bias=True)
        self.act3 = nn.ReLU()
        self.gap = nn.AdaptiveAvgPool1d(1)

        # 2-layer fusion head: 20 -> 16 -> 2
        self.fc1 = nn.Linear(20, 16, bias=True)
        self.act_fc = nn.ReLU()
        self.fc2 = nn.Linear(16, 2, bias=True)

    def forward(self, x_wave, x_feat):
        if x_wave.ndim == 2:
            x_wave = x_wave.unsqueeze(1)
        h1 = self.pool1(self.act1(self.conv1(x_wave)))
        h2 = self.pool2(self.act2(self.conv2(h1)))
        h3 = self.act3(self.conv3(h2))
        h_gap = self.gap(h3).view(x_wave.size(0), 16)
        h_concat = torch.cat([h_gap, x_feat], dim=1)
        logits = self.fc2(self.act_fc(self.fc1(h_concat)))
        return logits

class PTBXLBeatDataset(Dataset):
    def __init__(self, waveforms, features, labels, patient_ids, is_training=True):
        self.waves = waveforms.astype(np.float32) / 128.0
        self.feats = features.astype(np.float32) / 128.0
        self.labels = labels.astype(np.int64)
        self.patient_ids = patient_ids
        self.is_training = is_training

    def __len__(self):
        return len(self.labels)

    def __getitem__(self, idx):
        wave = self.waves[idx]
        feat = self.feats[idx]
        label = self.labels[idx]
        pid = str(self.patient_ids[idx])

        if self.is_training:
            gain = np.random.uniform(0.85, 1.15)
            wave = wave * gain
            shift = np.random.randint(-3, 4)
            wave = np.roll(wave, shift)

        x_wave = torch.from_numpy(wave).unsqueeze(0).float()
        x_feat = torch.from_numpy(feat).float()
        y = torch.tensor(label, dtype=torch.long)
        return x_wave, x_feat, y, pid

def train_and_eval(gpu_id=2, seed=17, max_epochs=60, alpha=0.90, gamma=2.5, output_dir=""):
    torch.manual_seed(seed)
    np.random.seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)

    device = torch.device(f"cuda:{gpu_id}" if torch.cuda.is_available() else "cpu")
    print(f"Using device: {device}, Seed: {seed}")

    cache_dir = os.path.join(base_dir, "cache_ptbxl_beats_v1")
    train_npz = np.load(os.path.join(cache_dir, "train_beats.npz"))
    val_npz = np.load(os.path.join(cache_dir, "val_beats.npz"))
    test_npz = np.load(os.path.join(cache_dir, "test_beats.npz"))

    train_ds = PTBXLBeatDataset(train_npz["waveforms"], train_npz["features"], train_npz["labels"], train_npz["patient_ids"], is_training=True)
    val_ds = PTBXLBeatDataset(val_npz["waveforms"], val_npz["features"], val_npz["labels"], val_npz["patient_ids"], is_training=False)
    test_ds = PTBXLBeatDataset(test_npz["waveforms"], test_npz["features"], test_npz["labels"], test_npz["patient_ids"], is_training=False)

    train_loader = DataLoader(train_ds, batch_size=512, shuffle=True)
    val_loader = DataLoader(val_ds, batch_size=1024, shuffle=False)
    test_loader = DataLoader(test_ds, batch_size=1024, shuffle=False)

    model = TinyECGCNN_NV_MLP().to(device)
    criterion = FocalLoss(alpha=alpha, gamma=gamma)
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=max_epochs, eta_min=1e-5)

    best_val_f1 = 0.0
    best_model_state = None

    for epoch in range(1, max_epochs + 1):
        model.train()
        total_loss = 0.0
        for x_w, x_f, y, _ in train_loader:
            x_w, x_f, y = x_w.to(device), x_f.to(device), y.to(device)
            optimizer.zero_grad()
            logits = model(x_w, x_f)
            loss = criterion(logits, y)
            loss.backward()
            optimizer.step()
            total_loss += loss.item() * len(y)
        scheduler.step()

        # Val evaluation
        model.eval()
        val_probs = []
        val_targets = []
        with torch.no_grad():
            for x_w, x_f, y, _ in val_loader:
                x_w, x_f = x_w.to(device), x_f.to(device)
                logits = model(x_w, x_f)
                probs = torch.softmax(logits, dim=1)[:, 1].cpu().numpy()
                val_probs.extend(probs)
                val_targets.extend(y.numpy())

        val_probs = np.array(val_probs)
        val_targets = np.array(val_targets)
        preds = (val_probs >= 0.5).astype(int)
        vtp = np.sum((preds == 1) & (val_targets == 1))
        vfn = np.sum((preds == 0) & (val_targets == 1))
        vfp = np.sum((preds == 1) & (val_targets == 0))
        vtn = np.sum((preds == 0) & (val_targets == 0))
        se = (vtp / (vtp + vfn) * 100) if (vtp + vfn) > 0 else 0
        pp = (vtp / (vtp + vfp) * 100) if (vtp + vfp) > 0 else 0
        fpr = (vfp / (vtn + vfp) * 100) if (vtn + vfp) > 0 else 0
        f1 = (2 * se * pp) / (se + pp + 1e-8)

        if f1 > best_val_f1:
            best_val_f1 = f1
            best_model_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}

        if epoch % 5 == 0 or epoch == 1:
            print(f"Epoch {epoch:02d}: Loss={total_loss/len(train_ds):.4f}, Val Se={se:.2f}%, +P={pp:.2f}%, FPR={fpr:.2f}%, F1={f1:.2f}%")

    # Load best model
    if best_model_state:
        model.load_state_dict({k: v.to(device) for k, v in best_model_state.items()})

    # Threshold scanning on validation set
    model.eval()
    val_probs = []
    val_targets = []
    with torch.no_grad():
        for x_w, x_f, y, _ in val_loader:
            x_w, x_f = x_w.to(device), x_f.to(device)
            logits = model(x_w, x_f)
            probs = torch.softmax(logits, dim=1)[:, 1].cpu().numpy()
            val_probs.extend(probs)
            val_targets.extend(y.numpy())

    val_probs = np.array(val_probs)
    val_targets = np.array(val_targets)

    # Grid search for optimal threshold on validation set (maximizing F1)
    th_candidates = np.linspace(0.01, 0.99, 981)
    f1_candidates = []
    for th in th_candidates:
        p = (val_probs >= th).astype(int)
        tp = np.sum((p == 1) & (val_targets == 1))
        fn = np.sum((p == 0) & (val_targets == 1))
        fp = np.sum((p == 1) & (val_targets == 0))
        tn = np.sum((p == 0) & (val_targets == 0))
        c_se = (tp / (tp + fn) * 100) if (tp + fn) > 0 else 0
        c_pp = (tp / (tp + fp) * 100) if (tp + fp) > 0 else 0
        c_fpr = (fp / (tn + fp) * 100) if (tn + fp) > 0 else 0
        c_f1 = (2 * c_se * c_pp) / (c_se + c_pp + 1e-8)
        f1_candidates.append({
            "threshold": float(th),
            "f1": float(c_f1),
            "se": float(c_se),
            "plus_p": float(c_pp),
            "fpr": float(c_fpr),
            "tp": int(tp), "fn": int(fn), "fp": int(fp), "tn": int(tn)
        })

    # Sort by -f1, -se, abs(threshold - 0.5)
    f1_candidates.sort(key=lambda c: (-c["f1"], -c["se"], abs(c["threshold"] - 0.5)))
    best = f1_candidates[0]
    optimal_th = best["threshold"]
    print(f"\nValidation Optimal Threshold: {optimal_th:.4f} (Val F1={best['f1']:.2f}%, Se={best['se']:.2f}%, +P={best['plus_p']:.2f}%, FPR={best['fpr']:.2f}%)")

    # Test evaluation
    model.eval()
    test_probs = []
    test_targets = []
    test_pids = []
    with torch.no_grad():
        for x_w, x_f, y, pids in test_loader:
            x_w, x_f = x_w.to(device), x_f.to(device)
            logits = model(x_w, x_f)
            probs = torch.softmax(logits, dim=1)[:, 1].cpu().numpy()
            test_probs.extend(probs)
            test_targets.extend(y.numpy())
            test_pids.extend(pids)

    test_probs = np.array(test_probs)
    test_targets = np.array(test_targets)
    preds = (test_probs >= optimal_th).astype(int)

    tp = np.sum((preds == 1) & (test_targets == 1))
    fn = np.sum((preds == 0) & (test_targets == 1))
    fp = np.sum((preds == 1) & (test_targets == 0))
    tn = np.sum((preds == 0) & (test_targets == 0))

    t_se = (tp / (tp + fn) * 100) if (tp + fn) > 0 else 0
    t_pp = (tp / (tp + fp) * 100) if (tp + fp) > 0 else 0
    t_fpr = (fp / (tn + fp) * 100) if (tn + fp) > 0 else 0

    se_ci = wilson_score_interval(tp, tp + fn)
    pp_ci = wilson_score_interval(tp, tp + fp)
    fpr_ci = wilson_score_interval(fp, tn + fp)
    patient_counts = {}
    for pred, target, pid in zip(preds, test_targets, test_pids):
        if pid not in patient_counts:
            patient_counts[pid] = {"vtp": 0, "vfn": 0, "vfp": 0, "vtn": 0}
        if pred == 1 and target == 1:
            patient_counts[pid]["vtp"] += 1
        elif pred == 0 and target == 1:
            patient_counts[pid]["vfn"] += 1
        elif pred == 1 and target == 0:
            patient_counts[pid]["vfp"] += 1
        elif pred == 0 and target == 0:
            patient_counts[pid]["vtn"] += 1

    # 10,000 resample bootstrap CI
    np.random.seed(20260827)
    pids_list = list(patient_counts.keys())
    n_pats = len(pids_list)
    b_se, b_pp, b_fpr = [], [], []
    for _ in range(10000):
        sampled = np.random.choice(pids_list, size=n_pats, replace=True)
        btp = sum(patient_counts[p]["vtp"] for p in sampled)
        bfn = sum(patient_counts[p]["vfn"] for p in sampled)
        bfp = sum(patient_counts[p]["vfp"] for p in sampled)
        btn = sum(patient_counts[p]["vtn"] for p in sampled)
        if btp + bfn > 0:
            b_se.append(btp / (btp + bfn) * 100.0)
        if btp + bfp > 0:
            b_pp.append(btp / (btp + bfp) * 100.0)
        if btn + bfp > 0:
            b_fpr.append(bfp / (btn + bfp) * 100.0)

    bootstrap_se_ci = [float(np.percentile(b_se, 2.5)), float(np.percentile(b_se, 97.5))] if b_se else [0.0, 0.0]
    bootstrap_pp_ci = [float(np.percentile(b_pp, 2.5)), float(np.percentile(b_pp, 97.5))] if b_pp else [0.0, 0.0]
    bootstrap_fpr_ci = [float(np.percentile(b_fpr, 2.5)), float(np.percentile(b_fpr, 97.5))] if b_fpr else [0.0, 0.0]

    # Save artifacts if output_dir specified
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
        model_path = os.path.join(output_dir, "model_fp32.pt")
        torch.save(model.state_dict(), model_path)

        def compute_sha256(filepath):
            import hashlib
            h = hashlib.sha256()
            with open(filepath, "rb") as f:
                for chunk in iter(lambda: f.read(65536), b""):
                    h.update(chunk)
            return h.hexdigest()

        model_hash = compute_sha256(model_path)
        with open(os.path.join(output_dir, "model_sha256.txt"), "w", encoding="utf-8") as f:
            f.write(f"{model_hash}  model_fp32.pt\n")

        with open(os.path.join(output_dir, "decision_threshold.json"), "w", encoding="utf-8") as f:
            json.dump({
                "optimal_threshold": float(optimal_th),
                "val_f1_percent": float(best["f1"]),
                "val_se_percent": float(best["se"]),
                "val_plus_p_percent": float(best["plus_p"]),
                "val_fpr_percent": float(best["fpr"])
            }, f, indent=2)

        with open(os.path.join(output_dir, "config.json"), "w", encoding="utf-8") as f:
            json.dump({
                "model": {"name": "TinyECGCNN_NV_MLP", "parameters": 1874, "macs_per_beat": 91290},
                "training": {"loss": "FocalLoss", "alpha": alpha, "gamma": gamma, "epochs": max_epochs, "lr": 1e-3, "seed": seed}
            }, f, indent=2)

        with open(os.path.join(output_dir, "metrics.json"), "w", encoding="utf-8") as f:
            json.dump({
                "seed": seed,
                "optimal_threshold": float(optimal_th),
                "test_metrics": {
                    "vtp": int(tp), "vfn": int(fn), "vfp": int(fp), "vtn": int(tn),
                    "veb_se_percent": float(t_se),
                    "veb_plus_p_percent": float(t_pp),
                    "veb_fpr_percent": float(t_fpr),
                    "veb_se_ci": se_ci,
                    "veb_plus_p_ci": pp_ci,
                    "veb_fpr_ci": fpr_ci,
                    "patient_bootstrap_ci_10k": {
                        "veb_se_bootstrap_ci": bootstrap_se_ci,
                        "veb_plus_p_bootstrap_ci": bootstrap_pp_ci,
                        "veb_fpr_bootstrap_ci": bootstrap_fpr_ci
                    }
                }
            }, f, indent=2)

        manifest_lines = []
        for fname in ["config.json", "decision_threshold.json", "metrics.json", "model_fp32.pt", "model_sha256.txt"]:
            fpath = os.path.join(output_dir, fname)
            if os.path.exists(fpath):
                manifest_lines.append(f"{compute_sha256(fpath)}  {fname}\n")
        with open(os.path.join(output_dir, "manifest_sha256.txt"), "w", encoding="utf-8") as f:
            f.writelines(manifest_lines)

    return {
        "optimal_threshold": optimal_th,
        "test_metrics": {
            "vtp": int(tp), "vfn": int(fn), "vfp": int(fp), "vtn": int(tn),
            "veb_se_percent": float(t_se),
            "veb_plus_p_percent": float(t_pp),
            "veb_fpr_percent": float(t_fpr),
            "veb_se_ci": se_ci, "veb_plus_p_ci": pp_ci, "veb_fpr_ci": fpr_ci
        },
        "model_state": best_model_state
    }

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--gpu_id", type=int, default=2)
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--output_dir", type=str, default="")
    parser.add_argument("--max_epochs", type=int, default=60)
    args = parser.parse_args()
    train_and_eval(gpu_id=args.gpu_id, seed=args.seed, output_dir=args.output_dir, max_epochs=args.max_epochs)
