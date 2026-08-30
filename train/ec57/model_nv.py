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
from typing import Tuple, Dict, Any


class TinyECGCNN_NV(nn.Module):
    """Frozen 1.6k parameter INT8-deployable ECG beat classifier."""

    def __init__(self):
        super().__init__()
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

        # Classifier: 20 -> 2
        self.classifier = nn.Linear(in_features=20, out_features=2, bias=True)

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
        h_gap = self.gap(h3).view(x_wave.size(0), 16)   # [B, 16]

        # Concat with 4 auxiliary features
        h_concat = torch.cat([h_gap, x_feat], dim=1)    # [B, 20]

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
        gap = self.gap(a3).view(x_wave.size(0), 16)
        activations['conv3'] = c3
        activations['act3'] = a3
        activations['gap'] = gap

        concat = torch.cat([gap, x_feat], dim=1)
        logits = self.classifier(concat)
        activations['concat'] = concat
        activations['logits'] = logits

        return activations


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
    mac_conv2 = 8 * 16 * 5 * l2
    mac_conv3 = 16 * 16 * 3 * l3
    mac_linear = 20 * 2
    return mac_conv1 + mac_conv2 + mac_conv3 + mac_linear
