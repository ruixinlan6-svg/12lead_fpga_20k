"""Pure integer reference model for TinyECGCNN_NV (Section 1.3 & 3.3).

Executes layer-by-layer bit-exact integer arithmetic with:
  - INT8 inputs and weights
  - INT32 accumulators and biases
  - Requantization with hardware-identical multiplier/shift & round-half-away-from-zero
  - INT32 output logits
"""

import math
import numpy as np
import torch
import torch.nn as nn
from typing import Tuple, Dict, Any, Union
from train.ec57.quantize_int8 import (
    decompose_multiplier_shift,
    requantize_integer,
    quantize_weights_per_channel,
    quantize_tensor_symmetric_int8
)
from train.ec57.beat_dataset import round_half_away_from_zero


class IntegerTinyECGCNN_NV:
    """Pure integer implementation of TinyECGCNN_NV for bit-exact hardware verification."""

    def __init__(
        self,
        conv1_w: np.ndarray,       # [8, 1, 7] int8
        conv1_bias: np.ndarray,    # [8] int32
        conv1_mult: np.ndarray,    # [8] int32
        conv1_shift: np.ndarray,   # [8] int32
        conv2_w: np.ndarray,       # [16, 8, 5] int8
        conv2_bias: np.ndarray,    # [16] int32
        conv2_mult: np.ndarray,    # [16] int32
        conv2_shift: np.ndarray,   # [16] int32
        conv3_w: np.ndarray,       # [16, 16, 3] int8
        conv3_bias: np.ndarray,    # [16] int32
        conv3_mult: np.ndarray,    # [16] int32
        conv3_shift: np.ndarray,   # [16] int32
        fc_w: np.ndarray,          # [2, 20] int8
        fc_bias: np.ndarray        # [2] int32
    ):
        self.conv1_w = np.asarray(conv1_w, dtype=np.int8)
        self.conv1_bias = np.asarray(conv1_bias, dtype=np.int32)
        self.conv1_mult = np.asarray(conv1_mult, dtype=np.int32)
        self.conv1_shift = np.asarray(conv1_shift, dtype=np.int32)

        self.conv2_w = np.asarray(conv2_w, dtype=np.int8)
        self.conv2_bias = np.asarray(conv2_bias, dtype=np.int32)
        self.conv2_mult = np.asarray(conv2_mult, dtype=np.int32)
        self.conv2_shift = np.asarray(conv2_shift, dtype=np.int32)

        self.conv3_w = np.asarray(conv3_w, dtype=np.int8)
        self.conv3_bias = np.asarray(conv3_bias, dtype=np.int32)
        self.conv3_mult = np.asarray(conv3_mult, dtype=np.int32)
        self.conv3_shift = np.asarray(conv3_shift, dtype=np.int32)

        self.fc_w = np.asarray(fc_w, dtype=np.int8)
        self.fc_bias = np.asarray(fc_bias, dtype=np.int32)

    def eval_conv1(self, x_wave: np.ndarray) -> np.ndarray:
        """Conv1: [160] -> [8, 160] -> ReLU -> MaxPool2 -> [8, 80] INT8."""
        # Pad 3 on both sides with 0
        padded = np.pad(x_wave.astype(np.int32), (3, 3), mode='constant', constant_values=0)
        out_conv = np.zeros((8, 160), dtype=np.int8)

        for oc in range(8):
            w = self.conv1_w[oc, 0].astype(np.int32)
            b = int(self.conv1_bias[oc])
            mult = int(self.conv1_mult[oc])
            shift = int(self.conv1_shift[oc])

            for t in range(160):
                acc = b + int(np.sum(padded[t : t + 7] * w))
                out_conv[oc, t] = requantize_integer(acc, mult, shift, relu=True)

        # MaxPool1d(2)
        out_pool = np.zeros((8, 80), dtype=np.int8)
        for oc in range(8):
            for t in range(80):
                out_pool[oc, t] = max(out_conv[oc, 2 * t], out_conv[oc, 2 * t + 1])

        return out_pool

    def eval_conv2(self, h1: np.ndarray) -> np.ndarray:
        """Conv2: [8, 80] -> [16, 80] -> ReLU -> MaxPool2 -> [16, 40] INT8."""
        # Pad 2 on length with 0
        padded = np.pad(h1.astype(np.int32), ((0, 0), (2, 2)), mode='constant', constant_values=0)
        out_conv = np.zeros((16, 80), dtype=np.int8)

        for oc in range(16):
            w = self.conv2_w[oc].astype(np.int32)  # [8, 5]
            b = int(self.conv2_bias[oc])
            mult = int(self.conv2_mult[oc])
            shift = int(self.conv2_shift[oc])

            for t in range(80):
                window = padded[:, t : t + 5]  # [8, 5]
                acc = b + int(np.sum(window * w))
                out_conv[oc, t] = requantize_integer(acc, mult, shift, relu=True)

        # MaxPool1d(2)
        out_pool = np.zeros((16, 40), dtype=np.int8)
        for oc in range(16):
            for t in range(40):
                out_pool[oc, t] = max(out_conv[oc, 2 * t], out_conv[oc, 2 * t + 1])

        return out_pool

    def eval_conv3(self, h2: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """Conv3: [16, 40] -> [16, 40] -> ReLU -> GAP -> [16] INT8."""
        # Pad 1 on length with 0
        padded = np.pad(h2.astype(np.int32), ((0, 0), (1, 1)), mode='constant', constant_values=0)
        out_conv = np.zeros((16, 40), dtype=np.int8)

        for oc in range(16):
            w = self.conv3_w[oc].astype(np.int32)  # [16, 3]
            b = int(self.conv3_bias[oc])
            mult = int(self.conv3_mult[oc])
            shift = int(self.conv3_shift[oc])

            for t in range(40):
                window = padded[:, t : t + 3]  # [16, 3]
                acc = b + int(np.sum(window * w))
                out_conv[oc, t] = requantize_integer(acc, mult, shift, relu=True)

        # GAP: integer average over 40 elements with round-half-away-from-zero
        out_gap = np.zeros(16, dtype=np.int8)
        for oc in range(16):
            total_sum = int(np.sum(out_conv[oc].astype(np.int32)))
            # GAP average = (sum + 20) >> ... or round(sum / 40.0)
            avg = round_half_away_from_zero(total_sum / 40.0)
            out_gap[oc] = int(np.clip(avg, -128, 127))

        return out_conv, out_gap

    def eval_classifier(self, concat_feat: np.ndarray) -> np.ndarray:
        """Linear: [20] INT8 -> [2] INT32 logits."""
        logits = np.zeros(2, dtype=np.int32)
        x = concat_feat.astype(np.int32)

        for c in range(2):
            w = self.fc_w[c].astype(np.int32)
            b = int(self.fc_bias[c])
            logits[c] = b + int(np.sum(x * w))

        return logits

    def forward(self, x_wave: np.ndarray, x_feat: np.ndarray) -> np.ndarray:
        """Evaluates single beat and returns INT32 logits."""
        p1 = self.eval_conv1(x_wave)
        p2 = self.eval_conv2(p1)
        _, gap = self.eval_conv3(p2)
        concat = np.concatenate([gap, x_feat])
        logits = self.eval_classifier(concat)
        return logits

    def forward_with_intermediates(self, x_wave: np.ndarray, x_feat: np.ndarray) -> Dict[str, np.ndarray]:
        """Evaluates single beat and returns all intermediate activation maps for RTL comparison."""
        p1 = self.eval_conv1(x_wave)
        p2 = self.eval_conv2(p1)
        c3, gap = self.eval_conv3(p2)
        concat = np.concatenate([gap, x_feat])
        logits = self.eval_classifier(concat)

        return {
            'input_wave': np.asarray(x_wave, dtype=np.int8),
            'input_feat': np.asarray(x_feat, dtype=np.int8),
            'pool1': p1,
            'pool2': p2,
            'conv3_act': c3,
            'gap': gap,
            'concat': concat,
            'logits': logits
        }


def create_integer_model_from_torch(
    torch_model: nn.Module,
    calib_wave: torch.Tensor,
    calib_feat: torch.Tensor
) -> IntegerTinyECGCNN_NV:
    """Calibrates and converts a PyTorch TinyECGCNN_NV model into an IntegerTinyECGCNN_NV reference."""
    torch_model.eval()
    with torch.no_grad():
        acts = torch_model.extract_layer_activations(calib_wave, calib_feat)

    # 1. Activation scales
    s_in = float(np.max(np.abs(acts['input_wave'].numpy()))) / 127.0 if float(np.max(np.abs(acts['input_wave'].numpy()))) > 0 else 1.0/127.0
    s_a1 = float(np.max(np.abs(acts['act1'].numpy()))) / 127.0 if float(np.max(np.abs(acts['act1'].numpy()))) > 0 else 1.0/127.0
    s_a2 = float(np.max(np.abs(acts['act2'].numpy()))) / 127.0 if float(np.max(np.abs(acts['act2'].numpy()))) > 0 else 1.0/127.0
    s_a3 = float(np.max(np.abs(acts['act3'].numpy()))) / 127.0 if float(np.max(np.abs(acts['act3'].numpy()))) > 0 else 1.0/127.0
    s_feat = float(np.max(np.abs(acts['input_feat'].numpy()))) / 127.0 if float(np.max(np.abs(acts['input_feat'].numpy()))) > 0 else 1.0/127.0

    # 2. Conv1 weights and biases
    w1_fp = torch_model.conv1.weight.detach().numpy()  # [8, 1, 7]
    b1_fp = torch_model.conv1.bias.detach().numpy()    # [8]
    w1_int8, s_w1 = quantize_weights_per_channel(w1_fp)

    b1_int32 = np.zeros(8, dtype=np.int32)
    m1 = np.zeros(8, dtype=np.int32)
    shift1 = np.zeros(8, dtype=np.int32)
    for oc in range(8):
        b1_int32[oc] = round_half_away_from_zero(b1_fp[oc] / (s_in * s_w1[oc]))
        real_scale = (s_in * s_w1[oc]) / s_a1
        m1[oc], shift1[oc] = decompose_multiplier_shift(real_scale)

    # 3. Conv2 weights and biases
    w2_fp = torch_model.conv2.weight.detach().numpy()  # [16, 8, 5]
    b2_fp = torch_model.conv2.bias.detach().numpy()    # [16]
    w2_int8, s_w2 = quantize_weights_per_channel(w2_fp)

    b2_int32 = np.zeros(16, dtype=np.int32)
    m2 = np.zeros(16, dtype=np.int32)
    shift2 = np.zeros(16, dtype=np.int32)
    for oc in range(16):
        b2_int32[oc] = round_half_away_from_zero(b2_fp[oc] / (s_a1 * s_w2[oc]))
        real_scale = (s_a1 * s_w2[oc]) / s_a2
        m2[oc], shift2[oc] = decompose_multiplier_shift(real_scale)

    # 4. Conv3 weights and biases
    w3_fp = torch_model.conv3.weight.detach().numpy()  # [16, 16, 3]
    b3_fp = torch_model.conv3.bias.detach().numpy()    # [16]
    w3_int8, s_w3 = quantize_weights_per_channel(w3_fp)

    b3_int32 = np.zeros(16, dtype=np.int32)
    m3 = np.zeros(16, dtype=np.int32)
    shift3 = np.zeros(16, dtype=np.int32)
    for oc in range(16):
        b3_int32[oc] = round_half_away_from_zero(b3_fp[oc] / (s_a2 * s_w3[oc]))
        real_scale = (s_a2 * s_w3[oc]) / s_a3
        m3[oc], shift3[oc] = decompose_multiplier_shift(real_scale)

    # 5. Classifier weights and biases
    fc_w_fp = torch_model.classifier.weight.detach().numpy()  # [2, 20]
    fc_b_fp = torch_model.classifier.bias.detach().numpy()    # [2]

    # GAP output activation scale is s_a3; scalar feature scale is s_feat
    s_concat = np.concatenate([np.full(16, s_a3), np.full(4, s_feat)])
    fc_w_int8 = np.zeros((2, 20), dtype=np.int8)
    fc_b_int32 = np.zeros(2, dtype=np.int32)

    # Per-channel classifier quantization
    for oc in range(2):
        w_ch = fc_w_fp[oc]
        max_w = float(np.max(np.abs(w_ch)))
        s_fc_w = max_w / 127.0 if max_w > 0 else 1.0/127.0
        fc_w_int8[oc] = np.clip(round_half_away_from_zero(w_ch / s_fc_w), -128, 127)
        # Scale for input elements
        avg_in_scale = float(np.mean(s_concat))
        fc_b_int32[oc] = round_half_away_from_zero(fc_b_fp[oc] / (avg_in_scale * s_fc_w))

    return IntegerTinyECGCNN_NV(
        conv1_w=w1_int8,
        conv1_bias=b1_int32,
        conv1_mult=m1,
        conv1_shift=shift1,
        conv2_w=w2_int8,
        conv2_bias=b2_int32,
        conv2_mult=m2,
        conv2_shift=shift2,
        conv3_w=w3_int8,
        conv3_bias=b3_int32,
        conv3_mult=m3,
        conv3_shift=shift3,
        fc_w=fc_w_int8,
        fc_bias=fc_b_int32
    )
