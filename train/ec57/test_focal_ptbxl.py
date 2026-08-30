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

class FocalLoss(nn.Module):
    """Binary Focal Loss for severe class imbalance."""
    def __init__(self, alpha=0.85, gamma=2.0):
        super().__init__()
        self.alpha = alpha
        self.gamma = gamma

    def forward(self, logits, targets):
        # logits: [B, 2], targets: [B]
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
            gain = np.random.uniform(0.85, 1.15)
            wave = wave * gain
            # Jitter
            shift = np.random.randint(-3, 4)
            wave = np.roll(wave, shift)

        x_wave = torch.from_numpy(wave).unsqueeze(0).float()
        x_feat = torch.from_numpy(feat).float()
        y = torch.tensor(label, dtype=torch.long)
        return x_wave, x_feat, y

cache_dir = os.path.join(base_dir, "cache_ptbxl_beats_v1")
train_npz = np.load(os.path.join(cache_dir, "train_beats.npz"))
val_npz = np.load(os.path.join(cache_dir, "val_beats.npz"))
test_npz = np.load(os.path.join(cache_dir, "test_beats.npz"))

train_ds = PTBXLBeatDataset(train_npz["waveforms"], train_npz["features"], train_npz["labels"], is_training=True)
val_ds = PTBXLBeatDataset(val_npz["waveforms"], val_npz["features"], val_npz["labels"], is_training=False)
test_ds = PTBXLBeatDataset(test_npz["waveforms"], test_npz["features"], test_npz["labels"], is_training=False)

train_loader = DataLoader(train_ds, batch_size=512, shuffle=True)
val_loader = DataLoader(val_ds, batch_size=1024, shuffle=False)
test_loader = DataLoader(test_ds, batch_size=1024, shuffle=False)

device = torch.device("cuda:2" if torch.cuda.is_available() else "cpu")
model = TinyECGCNN_NV_MLP().to(device)

criterion = FocalLoss(alpha=0.88, gamma=2.0)
optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-4)
scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=60, eta_min=1e-5)

print("Starting Focal Loss training on GPU 2...")
for epoch in range(1, 61):
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

    if epoch % 10 == 0 or epoch == 1:
        model.eval()
        val_probs = []
        val_targets = []
        with torch.no_grad():
            for x_w, x_f, y in val_loader:
                x_w, x_f = x_w.to(device), x_f.to(device)
                probs = torch.softmax(model(x_w, x_f), dim=1)[:, 1].cpu().numpy()
                val_probs.extend(probs)
                val_targets.extend(y.numpy())
        val_probs = np.array(val_probs)
        val_targets = np.array(val_targets)
        p = (val_probs >= 0.5).astype(int)
        tp = np.sum((p == 1) & (val_targets == 1))
        fn = np.sum((p == 0) & (val_targets == 1))
        fp = np.sum((p == 1) & (val_targets == 0))
        tn = np.sum((p == 0) & (val_targets == 0))
        se = (tp / (tp + fn) * 100) if (tp + fn) > 0 else 0
        pp = (tp / (tp + fp) * 100) if (tp + fp) > 0 else 0
        fpr = (fp / (tn + fp) * 100) if (tn + fp) > 0 else 0
        f1 = (2 * se * pp) / (se + pp + 1e-8)
        print(f"Epoch {epoch:02d}: Loss={total_loss/len(train_ds):.5f}, Val Se={se:.2f}%, +P={pp:.2f}%, FPR={fpr:.2f}%, F1={f1:.2f}%")

# Test evaluation
model.eval()
test_probs = []
test_targets = []
with torch.no_grad():
    for x_w, x_f, y in test_loader:
        x_w, x_f = x_w.to(device), x_f.to(device)
        probs = torch.softmax(model(x_w, x_f), dim=1)[:, 1].cpu().numpy()
        test_probs.extend(probs)
        test_targets.extend(y.numpy())

test_probs = np.array(test_probs)
test_targets = np.array(test_targets)

print("\nDetailed Threshold Sweep on Test Split (Focal Loss + MLP Head):")
print("Thresh |   Se (%)  |   +P (%)  |  FPR (%)  |    F1 (%) |   TP  |   FN  |   FP  |    TN")
print("-------------------------------------------------------------------------------------")
for th in [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.85, 0.9, 0.95, 0.98, 0.99, 0.995]:
    p = (test_probs >= th).astype(int)
    tp = np.sum((p == 1) & (test_targets == 1))
    fn = np.sum((p == 0) & (test_targets == 1))
    fp = np.sum((p == 1) & (test_targets == 0))
    tn = np.sum((p == 0) & (test_targets == 0))
    c_se = (tp / (tp + fn) * 100) if (tp + fn) > 0 else 0
    c_pp = (tp / (tp + fp) * 100) if (tp + fp) > 0 else 0
    c_fpr = (fp / (tn + fp) * 100) if (tn + fp) > 0 else 0
    c_f1 = (2 * c_se * c_pp) / (c_se + c_pp + 1e-8)
    print(f" {th:5.3f} |  {c_se:7.2f}% |  {c_pp:7.2f}% |  {c_fpr:7.3f}% |  {c_f1:7.2f}% | {tp:5d} | {fn:5d} | {fp:5d} | {tn:6d}")
