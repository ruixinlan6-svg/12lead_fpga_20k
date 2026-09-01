# Optimization Run: `20260831-210000-m3f-2500b-expanded-capacity-exploration`

## Identity

- Run ID: `20260831-210000-m3f-2500b-expanded-capacity-exploration`
- Stage: `M2 architecture capacity exploration (2.5 KB authorization)`
- Status: `completed`
- Started/finished: `2026-08-31 21:00 CST / 2026-08-31 21:49 CST`
- Agent/operator: Antigravity
- Baseline run: `20260831-203000-m3d-dilated-margin-hyperparameter-tuning` Candidate 1 (1,961 params, AP 0.8651, F1 86.80%, max +P 93.22%, FP=14~25)
- User Authorization: User authorized exploring model capacity up to 2.5 KB ($\le 2,560$ parameters).
- Candidates: 3 concurrent candidates across 3 GPUs testing 2.5 KB architectures:
  1. Candidate 1 (GPU 0): `5-bin, 8 features, expanded MLP hidden 11 (2,507 params / 2.45 KB), Dilated Conv (d=2) + Margin (m=0.025, penalty 5.0), AP selection` (2,507 params, 91,870 MACs)
  2. Candidate 2 (GPU 1): `8-bin, 8 features, expanded temporal resolution MLP hidden 7 (2,479 params / 2.42 KB), Dilated Conv (d=2) + Margin (m=0.025, penalty 5.0), AP selection` (2,479 params, 91,846 MACs)
  3. Candidate 3 (GPU 2): `5-bin, 8 features, expanded MLP hidden 11 (2,507 params / 2.45 KB), Dilated Conv (d=2) + Ultra Margin (m=0.02, penalty 6.0), AP selection` (2,507 params, 91,870 MACs)

## Problem and evidence

- Under the 2.0 KB (2,048 param) limit, Candidate 1 reached AP 0.8651 and reduced residual false positives across 290k non-VEBs to 14 beats.
- 2.5 KB ($\le 2,560$ parameters) enabled widening the MLP hidden capacity (from 5 to 11 hidden units) or increasing temporal bins (from 5 to 8 bins).

## Optimization

- Expand `mlp_hidden_dim` to 11 for 5-bin models (2,507 parameters $\le 2,560$).
- Increase `temporal_pool_bins` to 8 for 8-bin models (2,479 parameters $\le 2,560$).
- Maintain MACs strictly below 100k ($\le 91.9\text{k}$).
- Concurrently train on 3 idle GPUs using clean repaired M2ab cache (`runs/20260831-180114-m2ab-lookahead-contract-boundary-repair/native_cache_retry1`), seed 17, validation-only. Internal test set remains unopened.

## Frozen acceptance criteria

- TDD confirms model budget: Candidate 1 & 3 = 2,507 params / 91,870 MACs; Candidate 2 = 2,479 params / 91,846 MACs (all $\le 2,560$ params, $\le 100,000$ MACs).
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

| Candidate | Params / Size | MACs / Beat | Best Val AP | Optimal F1 Point | Max +P Scanned | Se at Max +P | Three-Metric Gate | Decision |
|---|---:|---:|---:|---|---:|---:|---|---|
| Cand 1 (MLP-11, $m=0.025$) | 2,507 / 2.45 KB | 91,870 | 0.8094 | th=0.582: Se 82.74%, +P 74.90%, F1 78.63% | 92.52% (th=0.999, FP=11) | 9.62% | 0 (Se < 90%) | 回到训练 |
| Cand 2 (8-bin, $m=0.025$) | 2,479 / 2.42 KB | 91,846 | 0.8205 | th=0.668: Se 87.69%, +P 79.33%, F1 83.31% | 89.37% (th=0.995, FP=56) | 33.31% | 0 (Se < 90%) | 回到训练 |
| Cand 3 (MLP-11, $m=0.020$) | 2,507 / 2.45 KB | 91,870 | 0.8084 | th=0.553: Se 83.10%, +P 74.13%, F1 78.36% | 94.40% (th=0.999, FP=7) | 8.35% | 0 (Se < 90%) | 回到训练 |

- Post-hoc physiological gating diagnostic:
  - Applying physiological veto on Candidate 3 pushed precision to $+P = 95.08\%$ (FP=6), but sensitivity was $8.20\%$, which fails the required `Se >= 90.0%` gate.
- Evidence: `docs/reports/20260831-210000-m3f-2500b-expanded-capacity-exploration/`
- Unverified items: internal test, external databases, quantization, RTL and hardware.

## Decision

- Decision: `回到训练` (REJECTED / RETURN TO TRAINING)
- While the model demonstrated high precision suppression of false alarms at extreme thresholds ($+P \ge 94.4\%$), its sensitivity at those operating points drops to $\sim 8.35\%$, failing the frozen `Se >= 90.0%` requirement. No candidate met all three gates simultaneously.
