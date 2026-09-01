# Optimization Run: `20260831-193000-m3b-margin-loss-and-dilation-ablation`

## Identity

- Run ID: `20260831-193000-m3b-margin-loss-and-dilation-ablation`
- Stage: `M2 loss optimization & architecture`
- Status: `completed`
- Started/finished: `2026-08-31 19:30 CST / 2026-08-31 19:48 CST`
- Agent/operator: Antigravity
- Baseline run: `20260831-182200-m2ac-average-precision-checkpoint-selection` (AP 0.8316, max +P 90.68%, FPR 0.0862% at Se 85.22%)
- Candidates: 3 concurrent candidates across 3 GPUs testing Asymmetric Margin Loss and Dilated Conv Backbone within the 2,048 parameter / 100k MAC envelope:
  1. Candidate 1 (GPU 0): `5-bin, 8 features, MLP-5 (1,961 params, 91,330 MACs), Asymmetric Margin Loss (margin 0.05, penalty 2.0), AP checkpoint selection`
  2. Candidate 2 (GPU 1): `5-bin, 8 features, MLP-5 (1,961 params, 91,330 MACs), Tight Asymmetric Margin Loss (margin 0.03, penalty 4.0), AP checkpoint selection`
  3. Candidate 3 (GPU 2): `5-bin, 8 features, MLP-5, Dilated Conv Backbone (dilation 2, receptive field doubled, 1,961 params, 91,330 MACs), AP checkpoint selection`

## Problem and evidence

- In M2ac, rank-aligned AP selection elevated max precision to 90.68% and AP to 0.8316, but 62 residual false positives across 290k non-VEB beats prevent crossing the 95.0% threshold gate.
- Standard cross-entropy provides weak gradient penalty for near-zero false positive probabilities ($p \in [0.03, 0.15]$), allowing negative tail dispersion.
- Receptive field in standard Conv1D is limited to local QRS; dilated conv doubles the receptive field to encompass the full ST-T repolarization morphology without increasing parameter count or MACs.

## Optimization

- Introduce `AsymmetricMarginCrossEntropyLoss` with quadratic false positive penalty $\gamma \cdot \max(0, p - m)^2$ for negative samples exceeding margin $m$.
- Introduce `dilation: 2` in `TinyECGCNN_NV` for layers 2 and 3, preserving exact length 80 and 40 via matched padding ($p=4$ and $p=2$).
- Concurrently train on 3 idle GPUs using clean repaired M2ab cache (`runs/20260831-180114-m2ab-lookahead-contract-boundary-repair/native_cache_retry1`), seed 17, validation-only. Internal test set remains unopened.

## Frozen acceptance criteria

- TDD confirms model budget: Candidate 1 = 1,961 params / 91,330 MACs; Candidate 2 = 1,961 params / 91,330 MACs; Candidate 3 = 1,961 params / 91,330 MACs (all $\le 2,048$ params, $\le 100,000$ MACs).
- Validation eligibility gate: `VEB +P >= 95.0%` and `VEB FPR <= 0.25%`.
- If an eligible threshold exists, select the threshold maximizing `VEB Se`.
- If seed 17 passes, proceed to seeds 29 and 43.
- If seed 17 fails across all 3 candidates, record diagnostic curves and analyze next steps under `/goal`.

## Execution

- Entry commands:
  1. Unit tests pass (195/195 PASS)
  2. Sync updated code to remote GPU server
  3. Concurrently train 3 candidate runs on GPUs 0, 1, 2
  4. Download report artifacts and compute threshold curves
- Hardware: remote GPU server (GPU 0: RTX 5060 Ti, GPU 1: RTX 5060 Ti, GPU 2: RTX 4090)

## Results

| Candidate | Params / Budget | MACs / Budget | Best Val AP | Optimal F1 Operating Point | Max +P Scanned | Eligible Gates |
|---|---:|---:|---:|---|---:|---|
| Cand 1 (Margin m=0.05, p=2.0) | 1,961 / 2,048 | 91,330 / 100k | 0.8075 | th=0.747: Se 84.58%, +P 79.15%, FPR 0.1086%, F1 81.78% | 90.06% (th=0.979, FP=64) | 0 |
| **Cand 2 (Tight margin m=0.03, p=4.0)** | **1,961 / 2,048** | **91,330 / 100k** | **0.8456** | **th=0.645: Se 87.13%, +P 84.50%, FPR 0.0779%, F1 85.79%** | **92.25%** (th=0.980, FP=42) | **0** |
| Cand 3 (Dilated d=2, AP selection) | 1,961 / 2,048 | 91,330 / 100k | 0.8179 | th=0.761: Se 85.93%, +P 83.11%, FPR 0.0851%, F1 84.49% | 90.02% (th=0.993, FP=50) | 0 |

- Diagnostic findings:
  - **Candidate 2 (Tight Margin Loss)** achieved a major breakthrough across all validation metrics:
    - **Best Val AP**: **0.8456** (highest in project history).
    - **Max +P**: **92.25%** (at th=0.980: 500 TPs, only **42 FPs** across 290,106 non-VEBs, FPR = **0.0145%**).
    - **Optimal F1 Operating Point**: th=0.645 $\to$ **Se 87.13%, +P 84.50%, FPR 0.0779%, F1 85.79%** (1,232 TPs, 226 FPs).
    - Residual false positive count was successfully reduced from 62 down to 42.
  - To cross $\ge 95.0\%$ at 500 TPs, the FP count needs to be further compressed from 42 to $\le 26$ ($16$ beats difference).

- Evidence: `docs/reports/20260831-193000-m3b-margin-loss-and-dilation-ablation/`
- Unverified items: seeds 29/43, internal test, external databases, quantization, RTL and hardware.

## Decision

- Decision: `回到训练`
- Tight Asymmetric Margin Loss ($m=0.03, \gamma=4.0$) confirmed as the superior loss function (pushing AP to 0.8456 and max +P to 92.25%).
- Next step: Combine Tight Margin Loss with Direction 3 (P-wave Absence & Polarity Discordance features) to eliminate the remaining 16 FPs and cross the 95.0% gate.
