"""Tests for end-to-end M2 training, candidate ablation, threshold scanning, and artifact manifests."""

import os
import tempfile
import unittest
import numpy as np
import json

try:
    import torch
except ImportError:
    torch = None

if torch is not None:
    from train.ec57.train_nv import (
        binary_average_precision,
        BeatDataset,
        ThresholdGateError,
        build_epoch_sample_indices,
        scan_optimal_threshold,
        train_single_run,
    )
    from train.ec57.model_nv import TinyECGCNN_NV, count_parameters, count_macs
    from train.ec57.train_nv_remote import apply_smoke_overrides, format_split_summary
else:
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

    def test_binary_average_precision_is_rank_and_tie_deterministic(self):
        self.assertEqual(binary_average_precision([1, 0, 1], [0.9, 0.2, 0.8]), 1.0)
        tied_forward = binary_average_precision([1, 0, 1, 0], [0.8, 0.8, 0.2, 0.2])
        tied_reverse = binary_average_precision([0, 1, 0, 1], [0.8, 0.8, 0.2, 0.2])
        self.assertAlmostEqual(tied_forward, tied_reverse)
        with self.assertRaisesRegex(ValueError, "at least one positive"):
            binary_average_precision([0, 0], [0.2, 0.1])

    def test_train_single_epoch_smoke(self):
        """Pipeline must run 1 epoch, save all required artifacts and valid SHA-256 manifest."""
        config_path = "train/ec57/configs/candidate_b_morph_rr.json"
        with open(config_path, "r") as f:
            config = json.load(f)

        config["training"]["max_epochs"] = 1
        config["training"]["batch_size"] = 64
        config["run_mode"] = "one_epoch_pipeline_smoke"
        config["threshold_search"]["min_veb_se"] = 0.0
        config["threshold_search"]["min_veb_plus_p"] = 0.0
        config["threshold_search"]["max_veb_fpr"] = 1.0

        with tempfile.TemporaryDirectory() as tmp_dir:
            res = train_single_run(
                config=config,
                train_data=self.train_data,
                val_data=self.val_data,
                test_data=None,
                normalization={"statistics_source": "synthetic train split only"},
                output_dir=tmp_dir,
                seed=17,
                device_str="cpu"
            )

            # Check that all artifacts exist
            for fname in ["model_fp32.pt", "config.json", "normalization.json", "decision_threshold.json", "metrics.json", "manifest_sha256.txt", "model_sha256.txt"]:
                self.assertTrue(os.path.exists(os.path.join(tmp_dir, fname)), f"Missing artifact {fname}")
            self.assertFalse(os.path.exists(os.path.join(tmp_dir, "vfp_vfn.json")))

            # Check threshold and metrics
            self.assertIn("optimal_threshold", res)
            self.assertNotIn("test_metrics", res)
            self.assertIn("model_sha256", res)
            self.assertEqual(res["status"], "smoke_only")
            self.assertFalse(res["checkpoint_freezable"])
            self.assertEqual(res["evaluation_scope"], "validation_only")
            with open(os.path.join(tmp_dir, "decision_threshold.json"), "r", encoding="utf-8") as handle:
                decision = json.load(handle)
            with open(os.path.join(tmp_dir, "metrics.json"), "r", encoding="utf-8") as handle:
                metrics = json.load(handle)
            self.assertEqual(decision["status"], "smoke_only")
            self.assertFalse(decision["checkpoint_freezable"])
            self.assertEqual(metrics["status"], "smoke_only")
            self.assertFalse(metrics["checkpoint_freezable"])
            self.assertEqual(metrics["evaluation_scope"], "validation_only")
            self.assertNotIn("test_metrics", metrics)

    def test_training_path_rejects_internal_test_data_and_evaluation(self):
        with open("train/ec57/configs/candidate_b_morph_rr.json", "r", encoding="utf-8") as handle:
            config = json.load(handle)
        with tempfile.TemporaryDirectory() as tmp_dir:
            with self.assertRaisesRegex(ValueError, "training path cannot receive or evaluate internal_test"):
                train_single_run(
                    config=config,
                    train_data=self.train_data,
                    val_data=self.val_data,
                    test_data=self.test_data,
                    normalization={"statistics_source": "synthetic train split only"},
                    output_dir=tmp_dir,
                    seed=17,
                    device_str="cpu",
                    evaluate_internal_test=False,
                )
            self.assertEqual(os.listdir(tmp_dir), [])

        with tempfile.TemporaryDirectory() as tmp_dir:
            with self.assertRaisesRegex(ValueError, "training path cannot receive or evaluate internal_test"):
                train_single_run(
                    config=config,
                    train_data=self.train_data,
                    val_data=self.val_data,
                    test_data=None,
                    normalization={"statistics_source": "synthetic train split only"},
                    output_dir=tmp_dir,
                    seed=17,
                    device_str="cpu",
                    evaluate_internal_test=True,
                )
            self.assertEqual(os.listdir(tmp_dir), [])

    def test_threshold_scan_fails_closed_when_no_threshold_meets_gate(self):
        model = TinyECGCNN_NV()
        dataset = BeatDataset(
            waveforms=self.val_data["waveforms"],
            features=self.val_data["features"],
            labels=self.val_data["labels"],
            patient_ids=self.val_data["patient_ids"],
            use_features=True,
            is_training=False,
        )
        loader = torch.utils.data.DataLoader(dataset, batch_size=64, shuffle=False)
        with self.assertRaisesRegex(ThresholdGateError, "no validation threshold") as raised:
            scan_optimal_threshold(
                model,
                loader,
                device=torch.device("cpu"),
                min_veb_se=0.0,
                min_veb_plus_p=1.01,
                max_veb_fpr=0.0,
            )
        self.assertEqual(raised.exception.summary["valid_threshold_count"], 0)
        self.assertEqual(len(raised.exception.summary["thresholds"]), 999)

    def test_rejected_candidate_still_writes_hash_complete_diagnostics(self):
        with open("train/ec57/configs/candidate_a_morph.json", "r", encoding="utf-8") as handle:
            config = json.load(handle)
        config["training"]["max_epochs"] = 1
        config["training"]["batch_size"] = 64
        config["threshold_search"]["min_veb_se"] = 0.0
        config["threshold_search"]["min_veb_plus_p"] = 1.01
        config["threshold_search"]["max_veb_fpr"] = 0.0
        with tempfile.TemporaryDirectory() as tmp_dir:
            with self.assertRaises(ThresholdGateError):
                train_single_run(
                    config=config,
                    train_data=self.train_data,
                    val_data=self.val_data,
                    test_data=None,
                    normalization={"statistics_source": "synthetic train split only"},
                    output_dir=tmp_dir,
                    seed=17,
                    device_str="cpu",
                    evaluate_internal_test=False,
                )
            for filename in (
                "model_fp32.pt",
                "model_sha256.txt",
                "config.json",
                "normalization.json",
                "metrics.json",
                "threshold_gate_failure.json",
                "manifest_sha256.txt",
            ):
                self.assertTrue(os.path.isfile(os.path.join(tmp_dir, filename)), filename)
            with open(os.path.join(tmp_dir, "metrics.json"), "r", encoding="utf-8") as handle:
                metrics = json.load(handle)
            self.assertEqual(metrics["status"], "rejected")
            self.assertFalse(metrics["checkpoint_freezable"])

    def test_candidate_selection_can_run_without_accessing_internal_test(self):
        with open("train/ec57/configs/candidate_a_morph.json", "r", encoding="utf-8") as handle:
            config = json.load(handle)
        config["training"]["max_epochs"] = 1
        config["training"]["batch_size"] = 64
        config["threshold_search"]["min_veb_se"] = 0.0
        config["threshold_search"]["min_veb_plus_p"] = 0.0
        config["threshold_search"]["max_veb_fpr"] = 1.0
        with tempfile.TemporaryDirectory() as tmp_dir:
            result = train_single_run(
                config=config,
                train_data=self.train_data,
                val_data=self.val_data,
                test_data=None,
                normalization={"statistics_source": "synthetic train split only"},
                output_dir=tmp_dir,
                seed=17,
                device_str="cpu",
                evaluate_internal_test=False,
            )
            self.assertEqual(result["evaluation_scope"], "validation_only")
            self.assertNotIn("test_metrics", result)
            with open(os.path.join(tmp_dir, "metrics.json"), "r", encoding="utf-8") as handle:
                metrics = json.load(handle)
            self.assertEqual(metrics["evaluation_scope"], "validation_only")
            self.assertNotIn("test_metrics", metrics)

    def test_medium_candidate_is_rejected_before_training_or_model_export(self):
        with open(
            "train/ec57/configs/candidate_c_medium_tp5_la8_mlp48_cap2000_w10_dilated_margin_m0025_p50.json",
            "r",
            encoding="utf-8",
        ) as handle:
            config = json.load(handle)
        config["training"]["max_epochs"] = 0
        train_data = dict(self.train_data)
        val_data = dict(self.val_data)
        train_data["features"] = np.pad(self.train_data["features"], ((0, 0), (0, 4)))
        val_data["features"] = np.pad(self.val_data["features"], ((0, 0), (0, 4)))
        normalization = {
            "statistics_source": "synthetic train split only",
            "feature_contract_id": "qn88-ec57-hybrid-io-lookahead-v2",
            "decision_latency_mode": "next_valid_qrs",
            "feature_names": [f"feature_{index}" for index in range(8)],
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            with self.assertRaisesRegex(ValueError, "deployment resource budget exceeded"):
                train_single_run(
                    config=config,
                    train_data=train_data,
                    val_data=val_data,
                    test_data=None,
                    normalization=normalization,
                    output_dir=tmp_dir,
                    seed=17,
                    device_str="cpu",
                    evaluate_internal_test=False,
                )
            self.assertFalse(os.path.exists(os.path.join(tmp_dir, "model_fp32.pt")))
            for filename in (
                "config.json",
                "normalization.json",
                "resource_gate_failure.json",
                "metrics.json",
                "manifest_sha256.txt",
            ):
                self.assertTrue(os.path.isfile(os.path.join(tmp_dir, filename)), filename)
            with open(os.path.join(tmp_dir, "metrics.json"), "r", encoding="utf-8") as handle:
                metrics = json.load(handle)
            self.assertEqual(metrics["status"], "rejected")
            self.assertFalse(metrics["checkpoint_freezable"])
            self.assertEqual(metrics["evaluation_scope"], "pre_training_resource_gate")

    def test_medium_configs_are_labelled_historical_and_oversized(self):
        config_dir = os.path.join("train", "ec57", "configs")
        filenames = sorted(
            filename for filename in os.listdir(config_dir)
            if filename.startswith("candidate_c_medium_") and filename.endswith(".json")
        )
        self.assertEqual(len(filenames), 3)
        for filename in filenames:
            with open(os.path.join(config_dir, filename), "r", encoding="utf-8") as handle:
                description = json.load(handle)["description"]
            with self.subTest(filename=filename):
                self.assertIn("historical oversized diagnostic", description.lower())
                self.assertNotIn("50KB", description)
        with open(os.path.join(config_dir, filenames[0]), "r", encoding="utf-8") as handle:
            first_description = json.load(handle)["description"]
        self.assertIn("54,168 bytes", first_description)

    def test_candidate_configs_match_frozen_common_hyperparameters(self):
        config_dir = os.path.join("train", "ec57", "configs")
        for filename in (
            "candidate_a_morph.json",
            "candidate_b_morph_rr.json",
            "candidate_c_morph_rr_aug.json",
        ):
            with self.subTest(filename=filename):
                with open(os.path.join(config_dir, filename), "r", encoding="utf-8") as handle:
                    config = json.load(handle)
                self.assertEqual(config["training"]["batch_size"], 1024)
                self.assertEqual(config["training"]["max_epochs"], 50)
                self.assertEqual(config["training"]["early_stopping_patience"], 8)
                self.assertEqual(config["training"]["veb_class_weight"], 2.5)
                self.assertNotIn("scheduler", config["training"])
                self.assertEqual(config["threshold_search"]["min_veb_se"], 0.90)

    def test_all_formal_threshold_configs_freeze_minimum_veb_sensitivity(self):
        config_dir = os.path.join("train", "ec57", "configs")
        for filename in sorted(os.listdir(config_dir)):
            if not filename.endswith(".json"):
                continue
            with open(os.path.join(config_dir, filename), "r", encoding="utf-8") as handle:
                config = json.load(handle)
            if "threshold_search" not in config:
                continue
            with self.subTest(filename=filename):
                self.assertEqual(config["threshold_search"]["min_veb_se"], 0.90)

    def test_threshold_scan_rejects_high_precision_low_sensitivity_point(self):
        class ProbabilityFromWaveform(torch.nn.Module):
            def forward(self, x_wave, _x_feat):
                probabilities = x_wave[:, 0, 0].clamp(1e-6, 1.0 - 1e-6)
                return torch.stack((torch.log1p(-probabilities), torch.log(probabilities)), dim=1)

        probabilities = np.array([0.99] + [0.40] * 9 + [0.50] * 100, dtype=np.float32)
        labels = np.array([1] * 10 + [0] * 100, dtype=np.int64)
        waveforms = np.zeros((len(labels), 160), dtype=np.float32)
        waveforms[:, 0] = probabilities
        dataset = BeatDataset(
            waveforms=waveforms,
            features=np.zeros((len(labels), 4), dtype=np.float32),
            labels=labels,
            patient_ids=np.array(["validation_patient"] * len(labels)),
            use_features=True,
            is_training=False,
        )
        loader = torch.utils.data.DataLoader(dataset, batch_size=64, shuffle=False)

        with self.assertRaises(ThresholdGateError) as raised:
            scan_optimal_threshold(
                ProbabilityFromWaveform(),
                loader,
                device=torch.device("cpu"),
                scan_range=(0.40, 0.90),
                scan_step=0.10,
            )

        summary = raised.exception.summary
        self.assertEqual(summary["frozen_min_veb_se_percent"], 90.0)
        diagnostic = summary["best_se_under_plus_p_and_fpr_gates"]
        self.assertEqual(diagnostic["se_percent"], 10.0)
        self.assertEqual(diagnostic["plus_p_percent"], 100.0)
        self.assertEqual(diagnostic["fpr_percent"], 0.0)

    def test_class_prior_ablation_configs_differ_only_in_declared_weight_and_identity(self):
        filenames = (
            "candidate_c_dequant_w1.json",
            "candidate_c_dequant_w01.json",
            "candidate_c_dequant_w002.json",
        )
        normalized = []
        weights = []
        for filename in filenames:
            with open(os.path.join("train", "ec57", "configs", filename), "r", encoding="utf-8") as handle:
                config = json.load(handle)
            weights.append(config["training"]["veb_class_weight"])
            config["candidate_name"] = "normalized"
            config["description"] = "normalized"
            config["training"]["veb_class_weight"] = "normalized"
            normalized.append(config)
        self.assertEqual(weights, [1.0, 0.1, 0.02])
        self.assertEqual(normalized[0], normalized[1])
        self.assertEqual(normalized[1], normalized[2])

    def test_asymmetric_negative_focal_gamma_zero_matches_weighted_cross_entropy(self):
        from train.ec57.train_nv import asymmetric_focal_cross_entropy

        logits = torch.tensor([[3.0, -1.0], [-2.0, 2.0], [0.5, -0.25]], dtype=torch.float64)
        targets = torch.tensor([0, 1, 0], dtype=torch.long)
        weights = torch.tensor([1.0, 2.5], dtype=torch.float64)
        expected = torch.nn.functional.cross_entropy(logits, targets, weight=weights)
        actual = asymmetric_focal_cross_entropy(
            logits, targets, class_weights=weights, negative_gamma=0.0
        )
        torch.testing.assert_close(actual, expected, rtol=0.0, atol=0.0)

    def test_asymmetric_negative_focal_preserves_positive_loss_and_focuses_hard_negatives(self):
        from train.ec57.train_nv import asymmetric_focal_cross_entropy

        logits = torch.tensor([[5.0, -5.0], [-2.0, 2.0], [-1.0, 1.0]], dtype=torch.float64)
        targets = torch.tensor([0, 0, 1], dtype=torch.long)
        weights = torch.tensor([1.0, 2.5], dtype=torch.float64)
        gamma_one = asymmetric_focal_cross_entropy(
            logits, targets, class_weights=weights, negative_gamma=1.0, reduction="none"
        )
        gamma_four = asymmetric_focal_cross_entropy(
            logits, targets, class_weights=weights, negative_gamma=4.0, reduction="none"
        )
        self.assertLess(gamma_four[0], gamma_one[0])
        self.assertGreater(gamma_four[1] / gamma_four[0], gamma_one[1] / gamma_one[0])
        torch.testing.assert_close(gamma_four[2], gamma_one[2], rtol=0.0, atol=0.0)
        with self.assertRaisesRegex(ValueError, "negative_gamma"):
            asymmetric_focal_cross_entropy(logits, targets, class_weights=weights, negative_gamma=-1.0)

    def test_negative_focal_ablation_configs_differ_only_in_declared_gamma_and_identity(self):
        filenames = (
            "candidate_c_dequant_focal_g1.json",
            "candidate_c_dequant_focal_g2.json",
            "candidate_c_dequant_focal_g4.json",
        )
        normalized = []
        gammas = []
        for filename in filenames:
            with open(os.path.join("train", "ec57", "configs", filename), "r", encoding="utf-8") as handle:
                config = json.load(handle)
            gammas.append(config["training"]["negative_focal_gamma"])
            self.assertEqual(config["training"]["loss"], "asymmetric_negative_focal_cross_entropy")
            config["candidate_name"] = "normalized"
            config["description"] = "normalized"
            config["training"]["negative_focal_gamma"] = "normalized"
            normalized.append(config)
        self.assertEqual(gammas, [1.0, 2.0, 4.0])
        self.assertEqual(normalized[0], normalized[1])
        self.assertEqual(normalized[1], normalized[2])

    def test_five_bin_temporal_pool_preserves_bin_separation_and_budget(self):
        model = TinyECGCNN_NV(temporal_pool_bins=5)
        activation = torch.zeros((1, 16, 40), dtype=torch.float32)
        for bin_index in range(5):
            activation[:, :, bin_index * 8:(bin_index + 1) * 8] = float(bin_index + 1)
        pooled = model.temporal_pool(activation)
        self.assertEqual(tuple(pooled.shape), (1, 80))
        expected = torch.arange(1, 6, dtype=torch.float32).repeat_interleave(16).view(1, 80)
        torch.testing.assert_close(pooled, expected, rtol=0.0, atol=0.0)
        self.assertEqual(count_parameters(model), 1674)
        self.assertEqual(count_macs(model, input_len=160), 91048)

    def test_five_bin_config_changes_only_declared_representation(self):
        with open("train/ec57/configs/candidate_c_morph_rr_aug.json", "r", encoding="utf-8") as handle:
            baseline = json.load(handle)
        with open("train/ec57/configs/candidate_c_temporal_pool5.json", "r", encoding="utf-8") as handle:
            candidate = json.load(handle)
        self.assertEqual(candidate["model"]["temporal_pool_bins"], 5)
        candidate["candidate_name"] = baseline["candidate_name"]
        candidate["description"] = baseline["description"]
        candidate["model"].pop("temporal_pool_bins")
        self.assertEqual(candidate, baseline)

    def test_patient_cap_ablation_configs_differ_only_in_declared_cap_and_identity(self):
        filenames = (
            "candidate_c_temporal_pool5_cap500.json",
            "candidate_c_temporal_pool5_cap1000.json",
            "candidate_c_temporal_pool5_cap2000.json",
        )
        normalized = []
        caps = []
        for filename in filenames:
            with open(os.path.join("train", "ec57", "configs", filename), "r", encoding="utf-8") as handle:
                config = json.load(handle)
            caps.append(config["data"]["max_beats_per_patient_epoch"])
            self.assertEqual(config["training"]["loss"], "weighted_cross_entropy")
            self.assertEqual(config["model"]["temporal_pool_bins"], 5)
            config["candidate_name"] = "normalized"
            config["description"] = "normalized"
            config["data"]["max_beats_per_patient_epoch"] = "normalized"
            normalized.append(config)
        self.assertEqual(caps, [500, 1000, 2000])
        self.assertEqual(normalized[0], normalized[1])
        self.assertEqual(normalized[1], normalized[2])

    def test_balanced_temporal_focal_configs_differ_only_in_gamma_and_identity(self):
        filenames = tuple(
            f"candidate_c_temporal_pool5_cap2000_focal_g{gamma}.json"
            for gamma in (1, 2, 4)
        )
        normalized = []
        gammas = []
        for filename in filenames:
            with open(os.path.join("train", "ec57", "configs", filename), "r", encoding="utf-8") as handle:
                config = json.load(handle)
            gammas.append(config["training"]["negative_focal_gamma"])
            self.assertEqual(config["data"]["max_beats_per_patient_epoch"], 2000)
            self.assertEqual(config["model"]["temporal_pool_bins"], 5)
            self.assertEqual(config["training"]["loss"], "asymmetric_negative_focal_cross_entropy")
            config["candidate_name"] = "normalized"
            config["description"] = "normalized"
            config["training"]["negative_focal_gamma"] = "normalized"
            normalized.append(config)
        self.assertEqual(gammas, [1.0, 2.0, 4.0])
        self.assertEqual(normalized[0], normalized[1])
        self.assertEqual(normalized[1], normalized[2])

    def test_ap_checkpoint_candidate_changes_only_selection_metric_and_identity(self):
        config_root = os.path.join("train", "ec57", "configs")
        with open(os.path.join(config_root, "candidate_c_tp5_la8_mlp5_cap2000_w10.json"), "r", encoding="utf-8") as handle:
            baseline = json.load(handle)
        with open(os.path.join(config_root, "candidate_c_tp5_la8_mlp5_cap2000_ap.json"), "r", encoding="utf-8") as handle:
            candidate = json.load(handle)
        self.assertEqual(candidate["training"]["early_stopping_metric"], "val_average_precision")
        candidate["candidate_name"] = baseline["candidate_name"]
        candidate["description"] = baseline["description"]
        candidate["training"]["early_stopping_metric"] = baseline["training"]["early_stopping_metric"]
        self.assertEqual(candidate, baseline)

    def test_depthwise_morphology_model_shape_bins_and_budget(self):
        from train.ec57.model_nv import TinyECGCNN_NV_Depthwise

        model = TinyECGCNN_NV_Depthwise(temporal_pool_bins=5)
        waveform = torch.randn(3, 1, 160)
        features = torch.randn(3, 4)
        self.assertEqual(tuple(model(waveform, features).shape), (3, 2))
        activation = torch.zeros((1, 32, 40), dtype=torch.float32)
        for bin_index in range(5):
            activation[:, :, bin_index * 8:(bin_index + 1) * 8] = float(bin_index + 1)
        pooled = model.temporal_pool(activation)
        expected = torch.arange(1, 6, dtype=torch.float32).repeat_interleave(32).view(1, 160)
        torch.testing.assert_close(pooled, expected, rtol=0.0, atol=0.0)
        self.assertEqual(count_parameters(model), 1650)
        self.assertEqual(count_macs(model, input_len=160), 65288)

    def test_depthwise_candidate_changes_only_architecture_identity(self):
        with open("train/ec57/configs/candidate_c_temporal_pool5_cap2000.json", "r", encoding="utf-8") as handle:
            baseline = json.load(handle)
        with open("train/ec57/configs/candidate_ds_temporal_pool5_cap2000.json", "r", encoding="utf-8") as handle:
            candidate = json.load(handle)
        self.assertEqual(candidate["model"]["architecture"], "TinyECGCNN_NV_Depthwise")
        candidate["candidate_name"] = baseline["candidate_name"]
        candidate["description"] = baseline["description"]
        candidate["model"]["architecture"] = baseline["model"]["architecture"]
        self.assertEqual(candidate, baseline)

    def test_smoke_overrides_are_explicit_and_do_not_mutate_formal_config(self):
        with open("train/ec57/configs/candidate_b_morph_rr.json", "r", encoding="utf-8") as handle:
            formal = json.load(handle)
        smoke = apply_smoke_overrides(formal)
        self.assertEqual(formal["training"]["max_epochs"], 50)
        self.assertEqual(formal["threshold_search"]["min_veb_se"], 0.90)
        self.assertEqual(formal["threshold_search"]["min_veb_plus_p"], 0.95)
        self.assertEqual(smoke["training"]["max_epochs"], 1)
        self.assertEqual(smoke["threshold_search"]["min_veb_se"], 0.0)
        self.assertEqual(smoke["threshold_search"]["min_veb_plus_p"], 0.0)
        self.assertEqual(smoke["threshold_search"]["max_veb_fpr"], 1.0)
        self.assertEqual(smoke["run_mode"], "one_epoch_pipeline_smoke")

    def test_validation_only_summary_handles_unloaded_internal_test(self):
        self.assertEqual(
            format_split_summary("Internal test", None),
            "Internal test: not loaded (validation-only isolation)",
        )

    def test_epoch_sampler_caps_each_patient_and_global_negative_ratio(self):
        labels = np.array([1] * 20 + [0] * 100 + [1] * 5 + [0] * 100, dtype=np.int64)
        patient_ids = np.array(["p1"] * 120 + ["p2"] * 105)
        selected = build_epoch_sample_indices(
            labels,
            patient_ids,
            max_beats_per_patient=30,
            max_negative_per_positive=4,
            seed=17,
            epoch=3,
        )
        chosen_labels = labels[selected]
        chosen_patients = patient_ids[selected]
        self.assertLessEqual(int(np.sum(chosen_labels == 0)), 4 * int(np.sum(chosen_labels == 1)))
        self.assertLessEqual(int(np.sum(chosen_patients == "p1")), 30)
        self.assertLessEqual(int(np.sum(chosen_patients == "p2")), 30)
        repeated = build_epoch_sample_indices(
            labels,
            patient_ids,
            max_beats_per_patient=30,
            max_negative_per_positive=4,
            seed=17,
            epoch=3,
        )
        np.testing.assert_array_equal(selected, repeated)

    def test_fp32_input_dequantization_maps_signed_int8_after_augmentation(self):
        waveforms = np.zeros((1, 160), dtype=np.int8)
        waveforms[0, 0] = -128
        waveforms[0, 1] = 127
        features = np.array([[-128, 127, 0, 64]], dtype=np.int8)
        dataset = BeatDataset(
            waveforms=waveforms,
            features=features,
            labels=np.array([1]),
            patient_ids=np.array(["p1"]),
            input_divisor=128.0,
            is_training=False,
        )
        x_wave, x_feat, _, _ = dataset[0]
        self.assertAlmostEqual(float(x_wave[0, 0]), -1.0)
        self.assertAlmostEqual(float(x_wave[0, 1]), 127.0 / 128.0)
        self.assertAlmostEqual(float(x_feat[0]), -1.0)
        self.assertAlmostEqual(float(x_feat[1]), 127.0 / 128.0)


if __name__ == '__main__':
    unittest.main()
