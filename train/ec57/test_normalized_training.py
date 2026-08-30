import os
import sys
import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Dataset

# Add base dir
base_dir = r"C:\Users\Administrator\Desktop\LRX\ecg_ti_pipeline_3"
if base_dir not in sys.path:
    sys.path.insert(0, base_dir)

from train.ec57.model_nv import TinyECGCNN_NV
from train.ec57.metrics import VEBConfusionCounts, wilson_score_interval

print("Loading cached beats...")
cache_dir = os.path.join(base_dir, "cache_ec57_beats_v1")
train_npz = np.load(os.path.join(cache_dir, "train_beats.npz"))
val_npz = np.load(os.path.join(cache_dir, "val_beats.npz"))

print(f"Train samples: {len(train_npz['labels'])} (VEB: {np.sum(train_npz['labels'] == 1)})")
print(f"Val samples:   {len(val_npz['labels'])} (VEB: {np.sum(val_npz['labels'] == 1)})")

# Compute feature medians and IQRs from train
raw_feats = train_npz["features"]
meds = np.median(raw_feats, axis=0)
q75, q25 = np.percentile(raw_feats, [75, 25], axis=0)
iqrs = np.maximum(q75 - q25, 1e-4)

print(f"Feature Medians: {meds}")
print(f"Feature IQRs:    {iqrs}")

class NormalizedBeatDataset(Dataset):
    def __init__(self, waveforms, features, labels, is_training=True):
        self.waves = waveforms.astype(np.float32) / 128.0
        self.feats = features.astype(np.float32) / 128.0
        self.labels = labels.astype(np.int64)
        self.is_training = is_training

    def __len__(self):
        return len(self.labels)

    def __getitem__(self, idx):
        wave = self.waves[idx]
        feat = self.feats[idx]
        label = self.labels[idx]

        if self.is_training:
            # Gain aug
            gain = np.random.uniform(0.8, 1.2)
            wave = wave * gain

        x_wave = torch.from_numpy(wave).unsqueeze(0).float()
        x_feat = torch.from_numpy(feat).float()
        y = torch.tensor(label, dtype=torch.long)
        return x_wave, x_feat, y

# Split val into val (60%) and test (40%) by patient
val_pats = np.unique(val_npz["patient_ids"])
np.random.seed(42)
np.random.shuffle(val_pats)
n_val = int(len(val_pats) * 0.6)
val_set = set(val_pats[:n_val])
test_set = set(val_pats[n_val:])

val_mask = np.isin(val_npz["patient_ids"], list(val_set))
test_mask = np.isin(val_npz["patient_ids"], list(test_set))

train_ds = NormalizedBeatDataset(train_npz["waveforms"], train_npz["features"], train_npz["labels"], is_training=True)
val_ds = NormalizedBeatDataset(val_npz["waveforms"][val_mask], val_npz["features"][val_mask], val_npz["labels"][val_mask], is_training=False)
test_ds = NormalizedBeatDataset(val_npz["waveforms"][test_mask], val_npz["features"][test_mask], val_npz["labels"][test_mask], is_training=False)

train_loader = DataLoader(train_ds, batch_size=512, shuffle=True)
val_loader = DataLoader(val_ds, batch_size=1024, shuffle=False)
test_loader = DataLoader(test_ds, batch_size=1024, shuffle=False)

device = torch.device("cuda:2" if torch.cuda.is_available() else "cpu")
model = TinyECGCNN_NV().to(device)

# Focal Loss / Weighted Cross Entropy
class_weight = torch.tensor([1.0, 5.0], dtype=torch.float32).to(device)
criterion = nn.CrossEntropyLoss(weight=class_weight)
optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-4)
scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=30, eta_min=1e-5)

print("Starting training with normalized inputs...")
best_f1 = 0.0
for epoch in range(1, 31):
    model.train()
    total_loss = 0.0
    for x_w, x_f, y in train_loader:
        x_w, x_f, y = x_w.to(device), x_f.to(device), y.to(device)
        optimizer.zero_grad()
        logits = model(x_w, x_f)
        loss = criterion(logits, y)
        loss.backward()
        optimizer.step()
        total_loss += loss.item() * len(y)
    scheduler.step()

    # Val eval
    model.eval()
    val_probs = []
    val_targets = []
    with torch.no_grad():
        for x_w, x_f, y in val_loader:
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
    if epoch % 5 == 0 or epoch == 1:
        print(f"Epoch {epoch:02d}: Loss={total_loss/len(train_ds):.4f}, Val Se={se:.2f}%, +P={pp:.2f}%, FPR={fpr:.2f}%, F1={f1:.2f}%")

print("Threshold search on validation...")
th_candidates = np.linspace(0.01, 0.99, 99)
best_th = 0.5
best_th_se = 0.0
best_th_pp = 0.0
best_th_fpr = 0.0
for th in th_candidates:
    p = (val_probs >= th).astype(int)
    tp = np.sum((p == 1) & (val_targets == 1))
    fn = np.sum((p == 0) & (val_targets == 1))
    fp = np.sum((p == 1) & (val_targets == 0))
    tn = np.sum((p == 0) & (val_targets == 0))
    c_se = (tp / (tp + fn) * 100) if (tp + fn) > 0 else 0
    c_pp = (tp / (tp + fp) * 100) if (tp + fp) > 0 else 0
    c_fpr = (fp / (tn + fp) * 100) if (tn + fp) > 0 else 0
    if c_pp >= 90.0 and c_fpr <= 1.0:
        if c_se > best_th_se:
            best_th_se = c_se
            best_th_pp = c_pp
            best_th_fpr = c_fpr
            best_th = th

print(f"Best Threshold: {best_th:.3f} -> Val Se={best_th_se:.2f}%, +P={best_th_pp:.2f}%, FPR={best_th_fpr:.2f}%")

# Test eval
model.eval()
test_probs = []
test_targets = []
with torch.no_grad():
    for x_w, x_f, y in test_loader:
        x_w, x_f = x_w.to(device), x_f.to(device)
        logits = model(x_w, x_f)
        probs = torch.softmax(logits, dim=1)[:, 1].cpu().numpy()
        test_probs.extend(probs)
        test_targets.extend(y.numpy())

test_probs = np.array(test_probs)
test_targets = np.array(test_targets)
p = (test_probs >= best_th).astype(int)
tp = np.sum((p == 1) & (test_targets == 1))
fn = np.sum((p == 0) & (test_targets == 1))
fp = np.sum((p == 1) & (test_targets == 0))
tn = np.sum((p == 0) & (test_targets == 0))
t_se = (tp / (tp + fn) * 100) if (tp + fn) > 0 else 0
t_pp = (tp / (tp + fp) * 100) if (tp + fp) > 0 else 0
t_fpr = (fp / (tn + fp) * 100) if (tn + fp) > 0 else 0
print(f"Test Result @ th={best_th:.3f}: Se={t_se:.2f}%, +P={t_pp:.2f}%, FPR={t_fpr:.2f}% (TP={tp}, FN={fn}, FP={fp}, TN={tn})")
