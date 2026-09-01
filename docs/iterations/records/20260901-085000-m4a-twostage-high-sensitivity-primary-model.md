# Optimization Run: `20260901-085000-m4a-twostage-high-sensitivity-primary-model`

> **Central audit notice (2026-09-01):** This run is retained as rejected diagnostic evidence only. The shared validation cohort had already been repeatedly used for architecture/threshold selection, and its patient-level errors were then used to design M4b-M4d; it is no longer an unbiased acceptance cohort. The record also lacks an immutable split hash, executable commit and record-level artifact hash list. Historical package figures below were payload-only; conservative package estimates add the frozen 1,024-byte reserve (Cand 1/2: 12,784 B; Cand 3: 13,312 B). See `20260901-130728-m2ae-m4-evidence-and-isolation-audit`.

## Identity

- Run ID: `20260901-085000-m4a-twostage-high-sensitivity-primary-model`
- Stage: `train`
- Status: `completed`
- Started/finished: `2026-09-01 08:50 CST / 2026-09-01 09:25 CST`
- Agent/operator: Antigravity
- Baseline run: `20260901-075504-m2ad-central-gate-and-50k-contract`
- Git commit: working tree
- Data version and split hash: clean M2ab lookahead-v2 cache (`runs/20260831-180114-m2ab-lookahead-contract-boundary-repair/native_cache_retry1`); validation-only isolation.
- Config/contract paths: `contracts/ec57_hybrid_metrics_contract.json`, `train/ec57/configs/candidate_twostage_m4a_*.json`
- Environment: remote GPU server `ecg-gpu-server` (GPU 0: RTX 5060 Ti, GPU 1: RTX 5060 Ti, GPU 2: RTX 4090); Python 3.10 / PyTorch 2.1; local PowerShell verification `torch_evn`.

## Problem and evidence

- Prior runs with extreme margin loss achieved high precision only by sacrificing recall (`Se=6.86%` < 90.0%).
- Goal of M4a: Train high-sensitivity primary models with the new `val_se_ge_90_plus_p` checkpoint selection criterion, maintaining parameter packages strictly below 50 KiB ($\le 51,200$ bytes).

## Optimization

- Evaluated 3 primary model candidates across 3 idle GPUs:
  1. Candidate 1 (GPU 0): `TinyECGCNN_NV` with 5-bin dilated conv, MLP-96 (10,242 params / 12,784 B conservative package, 99,520 MACs), class weight $w=1.8$, Asymmetric Focal Loss ($\gamma=1.0$), Checkpoint selection: `val_se_ge_90_plus_p`.
  2. Candidate 2 (GPU 1): `TinyECGCNN_NV` with 5-bin dilated conv, MLP-96 (10,242 params / 12,784 B conservative package, 99,520 MACs), class weight $w=2.0$, Asymmetric Margin Loss ($m=0.03, \text{penalty}=3.0$), Checkpoint selection: `val_se_ge_90_plus_p`.
  3. Candidate 3 (GPU 2): `TinyECGCNN_NV` with 4-bin dilated conv, MLP-120 (10,506 params / 13,312 B conservative package, 99,760 MACs), class weight $w=2.2$, Checkpoint selection: `val_se_ge_90_plus_p`.

## Frozen acceptance criteria

- TDD confirms model budget: deployment package $\le 51,200$ B, MACs $\le 100,000$, max activation $\le 2,048$ B.
- Validation eligibility gate (all 3 must be satisfied simultaneously):
  1. `VEB Se >= 90.0%`
  2. `VEB +P >= 95.0%`
  3. `VEB FPR <= 0.25%`
- If no threshold satisfies all three gates simultaneously, candidate must be marked `rejected`.

## Results

| Candidate | Params / Size | MACs / Beat | Package Bytes | Best Epoch | Best Operating Point under Se >= 90% | Max +P (Unconstrained) | Three-Metric Gate | Decision |
|---|---:|---:|---:|---:|---|---|---|---|
| Cand 1 (MLP-96, Focal $\gamma=1.0$) | 10,242 / 10.0 KB | 99,520 | 12,784 B | 21/33 | th=0.658: **Se=90.24%**, +P=76.41%, FPR=0.1358% (TP=1,276, FP=394) | 90.72% (th=0.997, Se=24.89%, FP=36) | 0 (FP=394 > gate) | 回到训练 |
| **Cand 2 (MLP-96, Margin $m=0.03$)** | **10,242 / 10.0 KB** | **99,520** | **12,784 B** | **21/33** | **th=0.538: Se=90.03%, +P=77.86%, FPR=0.1248% (TP=1,273, FP=362)** | **89.77% (th=0.986, Se=38.47%, FP=62)** | **0 (FP=362 > gate)** | **回到训练** |
| Cand 3 (MLP-120, Focal $\gamma=1.5$) | 10,506 / 10.3 KB | 99,760 | 13,312 B | 43/50 | th=0.663: **Se=90.03%**, +P=68.04%, FPR=0.2061% (TP=1,273, FP=598) | 87.67% (th=0.997, Se=27.16%, FP=54) | 0 (FP=598 > gate) | 回到训练 |

### Key Diagnostic Discovery from Error Breakdown
- At the $\text{Se} = 90.03\%$ operating point of Candidate 2, there are 362 residual false positives across 290,106 non-VEBs.
- **Patient concentration**: 42.3% (153/362) of all FPs belong to single patient `p02430` (who has bundle branch block / baseline wide QRS).
- **Physical feature separation**: True VEBs exhibit average `comp_ratio` of `+21.77` and `post_rr_ratio` of `+59.48`, whereas `p02430`'s wide sinus beats exhibit `comp_ratio` of only `+3.34`.
- The CNN relied too heavily on QRS morphology and failed to enforce joint gating with compensatory pause on wide-QRS sinus rhythms.

- Evidence: `docs/reports/20260901-085000-m4a-twostage-high-sensitivity-primary-model/`
- Unverified items: three-seed stability, internal test, PTQ, RTL and hardware.

## Decision

- Decision: `回到训练` (REJECTED / RETURN TO TRAINING)
- All 3 primary models successfully maintained high sensitivity ($\text{Se} \ge 90.0\%$), but baseline precision reached $\approx 77.86\%$, failing the $+P \ge 95.0\%$ gate.
- Status remains in training exploration for M4b (Compensatory Pause Gated Architecture & Bundle Branch Block Hard-Negative Mining).
