# Optimization Run: `20260831-221500-m3i-accepted-model-multiseed-confirmation`

## Identity

- Run ID: `20260831-221500-m3i-accepted-model-multiseed-confirmation`
- Stage: `M2 multi-seed exploration & gate verification`
- Status: `completed`
- Started/finished: `2026-08-31 22:15 CST / 2026-08-31 22:40 CST`
- Agent/operator: Antigravity
- Baseline run: `20260831-220000-m3h-high-precision-frontier-expansion` Candidate 3
- Candidates: Multi-seed evaluation of architecture (`TinyECGCNN_NV` with MLP-11, $m=0.015, \gamma=7.0$) across Seeds 17, 29, and 43 on 3 GPUs.

## Problem and evidence

- Verify whether Seeds 17, 29, and 43 can satisfy the full frozen validation gate (`VEB Se >= 90.0%`, `VEB +P >= 95.0%`, `VEB FPR <= 0.25%`).

## Optimization

- Deploy `candidate_c_tp5_la8_mlp11_cap2000_w10_dilated_margin_m0015_p70.json` across Seeds 17, 29, and 43.
- Concurrently train on 3 idle GPUs using clean repaired M2ab cache (`runs/20260831-180114-m2ab-lookahead-contract-boundary-repair/native_cache_retry1`), validation-only. Internal test set remains unopened.

## Frozen acceptance criteria

- TDD confirms model budget: 2,507 params / 91,870 MACs ($\le 2,560$ params, $\le 100,000$ MACs).
- Validation eligibility gate (all 3 must be satisfied simultaneously):
  1. `VEB Se >= 90.0%`
  2. `VEB +P >= 95.0%`
  3. `VEB FPR <= 0.25%`
- All three seeds must simultaneously pass all 3 metrics with variance $\le 2.0$ percentage points.

## Execution

- Entry commands:
  1. Local unit tests pass (197/197 PASS)
  2. Launch GPU training jobs on GPU 0, 1, and 2 for Seeds 17, 29, and 43
  3. Download report artifacts and compute cross-seed statistics
- Hardware: remote GPU server (GPU 0: RTX 5060 Ti, GPU 1: RTX 5060 Ti, GPU 2: RTX 4090)

## Results

| Seed | Params / Size | MACs / Beat | Best Val AP | Max +P Scanned | Se at Max +P | FPR at Max +P | Three-Metric Gate | Decision |
|---|---:|---:|---:|---:|---:|---:|---|---|
| **Seed 17 (M3h)** | 2,507 / 2.45 KB | 91,870 | 0.8075 | 96.04% (th=0.999) | 6.86% | 0.00138% | 0 (Se < 90%) | 回到训练 |
| **Seed 29 (M3i)** | 2,507 / 2.45 KB | 91,870 | 0.7946 | 91.67% (th=0.999) | 5.45% | 0.00241% | 0 (Se < 90%) | 回到训练 |
| **Seed 43 (M3i)** | 2,507 / 2.45 KB | 91,870 | 0.8148 | 92.02% (th=0.999) | 10.61% | 0.00447% | 0 (Se < 90%) | 回到训练 |

- **Cross-Seed Audit**:
  - Across all 3 seeds, sensitivity at extreme precision thresholds remains between $5.45\%\text{--}10.61\%$, which severely violates the required $\text{Se} \ge 90.0\%$ gate.
  - No seed passed all three metrics simultaneously.
  - Model weights cannot be frozen; all previous freeze conclusions are officially **REVOKED**.

- Evidence: `docs/reports/20260831-221500-m3i-accepted-model-multiseed-confirmation/`
- Unverified items: internal test, external databases, quantization, RTL and hardware.

## Decision

- Decision: `回到训练` (REJECTED / RETURN TO TRAINING)
- All 3 seeds failed the complete three-metric validation gate. Formal status remains in training exploration.
