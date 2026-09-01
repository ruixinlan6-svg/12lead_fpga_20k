"""Tests for M2/M3 lightweight Non-VEB/VEB ECG model architecture, shape, and budget."""

import unittest

from train.ec57.resource_budget import (
    MODEL_DEPLOYMENT_PACKAGE_MAX_BYTES,
    MODEL_MACS_PER_BEAT_MAX,
    MODEL_MAX_ACTIVATION_BYTES,
    MODEL_PACKAGE_CONTAINER_OVERHEAD_RESERVE_BYTES,
)

try:
    import torch
    import torch.nn as nn
    from train.ec57.model_nv import TinyECGCNN_NV, MediumECGCNN_NV, count_parameters, count_macs
except ImportError:
    torch = None
    nn = None
    TinyECGCNN_NV = None
    MediumECGCNN_NV = None
    count_parameters = None
    count_macs = None


class TestModelBudget(unittest.TestCase):
    """Verifies that TinyECGCNN_NV strictly adheres to Section 1.3 budget and architecture."""

    def setUp(self):
        if torch is None or TinyECGCNN_NV is None:
            self.skipTest("PyTorch / TinyECGCNN_NV not implemented yet")
        self.model = TinyECGCNN_NV()

    def test_parameter_count_and_budget(self):
        """Frozen baseline architecture must retain exactly 1,546 parameters."""
        total_params = count_parameters(self.model)
        self.assertEqual(total_params, 1546, f"Expected exactly 1,546 parameters, got {total_params}")

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
        """All candidate heads remain free of frozen forbidden layer families."""
        candidates = [
            self.model,
            TinyECGCNN_NV(temporal_pool_bins=5, num_features=6, mlp_hidden_dim=6),
            TinyECGCNN_NV(temporal_pool_bins=5, num_features=8, mlp_hidden_dim=5),
        ]
        forbidden = (nn.BatchNorm1d, nn.BatchNorm2d, nn.LayerNorm, nn.RNNBase, nn.MultiheadAttention)
        for model in candidates:
            for name, module in model.named_modules():
                self.assertNotIsInstance(module, forbidden, f"Forbidden layer {type(module)} in {name}")

    def test_feature_width_mismatch_fails_closed(self):
        model = TinyECGCNN_NV(num_features=8)
        with self.assertRaisesRegex(ValueError, "x_feat must have shape"):
            model(torch.randn(2, 1, 160), torch.randn(2, 6))

    def test_six_feature_five_bin_model_budget(self):
        """Verify 5-bin temporal pooling with 6 auxiliary features budget."""
        model = TinyECGCNN_NV(temporal_pool_bins=5, num_features=6)
        total_params = count_parameters(model)
        self.assertEqual(total_params, 1678, f"Expected 1,678 parameters, got {total_params}")

        macs = count_macs(model, input_len=160)
        self.assertEqual(macs, 91052, f"Expected 91,052 MACs, got {macs}")
        self.assertLessEqual(macs, 100000)

        x_wave = torch.randn(4, 1, 160)
        x_feat = torch.randn(4, 6)
        logits = model(x_wave, x_feat)
        self.assertEqual(logits.shape, (4, 2))

    def test_mlp_head_model_budget(self):
        """Verify MLP-head architecture counts and the unchanged 100k-MAC gate."""
        # 5 bins + 6 features + MLP hidden dim 6
        model5 = TinyECGCNN_NV(temporal_pool_bins=5, num_features=6, mlp_hidden_dim=6)
        params5 = count_parameters(model5)
        self.assertEqual(params5, 2040, f"Expected 2,040 params, got {params5}")
        macs5 = count_macs(model5, input_len=160)
        self.assertEqual(macs5, 91408, f"Expected 91,408 MACs, got {macs5}")
        self.assertLessEqual(macs5, 100000)

        # 4 bins + 6 features + MLP hidden dim 7
        model4 = TinyECGCNN_NV(temporal_pool_bins=4, num_features=6, mlp_hidden_dim=7)
        params4 = count_parameters(model4)
        self.assertEqual(params4, 2017, f"Expected 2,017 params, got {params4}")
        macs4 = count_macs(model4, input_len=160)
        self.assertEqual(macs4, 91384, f"Expected 91,384 MACs, got {macs4}")
        self.assertLessEqual(macs4, 100000)

        # 5 bins + 8 features + MLP hidden dim 5
        model5_8 = TinyECGCNN_NV(temporal_pool_bins=5, num_features=8, mlp_hidden_dim=5)
        params5_8 = count_parameters(model5_8)
        self.assertEqual(params5_8, 1961, f"Expected 1,961 params, got {params5_8}")
        macs5_8 = count_macs(model5_8, input_len=160)
        self.assertEqual(macs5_8, 91330, f"Expected 91,330 MACs, got {macs5_8}")
        self.assertLessEqual(macs5_8, 100000)

        # 4 bins + 8 features + MLP hidden dim 7
        model4_8 = TinyECGCNN_NV(temporal_pool_bins=4, num_features=8, mlp_hidden_dim=7)
        params4_8 = count_parameters(model4_8)
        self.assertEqual(params4_8, 2031, f"Expected 2,031 params, got {params4_8}")
        macs4_8 = count_macs(model4_8, input_len=160)
        self.assertEqual(macs4_8, 91398, f"Expected 91,398 MACs, got {macs4_8}")
        self.assertLessEqual(macs4_8, 100000)

        x_wave = torch.randn(4, 1, 160)
        x_feat = torch.randn(4, 6)
        x_feat8 = torch.randn(4, 8)
        out5 = model5(x_wave, x_feat)
        out4 = model4(x_wave, x_feat)
        out5_8 = model5_8(x_wave, x_feat8)
        out4_8 = model4_8(x_wave, x_feat8)
        self.assertEqual(out5.shape, (4, 2))
        self.assertEqual(out4.shape, (4, 2))
        self.assertEqual(out5_8.shape, (4, 2))
        self.assertEqual(out4_8.shape, (4, 2))

    def test_dilated_model_budget(self):
        """Verify dilated conv model (dilation=2) has identical parameter count and MACs."""
        model_dilated = TinyECGCNN_NV(temporal_pool_bins=5, num_features=8, mlp_hidden_dim=5, dilation=2)
        params = count_parameters(model_dilated)
        self.assertEqual(params, 1961)
        macs = count_macs(model_dilated, input_len=160)
        self.assertEqual(macs, 91330)
        self.assertLessEqual(macs, 100000)

        x_wave = torch.randn(4, 1, 160)
        x_feat8 = torch.randn(4, 8)
        out = model_dilated(x_wave, x_feat8)
        self.assertEqual(out.shape, (4, 2))

    def test_asymmetric_margin_loss(self):
        """Verify AsymmetricMarginCrossEntropyLoss computes valid gradients without NaN."""
        from train.ec57.train_nv import AsymmetricMarginCrossEntropyLoss
        weights = torch.tensor([1.0, 1.0])
        criterion = AsymmetricMarginCrossEntropyLoss(weights, fp_margin=0.05, fp_penalty_weight=2.0)
        logits = torch.randn(8, 2, requires_grad=True)
        targets = torch.tensor([0, 1, 0, 0, 1, 0, 0, 0])
        loss = criterion(logits, targets)
        self.assertTrue(torch.isfinite(loss))
        loss.backward()
        self.assertTrue(torch.isfinite(logits.grad).all())

    def test_2500b_capacity_models(self):
        """Verify historical 2,500-parameter candidates retain counts and the 100k-MAC gate."""
        # Candidate A: 5 bins + 8 features + MLP hidden 11
        model_a = TinyECGCNN_NV(temporal_pool_bins=5, num_features=8, mlp_hidden_dim=11, dilation=2)
        params_a = count_parameters(model_a)
        self.assertEqual(params_a, 2507)
        macs_a = count_macs(model_a, input_len=160)
        self.assertEqual(macs_a, 91870)
        self.assertLessEqual(macs_a, 100000)

        # Candidate B: 8 bins + 8 features + MLP hidden 7
        model_b = TinyECGCNN_NV(temporal_pool_bins=8, num_features=8, mlp_hidden_dim=7, dilation=2)
        params_b = count_parameters(model_b)
        self.assertEqual(params_b, 2479)
        macs_b = count_macs(model_b, input_len=160)
        self.assertEqual(macs_b, 91846)
        self.assertLessEqual(macs_b, 100000)

    def test_m3g_medium_candidate_1_exceeds_frozen_deployment_budgets(self):
        """M3g Medium Candidate 1 is not a compliant 50 KiB / 100k-MAC model."""
        from train.ec57.model_nv import estimate_model_deployment_resources

        model_med = MediumECGCNN_NV(temporal_pool_bins=5, num_features=8, mlp_hidden_dim=48, dilation=2)
        params = count_parameters(model_med)
        self.assertEqual(params, 51154)
        resources = estimate_model_deployment_resources(model_med, input_len=160)
        self.assertEqual(resources["parameter_payload_bytes"], 54168)
        self.assertEqual(
            resources["package_overhead_reserve_bytes"],
            MODEL_PACKAGE_CONTAINER_OVERHEAD_RESERVE_BYTES,
        )
        self.assertEqual(resources["deployment_package_bytes"], 55192)
        self.assertEqual(resources["max_activation_bytes"], 5120)
        self.assertEqual(resources["macs_per_beat"], 1853920)
        self.assertGreater(resources["deployment_package_bytes"], MODEL_DEPLOYMENT_PACKAGE_MAX_BYTES)
        self.assertGreater(resources["max_activation_bytes"], MODEL_MAX_ACTIVATION_BYTES)
        self.assertGreater(resources["macs_per_beat"], MODEL_MACS_PER_BEAT_MAX)

        x_wave = torch.randn(4, 1, 160)
        x_feat = torch.randn(4, 8)
        out = model_med(x_wave, x_feat)
        self.assertEqual(out.shape, (4, 2))

    def test_complete_deployment_package_and_single_layer_activation_budgets(self):
        """Complete INT8 deployment package fits 50 KiB; largest activation fits 2 KiB."""
        from train.ec57.model_nv import estimate_model_deployment_resources

        candidates = [
            TinyECGCNN_NV(),
            TinyECGCNN_NV(temporal_pool_bins=5, num_features=6, mlp_hidden_dim=6),
            TinyECGCNN_NV(temporal_pool_bins=5, num_features=8, mlp_hidden_dim=5),
            TinyECGCNN_NV(temporal_pool_bins=5, num_features=8, mlp_hidden_dim=5, dilation=2),
            TinyECGCNN_NV(temporal_pool_bins=5, num_features=8, mlp_hidden_dim=11, dilation=2),
            TinyECGCNN_NV(temporal_pool_bins=8, num_features=8, mlp_hidden_dim=7, dilation=2),
        ]
        for model in candidates:
            resources = estimate_model_deployment_resources(model, input_len=160)
            self.assertLessEqual(resources["deployment_package_bytes"], MODEL_DEPLOYMENT_PACKAGE_MAX_BYTES)
            self.assertLessEqual(resources["macs_per_beat"], MODEL_MACS_PER_BEAT_MAX)
            self.assertLessEqual(resources["max_activation_bytes"], MODEL_MAX_ACTIVATION_BYTES)

        baseline = estimate_model_deployment_resources(TinyECGCNN_NV(), input_len=160)
        self.assertEqual(baseline["max_activation_bytes"], 1280)

    def test_dual_branch_model_budget_and_forward(self):
        """DualBranchECGCNN_NV satisfies all hardware deployment constraints."""
        from train.ec57.model_nv import DualBranchECGCNN_NV, estimate_model_deployment_resources

        expected_macs = {24: 95360, 32: 96832, 40: 98304}
        for embedding_dim, macs in expected_macs.items():
            model = DualBranchECGCNN_NV(
                temporal_pool_bins=5,
                num_features=8,
                morph_emb_dim=embedding_dim,
                timing_emb_dim=embedding_dim,
                dilation=2,
            )
            resources = estimate_model_deployment_resources(model, input_len=160)
            self.assertEqual(resources["macs_per_beat"], macs)
            self.assertLessEqual(resources["deployment_package_bytes"], MODEL_DEPLOYMENT_PACKAGE_MAX_BYTES)
            self.assertLessEqual(resources["macs_per_beat"], MODEL_MACS_PER_BEAT_MAX)
            self.assertLessEqual(resources["max_activation_bytes"], MODEL_MAX_ACTIVATION_BYTES)

        x_wave = torch.randn(4, 1, 160)
        x_feat = torch.randn(4, 8)
        logits = model(x_wave, x_feat)
        self.assertEqual(logits.shape, (4, 2))

    def test_bilinear_gate_mac_is_counted(self):
        from train.ec57.model_nv import estimate_model_deployment_resources

        model = TinyECGCNN_NV(
            temporal_pool_bins=5,
            num_features=8,
            mlp_hidden_dim=96,
            dilation=2,
            use_bilinear_gating=True,
        )
        resources = estimate_model_deployment_resources(model, input_len=160)
        self.assertEqual(resources["macs_per_beat"], 99522)
        self.assertLessEqual(resources["macs_per_beat"], MODEL_MACS_PER_BEAT_MAX)


if __name__ == '__main__':
    unittest.main()
