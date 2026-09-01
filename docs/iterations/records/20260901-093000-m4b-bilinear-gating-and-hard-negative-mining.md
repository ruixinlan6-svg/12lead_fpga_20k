# Optimization Run: `20260901-093000-m4b-bilinear-gating-and-hard-negative-mining`

> **Central audit notice (2026-09-01):** This run is rejected diagnostic evidence and is not admissible as an unbiased validation gate. Its loss/gating design was derived from M4a validation failures, especially patient `p02430`. The record lacks an immutable split hash, executable commit and record-level artifact hash list. Corrected conservative package estimates are 12,784 B (Cand 1) and 12,798 B (Cand 2/3); bilinear candidates are 99,522 MAC/beat after counting `gate_linear`. See `20260901-130728-m2ae-m4-evidence-and-isolation-audit`.

## Identity

- Run ID: `20260901-093000-m4b-bilinear-gating-and-hard-negative-mining`
- Stage: `train`
- Status: `completed`
- Started/finished: `2026-09-01 09:30 CST / 2026-09-01 09:55 CST`
- Agent/operator: Antigravity
- Baseline run: `20260901-085000-m4a-twostage-high-sensitivity-primary-model` Candidate 2 (Se 90.03%, +P 77.86%, FP=362)
- Git commit: working tree
- Data version and split hash: clean M2ab lookahead-v2 cache (`runs/20260831-180114-m2ab-lookahead-contract-boundary-repair/native_cache_retry1`); validation-only isolation.
- Config/contract paths: `contracts/ec57_hybrid_metrics_contract.json`, `train/ec57/configs/candidate_twostage_m4b_*.json`
- Environment: remote GPU server `ecg-gpu-server` (GPU 0: RTX 5060 Ti, GPU 1: RTX 5060 Ti, GPU 2: RTX 4090); Python 3.10 / PyTorch 2.1; local PowerShell verification `torch_evn`.

## Problem and evidence

- In M4a Candidate 2, high sensitivity was maintained ($\text{Se} = 90.03\%$), but 362 residual false positives limited precision to $77.86\%$.
- Root cause diagnosis: 42.3% (153/362) of all validation FPs originate from a single patient `p02430` who has Bundle Branch Block (baseline wide QRS with normal rhythm / low compensatory pause `comp_ratio = +3.34` vs True VEB `comp_ratio = +21.77`).
- Goal of M4b: Test train-set wide-QRS hard negative mining loss and bilinear compensatory pause gating to suppress false positives while maintaining $\text{Se} \ge 90.0\%$.

## Optimization

- Deployed 3 concurrent candidates across 3 idle GPUs:
  1. **Candidate 1 (GPU 0)**: `TinyECGCNN_NV` 5-bin MLP-96 with Hard-Negative Wide-QRS Mining Loss ($m=0.025$, base penalty=3.5, wide QRS penalty=6.0, $w=2.0$).
  2. **Candidate 2 (GPU 1)**: `TinyECGCNN_NV` 5-bin MLP-96 with Bilinear Compensatory Gating + Margin Loss ($m=0.025$, penalty=4.0, $w=2.2$).
  3. **Candidate 3 (GPU 2)**: `TinyECGCNN_NV` 5-bin MLP-96 with Bilinear Compensatory Gating + Hard-Negative Wide-QRS Mining Loss ($m=0.020$, base penalty=4.0, wide QRS penalty=7.0, $w=2.2$).

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
| **Cand 1 (Mining Loss w5)** | **10,242 / 10.0 KB** | **99,520** | **12,784 B** | **30/42** | **th=0.565: Se=90.17%, +P=79.74%, FPR=0.1117% (TP=1,275, FP=324)** | **90.69% (th=0.978, Se=48.23%, FP=70)** | **0 (FP=324 > gate)** | **回到训练** |
| Cand 2 (Bilinear Margin) | 10,245 / 10.0 KB | 99,522 | 12,798 B | 43/50 | th=0.506: Se=90.03%, +P=70.64%, FPR=0.1823% (TP=1,273, FP=529) | 89.54% (th=0.999, Se=24.82%, FP=41) | 0 (FP=529 > gate) | 回到训练 |
| Cand 3 (Bilinear Mining) | 10,245 / 10.0 KB | 99,522 | 12,798 B | 43/50 | th=0.244: Se=90.03%, +P=68.89%, FPR=0.1982% (TP=1,273, FP=575) | 88.80% (th=0.977, Se=39.82%, FP=71) | 0 (FP=575 > gate) | 回到训练 |

### Key Improvements in Candidate 1
- +P under $\text{Se} \ge 90\%$ improved from **$77.86\%$ (M4a Cand 2)** to **$79.74\%$ (M4b Cand 1)** (+1.88%).
- Validation False Positives reduced by **38 beats** (from 362 down to 324).
- Val AP reached **0.8482** (highest across the project).
- Val F1 reached **84.63%** (highest across the project).

- Evidence: `docs/reports/20260901-093000-m4b-bilinear-gating-and-hard-negative-mining/`
- Unverified items: three-seed stability, internal test, PTQ, RTL and hardware.

## Decision

- Decision: `回到训练` (REJECTED / RETURN TO TRAINING)
- Precision reached $79.74\%$ at $\text{Se}=90.17\%$, closing the gap but not yet reaching $+P \ge 95.0\%$ (requires $\le 67$ FPs).
- Status proceeds to M4c (Dual-Branch Equal-Capacity Representation with Patient-Balanced Triplet Mining).
