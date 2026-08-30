"""Tests for M2/M3 lightweight Non-VEB/VEB ECG model architecture, shape, and budget."""

import unittest

try:
    import torch
    import torch.nn as nn
    from train.ec57.model_nv import TinyECGCNN_NV, count_parameters, count_macs
except ImportError:
    torch = None
    nn = None
    TinyECGCNN_NV = None
    count_parameters = None
    count_macs = None


class TestModelBudget(unittest.TestCase):
    """Verifies that TinyECGCNN_NV strictly adheres to Section 1.3 budget and architecture."""

    def setUp(self):
        if torch is None or TinyECGCNN_NV is None:
            self.skipTest("PyTorch / TinyECGCNN_NV not implemented yet")
        self.model = TinyECGCNN_NV()

    def test_parameter_count_and_budget(self):
        """Model must have exactly 1,546 parameters with bias, and <= 2,048 max budget."""
        total_params = count_parameters(self.model)
        self.assertEqual(total_params, 1546, f"Expected exactly 1,546 parameters, got {total_params}")
        self.assertLessEqual(total_params, 2048, "Total parameters must not exceed 2,048")

        # Check per-layer parameter breakdown
        # Conv1: 1 * 8 * 7 + 8 = 64
        conv1_params = sum(p.numel() for p in self.model.conv1.parameters())
        self.assertEqual(conv1_params, 64)

        # Conv2: 8 * 16 * 5 + 16 = 656
        conv2_params = sum(p.numel() for p in self.model.conv2.parameters())
        self.assertEqual(conv2_params, 656)

        # Conv3: 16 * 16 * 3 + 16 = 784
        conv3_params = sum(p.numel() for p in self.model.conv3.parameters())
        self.assertEqual(conv3_params, 784)

        # Classifier: 20 * 2 + 2 = 42
        fc_params = sum(p.numel() for p in self.model.classifier.parameters())
        self.assertEqual(fc_params, 42)

    def test_mac_count(self):
        """Single beat inference MACs must be <= 100,000."""
        macs = count_macs(self.model, input_len=160)
        # Conv1: 1 * 8 * 7 * 160 = 8,960
        # Conv2: 8 * 16 * 5 * 80  = 51,200
        # Conv3: 16 * 16 * 3 * 40 = 30,720
        # Linear: 20 * 2 = 40
        # Total MACs = 8,960 + 51,200 + 30,720 + 40 = 90,920
        self.assertEqual(macs, 90920, f"Expected 90,920 MACs, got {macs}")
        self.assertLessEqual(macs, 100000, "MACs per beat must not exceed 100,000")

    def test_forward_shape(self):
        """Forward pass must accept [B, 1, 160] waveform and [B, 4] features, outputting [B, 2] logits."""
        batch_size = 8
        x_wave = torch.randn(batch_size, 1, 160)
        x_feat = torch.randn(batch_size, 4)

        out = self.model(x_wave, x_feat)
        self.assertEqual(out.shape, (batch_size, 2))

    def test_layerwise_activation_shapes(self):
        """Verify layer-by-layer intermediate activation tensor shapes."""
        x = torch.randn(2, 1, 160)
        f = torch.randn(2, 4)

        c1 = self.model.conv1(x)
        self.assertEqual(c1.shape, (2, 8, 160))

        a1 = self.model.act1(c1)
        p1 = self.model.pool1(a1)
        self.assertEqual(p1.shape, (2, 8, 80))

        c2 = self.model.conv2(p1)
        self.assertEqual(c2.shape, (2, 16, 80))

        a2 = self.model.act2(c2)
        p2 = self.model.pool2(a2)
        self.assertEqual(p2.shape, (2, 16, 40))

        c3 = self.model.conv3(p2)
        self.assertEqual(c3.shape, (2, 16, 40))

        a3 = self.model.act3(c3)
        gap = self.model.gap(a3).view(2, 16)
        self.assertEqual(gap.shape, (2, 16))

        concat = torch.cat([gap, f], dim=1)
        self.assertEqual(concat.shape, (2, 20))

        logits = self.model.classifier(concat)
        self.assertEqual(logits.shape, (2, 2))

    def test_no_forbidden_layers(self):
        """Ensure no BatchNorm, LayerNorm, LSTM, or Transformer modules are used."""
        for name, module in self.model.named_modules():
            self.assertNotIsInstance(module, (nn.BatchNorm1d, nn.BatchNorm2d, nn.LayerNorm, nn.RNNBase, nn.MultiheadAttention),
                                    f"Forbidden layer type found: {type(module)} in {name}")


if __name__ == '__main__':
    unittest.main()
