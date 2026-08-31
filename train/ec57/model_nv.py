"""TinyECGCNN_NV: Lightweight 1D CNN for single-lead beat classification (Non-VEB vs VEB).

Architecture (Frozen in Plan Section 1.3):
  Input: Waveform 1x160 (R peak at index 64)
  Layer 1: Conv1d(1, 8, kernel_size=7, padding=3), ReLU, MaxPool1d(2) -> 8x80
  Layer 2: Conv1d(8, 16, kernel_size=5, padding=2), ReLU, MaxPool1d(2) -> 16x40
  Layer 3: Conv1d(16, 16, kernel_size=3, padding=1), ReLU, AdaptiveAvgPool1d(1) -> 16
  Concat:  16 GAP features + 4 scalar auxiliary features -> 20
  Head:    Linear(20, 2) -> 2 logits [non_VEB, VEB]

Total Parameters: 1,546 (with bias)
Total MACs/beat: 90,920
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
from typing import Tuple, Dict, Any


class TinyECGCNN_NV(nn.Module):
    """Frozen 1.6k parameter INT8-deployable ECG beat classifier."""

    def __init__(self, temporal_pool_bins: int = 1):
        super().__init__()
        if not isinstance(temporal_pool_bins, int) or temporal_pool_bins <= 0:
            raise ValueError("temporal_pool_bins must be a positive integer")
        if 40 % temporal_pool_bins != 0:
            raise ValueError("temporal_pool_bins must divide the final temporal length 40")
        self.temporal_pool_bins = temporal_pool_bins
        # Conv Layer 1: 1 -> 8 (k=7, p=3, s=1)
        self.conv1 = nn.Conv1d(in_channels=1, out_channels=8, kernel_size=7, padding=3, bias=True)
        self.act1 = nn.ReLU()
        self.pool1 = nn.MaxPool1d(kernel_size=2, stride=2)

        # Conv Layer 2: 8 -> 16 (k=5, p=2, s=1)
        self.conv2 = nn.Conv1d(in_channels=8, out_channels=16, kernel_size=5, padding=2, bias=True)
        self.act2 = nn.ReLU()
        self.pool2 = nn.MaxPool1d(kernel_size=2, stride=2)

        # Conv Layer 3: 16 -> 16 (k=3, p=1, s=1)
        self.conv3 = nn.Conv1d(in_channels=16, out_channels=16, kernel_size=3, padding=1, bias=True)
        self.act3 = nn.ReLU()
        self.gap = nn.AdaptiveAvgPool1d(1)

        # Classifier: (16 * temporal_pool_bins + 4) -> 2
        self.classifier = nn.Linear(
            in_features=16 * self.temporal_pool_bins + 4,
            out_features=2,
            bias=True,
        )

    def temporal_pool(self, activation: torch.Tensor) -> torch.Tensor:
        """Pool fixed contiguous bins and flatten in temporal-bin-major order."""
        if activation.ndim != 3 or activation.shape[1:] != (16, 40):
            raise ValueError("temporal_pool expects activation shape [B, 16, 40]")
        bin_size = 40 // self.temporal_pool_bins
        pooled = F.avg_pool1d(activation, kernel_size=bin_size, stride=bin_size)
        return pooled.transpose(1, 2).contiguous().view(activation.size(0), -1)

    def forward(self, x_wave: torch.Tensor, x_feat: torch.Tensor) -> torch.Tensor:
        """
        Forward pass.
        Args:
            x_wave: Tensor of shape [B, 1, 160] (or [B, 160] auto-unsqueezed)
            x_feat: Tensor of shape [B, 4] (4 scalar auxiliary features)
        Returns:
            logits: Tensor of shape [B, 2] [logit_non_veb, logit_veb]
        """
        if x_wave.ndim == 2:
            x_wave = x_wave.unsqueeze(1)

        # Layer 1
        h1 = self.pool1(self.act1(self.conv1(x_wave)))  # [B, 8, 80]

        # Layer 2
        h2 = self.pool2(self.act2(self.conv2(h1)))      # [B, 16, 40]

        # Layer 3
        h3 = self.act3(self.conv3(h2))                  # [B, 16, 40]
        h_gap = self.temporal_pool(h3)                   # [B, 16 * bins]

        # Concat with 4 auxiliary features
        h_concat = torch.cat([h_gap, x_feat], dim=1)

        # Output logits
        logits = self.classifier(h_concat)              # [B, 2]
        return logits

    def extract_layer_activations(self, x_wave: torch.Tensor, x_feat: torch.Tensor) -> Dict[str, torch.Tensor]:
        """Extracts intermediate layer activations for golden generation and integer verification."""
        if x_wave.ndim == 2:
            x_wave = x_wave.unsqueeze(1)

        activations = {}
        activations['input_wave'] = x_wave
        activations['input_feat'] = x_feat

        c1 = self.conv1(x_wave)
        a1 = self.act1(c1)
        p1 = self.pool1(a1)
        activations['conv1'] = c1
        activations['act1'] = a1
        activations['pool1'] = p1

        c2 = self.conv2(p1)
        a2 = self.act2(c2)
        p2 = self.pool2(a2)
        activations['conv2'] = c2
        activations['act2'] = a2
        activations['pool2'] = p2

        c3 = self.conv3(p2)
        a3 = self.act3(c3)
        gap = self.temporal_pool(a3)
        activations['conv3'] = c3
        activations['act3'] = a3
        activations['gap'] = gap

        concat = torch.cat([gap, x_feat], dim=1)
        logits = self.classifier(concat)
        activations['concat'] = concat
        activations['logits'] = logits

        return activations


class TinyECGCNN_NV_Depthwise(nn.Module):
    """Depthwise-separable morphology encoder within the frozen QN88 budget."""

    def __init__(self, temporal_pool_bins: int = 5):
        super().__init__()
        if not isinstance(temporal_pool_bins, int) or temporal_pool_bins <= 0:
            raise ValueError("temporal_pool_bins must be a positive integer")
        if 40 % temporal_pool_bins != 0:
            raise ValueError("temporal_pool_bins must divide the final temporal length 40")
        self.temporal_pool_bins = temporal_pool_bins
        self.conv1 = nn.Conv1d(1, 8, kernel_size=7, padding=3, bias=True)
        self.pool1 = nn.MaxPool1d(2, 2)
        self.dw2 = nn.Conv1d(8, 8, kernel_size=5, padding=2, groups=8, bias=True)
        self.pw2 = nn.Conv1d(8, 24, kernel_size=1, bias=True)
        self.pool2 = nn.MaxPool1d(2, 2)
        self.dw3 = nn.Conv1d(24, 24, kernel_size=7, padding=3, groups=24, bias=True)
        self.pw3 = nn.Conv1d(24, 32, kernel_size=1, bias=True)
        self.classifier = nn.Linear(32 * temporal_pool_bins + 4, 2, bias=True)

    def temporal_pool(self, activation: torch.Tensor) -> torch.Tensor:
        if activation.ndim != 3 or activation.shape[1:] != (32, 40):
            raise ValueError("temporal_pool expects activation shape [B, 32, 40]")
        bin_size = 40 // self.temporal_pool_bins
        pooled = F.avg_pool1d(activation, kernel_size=bin_size, stride=bin_size)
        return pooled.transpose(1, 2).contiguous().view(activation.size(0), -1)

    def forward(self, x_wave: torch.Tensor, x_feat: torch.Tensor) -> torch.Tensor:
        if x_wave.ndim == 2:
            x_wave = x_wave.unsqueeze(1)
        h1 = self.pool1(F.relu(self.conv1(x_wave)))
        h2 = self.pool2(F.relu(self.pw2(self.dw2(h1))))
        h3 = F.relu(self.pw3(self.dw3(h2)))
        pooled = self.temporal_pool(h3)
        return self.classifier(torch.cat([pooled, x_feat], dim=1))

    def extract_layer_activations(self, x_wave: torch.Tensor, x_feat: torch.Tensor) -> Dict[str, torch.Tensor]:
        if x_wave.ndim == 2:
            x_wave = x_wave.unsqueeze(1)
        c1 = self.conv1(x_wave)
        p1 = self.pool1(F.relu(c1))
        d2 = self.dw2(p1)
        p2c = self.pw2(d2)
        p2 = self.pool2(F.relu(p2c))
        d3 = self.dw3(p2)
        p3c = self.pw3(d3)
        a3 = F.relu(p3c)
        pooled = self.temporal_pool(a3)
        concat = torch.cat([pooled, x_feat], dim=1)
        logits = self.classifier(concat)
        return {
            "input_wave": x_wave,
            "input_feat": x_feat,
            "conv1": c1,
            "pool1": p1,
            "dw2": d2,
            "pw2": p2c,
            "pool2": p2,
            "dw3": d3,
            "pw3": p3c,
            "act3": a3,
            "gap": pooled,
            "concat": concat,
            "logits": logits,
        }


def count_parameters(model: nn.Module) -> int:
    """Returns the total number of trainable parameters in the model."""
    return sum(p.numel() for p in model.parameters() if p.requires_grad)


def count_macs(model: nn.Module, input_len: int = 160) -> int:
    """
    Computes total multiply-accumulate (MAC) operations for one beat.
    
    Calculation:
      Conv1: 1 in_ch * 8 out_ch * 7 kernel * 160 out_len  = 8,960
      Conv2: 8 in_ch * 16 out_ch * 5 kernel * 80 out_len  = 51,200
      Conv3: 16 in_ch * 16 out_ch * 3 kernel * 40 out_len = 30,720
      Linear: 20 in_features * 2 out_features              = 40
      Total MACs                                           = 90,920
    """
    l1 = input_len
    l2 = l1 // 2
    l3 = l2 // 2

    mac_conv1 = 1 * 8 * 7 * l1
    if isinstance(model, TinyECGCNN_NV_Depthwise):
        mac_conv2 = (8 * 5 * l2) + (8 * 24 * l2)
        mac_conv3 = (24 * 7 * l3) + (24 * 32 * l3)
    else:
        mac_conv2 = 8 * 16 * 5 * l2
        mac_conv3 = 16 * 16 * 3 * l3
    mac_linear = model.classifier.in_features * 2
    return mac_conv1 + mac_conv2 + mac_conv3 + mac_linear
