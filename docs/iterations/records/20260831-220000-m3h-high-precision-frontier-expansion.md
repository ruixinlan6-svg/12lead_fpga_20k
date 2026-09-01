# Optimization Run: `20260831-220000-m3h-high-precision-frontier-expansion`

## Identity

- Run ID: `20260831-220000-m3h-high-precision-frontier-expansion`
- Stage: `M2 high-precision frontier exploration`
- Status: `completed`
- Started/finished: `2026-08-31 22:00 CST / 2026-08-31 22:15 CST`
- Agent/operator: Antigravity
- Baseline run: `20260831-210000-m3f-2500b-expanded-capacity-exploration` Candidate 3 (2,507 params, raw max +P 94.40% at 7 FPs)
- Candidates: 3 concurrent fine-tuned frontier candidates on 2.5 KB architecture (`TinyECGCNN_NV` with MLP-11, 2,507 params, 91,870 MACs) across 3 GPUs:
  1. Candidate 1 (GPU 0): `MLP-11, Dilated Conv (d=2) + Ultra Margin (m=0.018, penalty 6.5), veb_weight 1.0, lr 3e-4, AP selection` (2,507 params, 91,870 MACs)
  2. Candidate 2 (GPU 1): `MLP-11, Dilated Conv (d=2) + Margin (m=0.020, penalty 6.0), veb_weight 1.2, lr 4e-4, AP selection` (2,507 params, 91,870 MACs)
  3. Candidate 3 (GPU 2): `MLP-11, Dilated Conv (d=2) + Extreme Margin (m=0.015, penalty 7.0), veb_weight 1.0, lr 3e-4, AP selection` (2,507 params, 91,870 MACs)

## Problem and evidence

- In M3f Candidate 3, raw model predictions reached 94.40% precision (118 TPs, 7 FPs across 291,520 validation beats).
- To evaluate whether fine-tuned negative margin ($m=0.015\text{--}0.018, \gamma=6.5\text{--}7.0$) can achieve high precision out-of-the-box, fine-tuned configurations were evaluated.

## Optimization

- Target the exact sweet spot of negative margin loss ($m=0.015\text{--}0.020, \gamma=6.0\text{--}7.0$) and class balance weights ($w=1.0\text{--}1.2$).
- Concurrently train on 3 idle GPUs using clean repaired M2ab cache (`runs/20260831-180114-m2ab-lookahead-contract-boundary-repair/native_cache_retry1`), seed 17, validation-only. Internal test set remains unopened.

## Frozen acceptance criteria

- TDD confirms model budget: all candidates = 2,507 params / 91,870 MACs ($\le 2,560$ params, $\le 100,000$ MACs).
- Validation eligibility gate (all 3 must be satisfied simultaneously):
  1. `VEB Se >= 90.0%`
  2. `VEB +P >= 95.0%`
  3. `VEB FPR <= 0.25%`
- If no threshold satisfies all three gates simultaneously, the candidate must be rejected.

## Execution

- Entry commands:
  1. Local unit tests pass (197/197 PASS)
  2. Launch 3 concurrent GPU training jobs on GPU 0, 1, 2
  3. Download report artifacts and compute threshold curves
- Hardware: remote GPU server (GPU 0: RTX 5060 Ti, GPU 1: RTX 5060 Ti, GPU 2: RTX 4090)

## Results

| Candidate | Params / Size | MACs / Beat | Best Val AP | Max +P Scanned | Se at Max +P | FPR at Max +P | TP / FP Counts | Decision |
|---|---:|---:|---:|---:|---:|---:|---|---|
| Cand 1 ($m=0.018, \gamma=6.5$) | 2,507 / 2.45 KB | 91,870 | 0.8081 | 94.12% (th=0.999) | 7.92% | 0.0024% | TP=112, FP=7 | 回到训练 |
| Cand 2 ($w=1.2, m=0.020$) | 2,507 / 2.45 KB | 91,870 | 0.8112 | 94.97% (th=0.999) | 10.68% | 0.0028% | TP=151, FP=8 | 回到训练 |
| Cand 3 ($m=0.015, \gamma=7.0$) | 2,507 / 2.45 KB | 91,870 | 0.8075 | 96.04% (th=0.999) | **6.86%** | **0.00138%** | **TP=97, FP=4** | **回到训练** |

- Audit finding:
  - In Candidate 3 at th=0.999, precision (+P = 96.04%) and false positive rate (FPR = 0.00138%) met their respective numbers, but **sensitivity was only 6.86%** (missing 93.14% of true VEBs).
  - Because `VEB Se < 90.0%`, Candidate 3 **FAILS** the full three-metric frozen validation gate.
  - Previous acceptance and freeze decisions are officially **REVOKED**.
- Evidence: `docs/reports/20260831-220000-m3h-high-precision-frontier-expansion/candidate3_tp5_mlp11_m0015_p70/`
- Unverified items: internal test, external databases, quantization, RTL and hardware.

## Decision

- Decision: `回到训练` (REJECTED / RETURN TO TRAINING)
- No candidate met `VEB Se >= 90.0%`, `VEB +P >= 95.0%`, and `VEB FPR <= 0.25%` simultaneously.
- Freezing and deployment are prohibited; status returned to active training exploration.
