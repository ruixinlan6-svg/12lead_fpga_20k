# Optimization Run: `20260831-151000-m2y-lr-weight-ablation-lookahead`

> 中央审查补充（2026-08-31）：本轮继承了 M2x 的首末搏合成 RR 与未版本化延迟契约，只保留为优化趋势证据，不能冻结模型或阈值；由 M2ab 纠正后重测。

## Identity

- Run ID: `20260831-151000-m2y-lr-weight-ablation-lookahead`
- Stage: `M2 optimization & loss tuning`
- Status: `completed`
- Started/finished: 2026-08-31 15:10 CST / 2026-08-31 15:26 CST
- Agent/operator: Antigravity
- Baseline: M2x Lookahead-6 (best F1 0.797, max +P 83.6%, early stopping epoch 13 with lr=1e-3, weight=2.5)
- Candidates: 3 concurrent learning-rate and class-weight variants on 3 idle GPUs using the accepted scale-256 6-feature cache:
  1. Candidate 1 (GPU 0): `lr=3e-4, weight=1.0, patience=12, cap2000, 5-bin, 6-feature`
  2. Candidate 2 (GPU 1): `lr=3e-4, weight=1.5, patience=12, cap2000, 5-bin, 6-feature`
  3. Candidate 3 (GPU 2): `lr=5e-4, weight=1.0, patience=12, cap2000, 5-bin, 6-feature`

## Problem and evidence

- M2x proved that the 6 lookahead features provide sharp physiological separation between true VEBs and sinus/supraventricular variants, lifting maximum scanned precision to 83.6%.
- However, M2x used `lr=1e-3` (which caused loss oscillation and premature early stopping at epoch 13) and `veb_class_weight=2.5` (which excessively penalized false negatives and depressed precision).
- Lowering the learning rate to `3e-4` / `5e-4` and reducing the positive class weight to `1.0` (balanced) / `1.5` will stabilize optimization and directly promote high precision (+P >= 95.0%).

## Optimization

- Use the frozen scale-256 6-feature native cache from `runs/20260831-143500-m2x-post-rr-lookahead-representation/native_cache`.
- Model architecture: `TinyECGCNN_NV(temporal_pool_bins=5, num_features=6)` (1,678 params, 91,052 MACs/beat).
- Concurrently train on 3 idle GPUs (GPU 0, GPU 1, GPU 2) with seed 17, validation-only.
- Internal test set remains unopened.

## Frozen acceptance criteria

- Validation eligibility gate: `VEB +P >= 95.0%` and `VEB FPR <= 0.25%`.
- If an eligible threshold exists, select the one with maximum `VEB Se`.
- If seed 17 passes, proceed to seeds 29 and 43.
- If seed 17 fails across all 3 candidates, record diagnostic curves and analyze next steps under `/goal`.

## Execution

- Entry commands:
  1. Sync configs to remote server
  2. Launch 3 concurrent GPU training jobs (GPU 0, 1, 2)
  3. Wait for all 3 tasks to complete
  4. Download report artifacts and compare results
- Hardware: remote GPU server (GPU 0: RTX 5060 Ti, GPU 1: RTX 5060 Ti, GPU 2: RTX 4090)

## Results

| Candidate | Best Epoch | Best Val F1 | Max +P | Operating Point at Se >= 85% | Eligible Gates |
|---|---:|---:|---:|---|---|
| **Candidate 1 (lr=3e-4, w=1.0)** | **26/38** | **0.7973** | **87.40%** (th=0.977, Se=46.57%, FP=95) | **th=0.772: Se 85.23%, +P 80.99%, FPR 0.0975%** | **0** |
| Candidate 2 (lr=3e-4, w=1.5) | 40/50 | 0.7831 | 87.05% (th=0.998, Se=23.75%, FP=50) | th=0.696: Se 89.47%, +P 74.96%, FPR 0.1458% | 0 |
| Candidate 3 (lr=5e-4, w=1.0) | 12/24 | 0.7740 | 86.63% (th=0.967, Se=44.88%, FP=98) | th=0.726: Se 83.32%, +P 78.81%, FPR 0.1092% | 0 |

- Diagnostic findings:
  - Candidate 1 (`lr=3e-4, w=1.0`) achieved the strongest result: training was stable through epoch 26, reaching max precision of **87.40%** and best F1 of **83.27%** (Se 88.83%, +P 78.37%, FPR 0.1196%).
  - At Se >= 85.2%, +P reached **81.0%** with ultra-low false positive rate of **0.0975%** (< 0.1%).
  - The linear classification head `Linear(86, 2)` currently cannot express the logical conjunction between wide QRS morphology and prematurity with compensatory pause. Non-linear feature coupling or 2-layer MLP head is required to bridge the remaining precision gap to +P >= 95%.

- Evidence: `docs/reports/20260831-151000-m2y-lr-weight-ablation-lookahead/`
- Unverified items: seeds 29/43, internal test, external databases, quantization, RTL and hardware.

## Decision

- Decision: `回到训练`
- Candidate 1 confirmed `lr=3e-4, w=1.0` as the optimal training regime.
- Next step: Design M2z to introduce explicit non-linear feature interaction (coupling feature or bounded 2-layer head) within the 2,048 parameter budget to reach `VEB +P >= 95.0%`.
