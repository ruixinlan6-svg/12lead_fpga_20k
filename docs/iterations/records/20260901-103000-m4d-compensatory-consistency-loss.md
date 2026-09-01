# Optimization Run: `20260901-103000-m4d-compensatory-consistency-loss`

> **Central audit notice (2026-09-01):** This run is rejected diagnostic evidence and is not admissible as an unbiased validation gate because its loss was designed from M4c validation-patient errors. The record lacks an immutable split hash, executable commit and record-level artifact hash list. `DualBranchECGCNN_NV` has a fixed 32-unit classifier head; corrected 32/32 and 40/40 estimates are respectively 96,832/98,304 MAC per beat and 10,096/11,760 B conservative package. See `20260901-130728-m2ae-m4-evidence-and-isolation-audit`.

## Identity

- Run ID: `20260901-103000-m4d-compensatory-consistency-loss`
- Stage: `train`
- Status: `completed`
- Started/finished: `2026-09-01 10:30 CST / 2026-09-01 10:50 CST`
- Agent/operator: Antigravity
- Baseline run: `20260901-100000-m4c-dual-branch-timing-morphology-fusion` Candidate 2 (Se 90.10%, +P 82.51%, FPR 0.0931%, FP=270)
- Git commit: working tree
- Data version and split hash: clean M2ab lookahead-v2 cache (`runs/20260831-180114-m2ab-lookahead-contract-boundary-repair/native_cache_retry1`); validation-only isolation.
- Config/contract paths: `contracts/ec57_hybrid_metrics_contract.json`, `train/ec57/configs/candidate_twostage_m4d_*.json`
- Environment: remote GPU server `ecg-gpu-server` (GPU 0: RTX 5060 Ti, GPU 1: RTX 5060 Ti, GPU 2: RTX 4090); Python 3.10 / PyTorch 2.1; local PowerShell verification `torch_evn`.

## Problem and evidence

- In M4c, `DualBranchECGCNN_NV` advanced +P to 82.51% (FP=270), with 74.1% of remaining false alarms belonging to two specific patients `p02430` (152 FPs) and `p03217` (48 FPs).
- Goal of M4d: Evaluate `CompensatoryConsistencyLoss` which applies explicit quadratic penalties to normal sinus beats without compensatory pause ($\text{comp\_ratio} \le 0$).

## Optimization

- Deployed 3 concurrent candidates across 3 idle GPUs:
  1. Candidate 1 (GPU 0): `DualBranchECGCNN_NV` (32-dim Morph, 32-dim Timing, fixed 32-dim Head, 7,554 params / 10,096 B conservative package, 96,832 MACs), `CompensatoryConsistencyLoss` ($m=0.020$, base penalty=3.5, wide=6.0, comp_neg=8.0, $w=2.2$).
  2. Candidate 2 (GPU 1): `DualBranchECGCNN_NV` (32-dim Morph, 32-dim Timing, fixed 32-dim Head, 7,554 params / 10,096 B conservative package, 96,832 MACs), `CompensatoryConsistencyLoss` ($m=0.015$, base penalty=4.0, wide=8.0, comp_neg=12.0, $w=2.2$).
  3. Candidate 3 (GPU 2): `DualBranchECGCNN_NV` (40-dim Morph, 40-dim Timing, fixed 32-dim Head, 9,042 params / 11,760 B conservative package, 98,304 MACs), `CompensatoryConsistencyLoss` ($m=0.018$, base penalty=4.0, wide=7.0, comp_neg=10.0, $w=2.2$).

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
| Cand 1 (DualBranch comp=8.0) | 7,554 / 7.4 KB | 96,832 | 10,096 B | 18/30 | th=0.457: Se=90.03%, +P=81.24%, FPR=0.1013% (TP=1,273, FP=294) | 90.41% (th=0.996, Se=21.99%, FP=33) | 0 (FP=294 > gate) | 回到训练 |
| Cand 2 (DualBranch comp=12.0) | 7,554 / 7.4 KB | 96,832 | 10,096 B | 18/30 | th=0.390: Se=90.03%, +P=80.93%, FPR=0.1034% (TP=1,273, FP=300) | 91.91% (th=0.998, Se=17.68%, FP=22) | 0 (FP=300 > gate) | 回到训练 |
| Cand 3 (DualBranch 40/40 comp=10.0) | 9,042 / 8.8 KB | 98,304 | 11,760 B | 29/41 | th=0.339: Se=90.03%, +P=76.41%, FPR=0.1355% (TP=1,273, FP=393) | 91.53% (th=0.986, Se=34.37%, FP=45) | 0 (FP=393 > gate) | 回到训练 |

### Key Diagnostic Discovery
- Deep intra-patient analysis revealed that Patient `p02430` alone contains 75.2% (1,063/1,414) of all true VEBs in the validation set.
- The model successfully identifies 953 true VEBs in `p02430` with a 98.83% patient specificity (152 FPs out of 12,819 non-VEBs).
- The overall validation FPR across all 24 patients is 0.0931% (specificity 99.907%), but because the global VEB prevalence in the validation set is only 0.48% (1,414 : 290,106), reaching +P >= 95.0% under Se >= 90% strictly requires global FP <= 67 (FPR <= 0.023%).
- M4c Candidate 2 remains the best performing checkpoint (+P 82.51%, FPR 0.0931%, F1 86.25%).

- Evidence: `docs/reports/20260901-103000-m4d-compensatory-consistency-loss/`
- Unverified items: three-seed stability, internal test, PTQ, RTL and hardware.

## Decision

- Decision: `回到训练` (REJECTED / RETURN TO TRAINING)
- While the models have achieved substantial, verifiable progress (+P 77.86% -> 79.74% -> 82.51%, FPR 0.1248% -> 0.1117% -> 0.0931%), the three-metric gate has not yet been satisfied simultaneously.
- Status strictly remains in training exploration.
