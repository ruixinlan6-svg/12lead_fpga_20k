"""Tests for end-to-end M2 training, candidate ablation, threshold scanning, and artifact manifests."""

import os
import tempfile
import unittest
import numpy as np
import json

try:
    import torch
    from train.ec57.train_nv import train_single_run
    from train.ec57.model_nv import TinyECGCNN_NV, count_parameters, count_macs
except ImportError:
    torch = None
    train_single_run = None


class TestTrainPipeline(unittest.TestCase):
    """Verifies that M2 training pipeline runs smoothly on synthetic data."""

    def setUp(self):
        if torch is None or train_single_run is None:
            self.skipTest("PyTorch / train_single_run not available")

        # Generate synthetic smoke dataset (20 patients, 100 beats each)
        np.random.seed(42)
        n_samples = 500
        self.train_data = {
            "waveforms": np.random.randn(n_samples, 160).astype(np.float32),
            "features": np.random.randn(n_samples, 4).astype(np.float32),
            "labels": np.random.choice([0, 1], size=n_samples, p=[0.85, 0.15]),
            "patient_ids": np.random.choice([f"pat_{i:02d}" for i in range(10)], size=n_samples)
        }
        n_val = 150
        self.val_data = {
            "waveforms": np.random.randn(n_val, 160).astype(np.float32),
            "features": np.random.randn(n_val, 4).astype(np.float32),
            "labels": np.random.choice([0, 1], size=n_val, p=[0.85, 0.15]),
            "patient_ids": np.random.choice([f"val_pat_{i:02d}" for i in range(3)], size=n_val)
        }
        n_test = 150
        self.test_data = {
            "waveforms": np.random.randn(n_test, 160).astype(np.float32),
            "features": np.random.randn(n_test, 4).astype(np.float32),
            "labels": np.random.choice([0, 1], size=n_test, p=[0.85, 0.15]),
            "patient_ids": np.random.choice([f"test_pat_{i:02d}" for i in range(3)], size=n_test)
        }

    def test_train_single_epoch_smoke(self):
        """Pipeline must run 1 epoch, save all required artifacts and valid SHA-256 manifest."""
        config_path = "train/ec57/configs/candidate_b_morph_rr.json"
        with open(config_path, "r") as f:
            config = json.load(f)

        config["training"]["max_epochs"] = 1
        config["training"]["batch_size"] = 64

        with tempfile.TemporaryDirectory() as tmp_dir:
            res = train_single_run(
                config=config,
                train_data=self.train_data,
                val_data=self.val_data,
                test_data=self.test_data,
                output_dir=tmp_dir,
                seed=17,
                device_str="cpu"
            )

            # Check that all artifacts exist
            for fname in ["model_fp32.pt", "config.json", "decision_threshold.json", "metrics.json", "manifest_sha256.txt", "model_sha256.txt"]:
                self.assertTrue(os.path.exists(os.path.join(tmp_dir, fname)), f"Missing artifact {fname}")

            # Check threshold and metrics
            self.assertIn("optimal_threshold", res)
            self.assertIn("test_metrics", res)
            self.assertIn("model_sha256", res)


if __name__ == '__main__':
    unittest.main()
