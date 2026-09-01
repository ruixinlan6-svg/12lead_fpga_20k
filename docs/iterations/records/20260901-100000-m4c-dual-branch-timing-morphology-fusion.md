# Optimization Run: `20260901-100000-m4c-dual-branch-timing-morphology-fusion`

> **Central audit notice (2026-09-01):** This run is rejected diagnostic evidence and is not admissible as an unbiased validation gate because its design follows validation-error mining in M4a/M4b. The record lacks an immutable split hash, executable commit and record-level artifact hash list. `DualBranchECGCNN_NV` has a fixed 32-unit classifier head; corrected 24/24 and 32/32 resource estimates are respectively 95,360 and 96,832 MAC/beat, with conservative packages of 8,432 B and 10,096 B. See `20260901-130728-m2ae-m4-evidence-and-isolation-audit`.

## Identity

- Run ID: `20260901-100000-m4c-dual-branch-timing-morphology-fusion`
- Stage: `train`
- Status: `completed`
- Started/finished: `2026-09-01 10:00 CST / 2026-09-01 10:25 CST`
- Agent/operator: Antigravity
- Baseline run: `20260901-093000-m4b-bilinear-gating-and-hard-negative-mining` Candidate 1 (Se 90.17%, +P 79.74%, FP=324, Val AP=0.8482)
- Git commit: working tree
- Data version and split hash: clean M2ab lookahead-v2 cache (`runs/20260831-180114-m2ab-lookahead-contract-boundary-repair/native_cache_retry1`); validation-only isolation.
- Config/contract paths: `contracts/ec57_hybrid_metrics_contract.json`, `train/ec57/configs/candidate_twostage_m4c_*.json`
- Environment: remote GPU server `ecg-gpu-server` (GPU 0: RTX 5060 Ti, GPU 1: RTX 5060 Ti, GPU 2: RTX 4090); Python 3.10 / PyTorch 2.1; local PowerShell verification `torch_evn`.

## Problem and evidence

- In M4b, Candidate 1 achieved +P 79.74% (FP=324), but the 80-dim morphology vector still dominated the 8 scalar timing features.
- Goal: Deploy `DualBranchECGCNN_NV` to project morphology and timing features into equal-capacity non-linear embeddings (24~32 dim) with multiplicative gating.

## Optimization

- Deployed 3 concurrent candidates across 3 idle GPUs:
  1. Candidate 1 (GPU 0): `DualBranchECGCNN_NV` (24-dim Morph, 24-dim Timing, fixed 32-dim Head, 6,066 params / 8,432 B conservative package, 95,360 MACs), Hard-Negative Wide-QRS Mining Loss ($m=0.025$, base penalty=3.5, wide penalty=6.0, $w=2.0$).
  2. **Candidate 2 (GPU 1)**: `DualBranchECGCNN_NV` (32-dim Morph, 32-dim Timing, fixed 32-dim Head, 7,554 params / 10,096 B conservative package, 96,832 MACs), Hard-Negative Wide-QRS Mining Loss ($m=0.025$, base penalty=4.0, wide penalty=8.0, $w=2.2$).
  3. Candidate 3 (GPU 2): `DualBranchECGCNN_NV` (24-dim Morph, 24-dim Timing, fixed 32-dim Head, 6,066 params / 8,432 B conservative package, 95,360 MACs), Asymmetric Margin Loss ($m=0.025$, penalty=4.0, $w=2.2$).

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
| Cand 1 (DualBranch 24/24) | 6,066 / 5.9 KB | 95,360 | 8,432 B | 32/44 | th=0.408: Se=90.10%, +P=78.64%, FPR=0.1193% (TP=1,274, FP=346) | 90.41% (th=0.976, Se=43.35%, FP=65) | 0 (FP=346 > gate) | 回到训练 |
| **Cand 2 (DualBranch 32/32)** | **7,554 / 7.4 KB** | **96,832** | **10,096 B** | **21/33** | **th=0.643: Se=90.10%, +P=82.51%, FPR=0.0931% (TP=1,274, FP=270)** | **89.34% (th=0.999, Se=23.13%, FP=39)** | **0 (FP=270 > gate)** | **回到训练** |
| Cand 3 (DualBranch 24/24 Margin) | 6,066 / 5.9 KB | 95,360 | 8,432 B | 36/48 | th=0.453: Se=90.03%, +P=79.66%, FPR=0.1120% (TP=1,273, FP=325) | 91.75% (th=0.986, Se=37.77%, FP=48) | 0 (FP=325 > gate) | 回到训练 |

### Key Improvements in Candidate 2
- +P under $\text{Se} \ge 90\%$ improved from **$79.74\%$ (M4b Cand 1)** to **$82.51\%$ (M4c Cand 2)** (**$+2.77\%$**).
- FPR dropped below $0.10\%$ to **$0.0931\%$** (historic first for $\text{Se} \ge 90\%$).
- Total FP count reduced from **324 down to 270** (**54 false positives eliminated**).
- Val F1 reached **86.25%** and Val AP reached **0.8536**.
- Hardware footprint after central correction: 10,096-byte conservative package and 96,832 MACs ($\le 100,000$).

- Evidence: `docs/reports/20260901-100000-m4c-dual-branch-timing-morphology-fusion/`
- Unverified items: three-seed stability, internal test, PTQ, RTL and hardware.

## Decision

- Decision: `回到训练` (REJECTED / RETURN TO TRAINING)
- Precision reached $82.51\%$ at $\text{Se}=90.10\%$, showing significant continuous progress toward $+P \ge 95.0\%$ (residual gap: 203 FPs, 74.1% of which reside in 2 patients `p02430` and `p03217`).
- Status proceeds to M4d (Compensatory Consistency & Sinus Arrhythmia Contrastive Loss on DualBranch-32).
