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

from train.ec57.resource_budget import (
    MODEL_PACKAGE_CONTAINER_OVERHEAD_RESERVE_BYTES,
)


class TinyECGCNN_NV(nn.Module):
    """Frozen 1.6k parameter INT8-deployable ECG beat classifier."""

    def __init__(
        self,
        temporal_pool_bins: int = 1,
        num_features: int = 4,
        mlp_hidden_dim: int = 0,
        dilation: int = 1,
        use_bilinear_gating: bool = False,
    ):
        super().__init__()
        if not isinstance(temporal_pool_bins, int) or temporal_pool_bins <= 0:
            raise ValueError("temporal_pool_bins must be a positive integer")
        if 40 % temporal_pool_bins != 0:
            raise ValueError("temporal_pool_bins must divide the final temporal length 40")
        if not isinstance(num_features, int) or num_features <= 0:
            raise ValueError("num_features must be a positive integer")
        if not isinstance(mlp_hidden_dim, int) or mlp_hidden_dim < 0:
            raise ValueError("mlp_hidden_dim must be a non-negative integer")
        if dilation not in {1, 2}:
            raise ValueError(f"dilation must be 1 or 2, got {dilation}")
        self.temporal_pool_bins = temporal_pool_bins
        self.num_features = num_features
        self.mlp_hidden_dim = mlp_hidden_dim
        self.dilation = dilation
        self.use_bilinear_gating = use_bilinear_gating

        if use_bilinear_gating and num_features >= 3:
            self.gate_linear = nn.Linear(2, 1, bias=True)
        else:
            self.gate_linear = None

        # Conv Layer 1: 1 -> 8 (k=7, p=3, s=1)
        self.conv1 = nn.Conv1d(in_channels=1, out_channels=8, kernel_size=7, padding=3, bias=True)
        self.act1 = nn.ReLU()
        self.pool1 = nn.MaxPool1d(kernel_size=2, stride=2)

        # Conv Layer 2: 8 -> 16 (k=5, s=1)
        # If dilation=2, effective kernel=9, padding=4 preserves length
        p2 = 4 if dilation == 2 else 2
        self.conv2 = nn.Conv1d(in_channels=8, out_channels=16, kernel_size=5, padding=p2, dilation=dilation, bias=True)
        self.act2 = nn.ReLU()
        self.pool2 = nn.MaxPool1d(kernel_size=2, stride=2)

        # Conv Layer 3: 16 -> 16 (k=3, s=1)
        # If dilation=2, effective kernel=5, padding=2 preserves length
        p3 = 2 if dilation == 2 else 1
        self.conv3 = nn.Conv1d(in_channels=16, out_channels=16, kernel_size=3, padding=p3, dilation=dilation, bias=True)
        self.act3 = nn.ReLU()
        self.gap = nn.AdaptiveAvgPool1d(1)

        in_dim = 16 * self.temporal_pool_bins + num_features
        if mlp_hidden_dim > 0:
            self.classifier = nn.Sequential(
                nn.Linear(in_dim, mlp_hidden_dim, bias=True),
                nn.ReLU(),
                nn.Linear(mlp_hidden_dim, 2, bias=True),
            )
        else:
            self.classifier = nn.Linear(
                in_features=in_dim,
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
        if x_feat.ndim != 2 or x_feat.shape[1] != self.num_features:
            raise ValueError(f"x_feat must have shape [B,{self.num_features}]")

        # Layer 1
        h1 = self.pool1(self.act1(self.conv1(x_wave)))  # [B, 8, 80]

        # Layer 2
        h2 = self.pool2(self.act2(self.conv2(h1)))      # [B, 16, 40]

        # Layer 3
        h3 = self.act3(self.conv3(h2))                  # [B, 16, 40]
        h_gap = self.temporal_pool(h3)                   # [B, 16 * bins]

        if self.gate_linear is not None:
            # Gating factor from post_rr (idx 1) and comp_ratio (idx 2)
            gate = torch.sigmoid(self.gate_linear(x_feat[:, [1, 2]]))
            h_gap = h_gap * gate

        # Concat with auxiliary features
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


class DualBranchECGCNN_NV(nn.Module):
    """Dual-branch architecture balancing morphology CNN and physiological timing representations."""

    def __init__(
        self,
        temporal_pool_bins: int = 5,
        num_features: int = 8,
        morph_emb_dim: int = 24,
        timing_emb_dim: int = 24,
        dilation: int = 2,
    ):
        super().__init__()
        if not isinstance(temporal_pool_bins, int) or temporal_pool_bins <= 0:
            raise ValueError("temporal_pool_bins must be a positive integer")
        if 40 % temporal_pool_bins != 0:
            raise ValueError("temporal_pool_bins must divide 40")
        self.temporal_pool_bins = temporal_pool_bins
        self.num_features = num_features
        self.dilation = dilation
        self.morph_emb_dim = morph_emb_dim
        self.timing_emb_dim = timing_emb_dim

        # Morphology Branch (1D-CNN)
        self.conv1 = nn.Conv1d(1, 8, kernel_size=7, padding=3, bias=True)
        self.act1 = nn.ReLU()
        self.pool1 = nn.MaxPool1d(2, 2)

        p2 = 4 if dilation == 2 else 2
        self.conv2 = nn.Conv1d(8, 16, kernel_size=5, padding=p2, dilation=dilation, bias=True)
        self.act2 = nn.ReLU()
        self.pool2 = nn.MaxPool1d(2, 2)

        p3 = 2 if dilation == 2 else 1
        self.conv3 = nn.Conv1d(16, 16, kernel_size=3, padding=p3, dilation=dilation, bias=True)
        self.act3 = nn.ReLU()

        in_morph = 16 * temporal_pool_bins
        self.morph_proj = nn.Sequential(
            nn.Linear(in_morph, morph_emb_dim, bias=True),
            nn.ReLU(),
        )

        # Timing Branch (MLP on 8 features)
        self.timing_proj = nn.Sequential(
            nn.Linear(num_features, timing_emb_dim, bias=True),
            nn.ReLU(),
        )

        # Fusion & Classification Head
        fusion_dim = morph_emb_dim * 2 + timing_emb_dim
        self.classifier = nn.Sequential(
            nn.Linear(fusion_dim, 32, bias=True),
            nn.ReLU(),
            nn.Linear(32, 2, bias=True),
        )

    def temporal_pool(self, activation: torch.Tensor) -> torch.Tensor:
        bin_size = 40 // self.temporal_pool_bins
        pooled = F.avg_pool1d(activation, kernel_size=bin_size, stride=bin_size)
        return pooled.transpose(1, 2).contiguous().view(activation.size(0), -1)

    def forward(self, x_wave: torch.Tensor, x_feat: torch.Tensor) -> torch.Tensor:
        if x_wave.ndim == 2:
            x_wave = x_wave.unsqueeze(1)
        if x_feat.ndim != 2 or x_feat.shape[1] != self.num_features:
            raise ValueError(f"x_feat must have shape [B,{self.num_features}]")

        h1 = self.pool1(self.act1(self.conv1(x_wave)))
        h2 = self.pool2(self.act2(self.conv2(h1)))
        h3 = self.act3(self.conv3(h2))
        h_gap = self.temporal_pool(h3)

        e_morph = self.morph_proj(h_gap)
        e_timing = self.timing_proj(x_feat)

        gated_morph = e_morph * torch.sigmoid(e_timing)
        h_fused = torch.cat([gated_morph, e_morph, e_timing], dim=1)
        logits = self.classifier(h_fused)
        return logits


class TinyECGCNN_NV_Depthwise(nn.Module):
    """Depthwise-separable morphology encoder within the frozen QN88 budget."""

    def __init__(self, temporal_pool_bins: int = 5, num_features: int = 4):
        super().__init__()
        if not isinstance(temporal_pool_bins, int) or temporal_pool_bins <= 0:
            raise ValueError("temporal_pool_bins must be a positive integer")
        if 40 % temporal_pool_bins != 0:
            raise ValueError("temporal_pool_bins must divide the final temporal length 40")
        if not isinstance(num_features, int) or num_features <= 0:
            raise ValueError("num_features must be a positive integer")
        self.temporal_pool_bins = temporal_pool_bins
        self.num_features = num_features
        self.conv1 = nn.Conv1d(1, 8, kernel_size=7, padding=3, bias=True)
        self.pool1 = nn.MaxPool1d(2, 2)
        self.dw2 = nn.Conv1d(8, 8, kernel_size=5, padding=2, groups=8, bias=True)
        self.pw2 = nn.Conv1d(8, 24, kernel_size=1, bias=True)
        self.pool2 = nn.MaxPool1d(2, 2)
        self.dw3 = nn.Conv1d(24, 24, kernel_size=7, padding=3, groups=24, bias=True)
        self.pw3 = nn.Conv1d(24, 32, kernel_size=1, bias=True)
        self.classifier = nn.Linear(32 * temporal_pool_bins + num_features, 2, bias=True)

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


class MediumECGCNN_NV(nn.Module):
    """
    Historical oversized Medium-scale 1D CNN diagnostic model.
    Architecture:
      Conv1: 1 -> 32 (k=7, p=3, s=1) -> MaxPool(2) (Length 80)
      Conv2: 32 -> 64 (k=5, p=4, d=2, s=1) -> MaxPool(2) (Length 40)
      Conv3: 64 -> 64 (k=3, p=2, d=2, s=1) (Length 40)
      Conv4: 64 -> 64 (k=3, p=1, s=1) (Length 40)
      TemporalPool: 5 bins -> 320 morph features
      Classifier: Linear(328, mlp_hidden_dim) -> ReLU -> Linear(mlp_hidden_dim, 2)
    """

    def __init__(
        self,
        temporal_pool_bins: int = 5,
        num_features: int = 8,
        mlp_hidden_dim: int = 48,
        dilation: int = 2,
    ):
        super().__init__()
        if not isinstance(temporal_pool_bins, int) or temporal_pool_bins <= 0:
            raise ValueError("temporal_pool_bins must be a positive integer")
        if 40 % temporal_pool_bins != 0:
            raise ValueError("temporal_pool_bins must divide the final temporal length 40")
        if not isinstance(num_features, int) or num_features <= 0:
            raise ValueError("num_features must be a positive integer")
        if not isinstance(mlp_hidden_dim, int) or mlp_hidden_dim <= 0:
            raise ValueError("mlp_hidden_dim must be a positive integer")
        if dilation not in {1, 2}:
            raise ValueError(f"dilation must be 1 or 2, got {dilation}")

        self.temporal_pool_bins = temporal_pool_bins
        self.num_features = num_features
        self.mlp_hidden_dim = mlp_hidden_dim
        self.dilation = dilation

        # Layer 1: 1 -> 32
        self.conv1 = nn.Conv1d(1, 32, kernel_size=7, padding=3, bias=True)
        self.act1 = nn.ReLU()
        self.pool1 = nn.MaxPool1d(kernel_size=2, stride=2)

        # Layer 2: 32 -> 64
        p2 = 4 if dilation == 2 else 2
        self.conv2 = nn.Conv1d(32, 64, kernel_size=5, padding=p2, dilation=dilation, bias=True)
        self.act2 = nn.ReLU()
        self.pool2 = nn.MaxPool1d(kernel_size=2, stride=2)

        # Layer 3: 64 -> 64
        p3 = 2 if dilation == 2 else 1
        self.conv3 = nn.Conv1d(64, 64, kernel_size=3, padding=p3, dilation=dilation, bias=True)
        self.act3 = nn.ReLU()

        # Layer 4: 64 -> 64
        self.conv4 = nn.Conv1d(64, 64, kernel_size=3, padding=1, bias=True)
        self.act4 = nn.ReLU()

        in_dim = 64 * self.temporal_pool_bins + num_features
        self.classifier = nn.Sequential(
            nn.Linear(in_dim, mlp_hidden_dim, bias=True),
            nn.ReLU(),
            nn.Linear(mlp_hidden_dim, 2, bias=True),
        )

    def temporal_pool(self, activation: torch.Tensor) -> torch.Tensor:
        if activation.ndim != 3 or activation.shape[1:] != (64, 40):
            raise ValueError("temporal_pool expects activation shape [B, 64, 40]")
        bin_size = 40 // self.temporal_pool_bins
        pooled = F.avg_pool1d(activation, kernel_size=bin_size, stride=bin_size)
        return pooled.transpose(1, 2).contiguous().view(activation.size(0), -1)

    def forward(self, x_wave: torch.Tensor, x_feat: torch.Tensor) -> torch.Tensor:
        if x_wave.ndim == 2:
            x_wave = x_wave.unsqueeze(1)
        if x_feat.ndim != 2 or x_feat.shape[1] != self.num_features:
            raise ValueError(f"x_feat must have shape [B,{self.num_features}]")

        h1 = self.pool1(self.act1(self.conv1(x_wave)))
        h2 = self.pool2(self.act2(self.conv2(h1)))
        h3 = self.act3(self.conv3(h2))
        h4 = self.act4(self.conv4(h3))
        h_pool = self.temporal_pool(h4)
        h_concat = torch.cat([h_pool, x_feat], dim=1)
        return self.classifier(h_concat)


def count_parameters(model: nn.Module) -> int:
    """Returns the total number of trainable parameters in the model."""
    return sum(p.numel() for p in model.parameters() if p.requires_grad)


def estimate_int8_parameter_payload_bytes(model: nn.Module) -> int:
    """Estimate the quantized parameter payload size in bytes.

    The payload includes signed INT8 weights, signed INT32 biases, and
    one signed INT32 multiplier plus one signed INT32 shift per Conv/Linear
    output channel. Container headers, alignment, and checksums are accounted
    for separately through the frozen container-overhead reserve.
    """
    weight_bytes = sum(
        parameter.numel()
        for name, parameter in model.named_parameters()
        if not name.endswith("bias")
    )
    bias_bytes = 4 * sum(
        parameter.numel()
        for name, parameter in model.named_parameters()
        if name.endswith("bias")
    )
    output_channels = sum(
        module.out_channels if isinstance(module, nn.Conv1d) else module.out_features
        for module in model.modules()
        if isinstance(module, (nn.Conv1d, nn.Linear))
    )
    requant_bytes = output_channels * 2 * 4
    return int(weight_bytes + bias_bytes + requant_bytes)


def estimate_max_int8_activation_bytes(model: nn.Module, input_len: int = 160) -> int:
    """Measure the largest per-beat leaf-layer output assuming INT8 activations."""
    if not isinstance(input_len, int) or input_len <= 0:
        raise ValueError("input_len must be a positive integer")
    num_features = int(getattr(model, "num_features", 4))
    parameter = next(model.parameters(), None)
    device = parameter.device if parameter is not None else torch.device("cpu")
    dtype = parameter.dtype if parameter is not None else torch.float32
    activation_bytes = [input_len, num_features]
    hooks = []

    def record_output(_module, _inputs, output):
        if isinstance(output, torch.Tensor):
            activation_bytes.append(int(output[0].numel()))

    for module in model.modules():
        if module is not model and not any(module.children()):
            hooks.append(module.register_forward_hook(record_output))

    was_training = model.training
    try:
        model.eval()
        with torch.no_grad():
            model(
                torch.zeros((1, 1, input_len), device=device, dtype=dtype),
                torch.zeros((1, num_features), device=device, dtype=dtype),
            )
    finally:
        for hook in hooks:
            hook.remove()
        model.train(was_training)
    return max(activation_bytes)


def count_macs(model: nn.Module, input_len: int = 160) -> int:
    """Computes total multiply-accumulate (MAC) operations for one beat."""
    l1 = input_len
    l2 = l1 // 2
    l3 = l2 // 2

    if isinstance(model, MediumECGCNN_NV):
        mac_conv1 = 1 * 32 * 7 * l1
        mac_conv2 = 32 * 64 * 5 * l2
        mac_conv3 = 64 * 64 * 3 * l3
        mac_conv4 = 64 * 64 * 3 * l3
        mac_conv = mac_conv1 + mac_conv2 + mac_conv3 + mac_conv4
    elif isinstance(model, TinyECGCNN_NV_Depthwise):
        mac_conv1 = 1 * 8 * 7 * l1
        mac_conv2 = (8 * 5 * l2) + (8 * 24 * l2)
        mac_conv3 = (24 * 7 * l3) + (24 * 32 * l3)
        mac_conv = mac_conv1 + mac_conv2 + mac_conv3
    else:
        mac_conv1 = 1 * 8 * 7 * l1
        mac_conv2 = 8 * 16 * 5 * l2
        mac_conv3 = 16 * 16 * 3 * l3
        mac_conv = mac_conv1 + mac_conv2 + mac_conv3

    if isinstance(model.classifier, nn.Linear):
        mac_linear = model.classifier.in_features * model.classifier.out_features
    elif isinstance(model.classifier, nn.Sequential):
        mac_linear = sum(
            m.in_features * m.out_features for m in model.classifier if isinstance(m, nn.Linear)
        )
    else:
        mac_linear = 0

    mac_auxiliary = 0
    if isinstance(model, DualBranchECGCNN_NV):
        mac_auxiliary += sum(
            module.in_features * module.out_features
            for branch in (model.morph_proj, model.timing_proj)
            for module in branch
            if isinstance(module, nn.Linear)
        )
    gate_linear = getattr(model, "gate_linear", None)
    if isinstance(gate_linear, nn.Linear):
        mac_auxiliary += gate_linear.in_features * gate_linear.out_features

    return mac_conv + mac_linear + mac_auxiliary


def estimate_model_deployment_resources(model: nn.Module, input_len: int = 160) -> Dict[str, int]:
    """Return the frozen deployment package, MAC, and peak-activation estimates."""
    parameter_payload_bytes = estimate_int8_parameter_payload_bytes(model)
    return {
        "parameter_payload_bytes": parameter_payload_bytes,
        "package_overhead_reserve_bytes": MODEL_PACKAGE_CONTAINER_OVERHEAD_RESERVE_BYTES,
        "deployment_package_bytes": (
            parameter_payload_bytes + MODEL_PACKAGE_CONTAINER_OVERHEAD_RESERVE_BYTES
        ),
        "macs_per_beat": count_macs(model, input_len=input_len),
        "max_activation_bytes": estimate_max_int8_activation_bytes(model, input_len=input_len),
    }
