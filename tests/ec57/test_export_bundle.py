"""Tests for RTL bundle export and core golden dataset generation."""

import unittest
import os
import json
import tempfile
import numpy as np
try:
    import torch
    from train.ec57.model_nv import TinyECGCNN_NV
    from train.ec57.integer_reference import create_integer_model_from_torch
    from train.ec57.export_rtl_bundle import export_rtl_bundle
    from tools.ec57.generate_golden import generate_core_golden
except ImportError:
    torch = None
    TinyECGCNN_NV = None
    create_integer_model_from_torch = None
    export_rtl_bundle = None
    generate_core_golden = None


class TestExportBundle(unittest.TestCase):
    """Verifies that model export produces all required binary memory bundles and golden vectors."""

    def setUp(self):
        if torch is None or export_rtl_bundle is None:
            self.skipTest("PyTorch / export_rtl_bundle not available")

        torch.manual_seed(100)
        self.torch_model = TinyECGCNN_NV()
        self.int_model = create_integer_model_from_torch(
            self.torch_model,
            calib_wave=torch.randn(10, 1, 160),
            calib_feat=torch.randn(10, 4)
        )

    def test_export_bundle_files_and_manifest(self):
        """Export must produce weights_int8.bin, bias_int32.bin, requant.json, model_layout.json, bundle_manifest.json."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            manifest = export_rtl_bundle(self.int_model, output_dir=tmp_dir)

            expected_files = [
                'weights_int8.bin',
                'bias_int32.bin',
                'requant.json',
                'model_layout.json',
                'bundle_manifest.json'
            ]
            for fname in expected_files:
                fpath = os.path.join(tmp_dir, fname)
                self.assertTrue(os.path.exists(fpath), f"Missing bundle file: {fname}")
                self.assertGreater(os.path.getsize(fpath), 0)

            self.assertIn('bundle_sha256', manifest)
            self.assertIn('files', manifest)

    def test_generate_core_golden(self):
        """Core golden generation produces all required intermediate integer layer activations."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            golden_path = os.path.join(tmp_dir, 'core_golden_test.npz')
            generate_core_golden(self.int_model, num_beats=16, output_path=golden_path, seed=42)

            self.assertTrue(os.path.exists(golden_path))
            with np.load(golden_path) as data:
                required_keys = ['input_wave', 'input_feat', 'pool1', 'pool2', 'conv3_act', 'gap', 'concat', 'logits', 'classes']
                for k in required_keys:
                    self.assertIn(k, data)
                    self.assertEqual(len(data[k]), 16)


if __name__ == '__main__':
    unittest.main()
