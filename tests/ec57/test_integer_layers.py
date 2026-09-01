"""Tests for pure integer reference model and intermediate layer evaluation."""

import unittest
import numpy as np
try:
    import torch
    from train.ec57.model_nv import TinyECGCNN_NV
    from train.ec57.integer_reference import IntegerTinyECGCNN_NV, create_integer_model_from_torch
except ImportError:
    torch = None
    TinyECGCNN_NV = None
    IntegerTinyECGCNN_NV = None
    create_integer_model_from_torch = None


class TestIntegerLayers(unittest.TestCase):
    """Verifies that pure integer inference functions correctly and matches structure."""

    def setUp(self):
        if torch is None or IntegerTinyECGCNN_NV is None:
            self.skipTest("PyTorch / integer_reference not available")

        # Create a torch model and convert it to integer reference
        torch.manual_seed(42)
        self.torch_model = TinyECGCNN_NV()
        self.torch_model.eval()

        # Calibration data for activation scales
        calib_wave = torch.randn(10, 1, 160)
        calib_feat = torch.randn(10, 4)

        self.int_model = create_integer_model_from_torch(self.torch_model, calib_wave, calib_feat)

    def test_layerwise_integer_shapes(self):
        """Integer layers must output exact integer types and shapes."""
        x_wave = np.random.randint(-128, 127, size=160, dtype=np.int8)
        x_feat = np.random.randint(-128, 127, size=4, dtype=np.int8)

        acts = self.int_model.forward_with_intermediates(x_wave, x_feat)

        # Layer 1: Conv1 + ReLU + MaxPool -> [8, 80] INT8
        self.assertEqual(acts['pool1'].shape, (8, 80))
        self.assertEqual(acts['pool1'].dtype, np.int8)

        # Layer 2: Conv2 + ReLU + MaxPool -> [16, 40] INT8
        self.assertEqual(acts['pool2'].shape, (16, 40))
        self.assertEqual(acts['pool2'].dtype, np.int8)

        # Layer 3: Conv3 + ReLU + GAP -> [16] INT8
        self.assertEqual(acts['gap'].shape, (16,))
        self.assertEqual(acts['gap'].dtype, np.int8)

        # Concat: [20] INT8
        self.assertEqual(acts['concat'].shape, (20,))
        self.assertEqual(acts['concat'].dtype, np.int8)

        # Logits: [2] INT32
        self.assertEqual(acts['logits'].shape, (2,))
        self.assertEqual(acts['logits'].dtype, np.int32)

    def test_deterministic_integer_reproducibility(self):
        """Repeated forward passes with same integer input must yield bit-exact identical outputs."""
        x_wave = np.random.randint(-128, 127, size=160, dtype=np.int8)
        x_feat = np.random.randint(-128, 127, size=4, dtype=np.int8)

        out1 = self.int_model.forward(x_wave, x_feat)
        out2 = self.int_model.forward(x_wave, x_feat)

        np.testing.assert_array_equal(out1, out2)

    def test_dilated_mlp_integer_shapes(self):
        """Verify winning 2.5KB dilated model (5 bins, 8 features, MLP 11) runs integer inference."""
        torch_model = TinyECGCNN_NV(temporal_pool_bins=5, num_features=8, mlp_hidden_dim=11, dilation=2)
        torch_model.eval()
        calib_wave = torch.randn(10, 1, 160)
        calib_feat = torch.randn(10, 8)

        int_model = create_integer_model_from_torch(torch_model, calib_wave, calib_feat)

        x_wave = np.random.randint(-128, 127, size=160, dtype=np.int8)
        x_feat = np.random.randint(-128, 127, size=8, dtype=np.int8)

        acts = int_model.forward_with_intermediates(x_wave, x_feat)

        self.assertEqual(acts['pool1'].shape, (8, 80))
        self.assertEqual(acts['pool2'].shape, (16, 40))
        self.assertEqual(acts['gap'].shape, (80,)) # 16 * 5 = 80
        self.assertEqual(acts['concat'].shape, (88,)) # 80 + 8 = 88
        self.assertEqual(acts['logits'].shape, (2,))
        self.assertEqual(acts['logits'].dtype, np.int32)


if __name__ == '__main__':
    unittest.main()
