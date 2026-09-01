# Optimization Run: `20260831-203000-m3d-dilated-margin-hyperparameter-tuning`

## Identity

- Run ID: `20260831-203000-m3d-dilated-margin-hyperparameter-tuning`
- Stage: `M2 architecture & loss parameter tuning`
- Status: `completed`
- Started/finished: `2026-08-31 20:30 CST / 2026-08-31 20:38 CST`
- Agent/operator: Antigravity
- Baseline run: `20260831-201000-m3c-ultra-margin-and-dilated-combination` Candidate 2 (AP 0.8487, max +P 92.62%, 38 FPs) & Candidate 1 (max +P 92.67%, 17 FPs)
- Candidates: 3 concurrent candidates across 3 GPUs testing Dilated Backbone fine-tuned margins and capacity within the 2,048 parameter envelope:
  1. Candidate 1 (GPU 0): `5-bin, 8 features, MLP-5, Dilated Conv (d=2) + Sweet-spot Margin (m=0.025, penalty 5.0), AP selection` (1,961 params, 91,330 MACs)
  2. Candidate 2 (GPU 1): `4-bin, 8 features, MLP-7, Dilated Conv (d=2) + Tight Margin (m=0.03, penalty 4.0), AP selection` (2,031 params, 91,398 MACs)
  3. Candidate 3 (GPU 2): `5-bin, 8 features, MLP-5, Dilated Conv (d=2) + Ultra Margin (m=0.02, penalty 5.0), class weight 1.1, AP selection` (1,961 params, 91,330 MACs)

## Problem and evidence

- In M3c, combining Dilated Conv ($d=2$) and Margin Loss achieved the highest AP in project history (0.8487), and Ultra Margin ($m=0.02$) drove the absolute FP count down to only 17 across 290k non-VEBs.
- The remaining gap to $+P \ge 95.0\%$ was only 6 false positives ($17 \to \le 11$).
- Fine-tuning the margin parameter $m \in [0.02, 0.025]$, scaling MLP hidden capacity to 7, and balancing class weights sought to close the final 6 FP gap.

## Optimization

- Candidate 1: 5-bin Dilated ($d=2$) with $m=0.025, \gamma=5.0$.
- Candidate 2: 4-bin Dilated ($d=2$) with MLP hidden dimension 7 (2,031 params).
- Candidate 3: 5-bin Dilated ($d=2$) with $m=0.02, \gamma=5.0$ and positive weight 1.1.
- Concurrently train on 3 idle GPUs using clean repaired M2ab cache (`runs/20260831-180114-m2ab-lookahead-contract-boundary-repair/native_cache_retry1`), seed 17, validation-only. Internal test set remains unopened.

## Frozen acceptance criteria

- TDD confirms model budget: Candidate 1 & 3 = 1,961 params / 91,330 MACs; Candidate 2 = 2,031 params / 91,398 MACs (all $\le 2,048$ params, $\le 100,000$ MACs).
- Validation eligibility gate: `VEB +P >= 95.0%` and `VEB FPR <= 0.25%`.
- If an eligible threshold exists, select the threshold maximizing `VEB Se`.
- If seed 17 passes, proceed to seeds 29 and 43.
- If seed 17 fails across all 3 candidates, record diagnostic curves and analyze next steps under `/goal`.

## Execution

- Entry commands:
  1. Local unit tests pass (195/195 PASS)
  2. Sync updated code and configs to remote GPU server
  3. Launch 3 concurrent GPU training jobs on GPU 0, 1, 2
  4. Download report artifacts and compute threshold curves
- Hardware: remote GPU server (GPU 0: RTX 5060 Ti, GPU 1: RTX 5060 Ti, GPU 2: RTX 4090)

## Results

| Candidate | Params / Budget | MACs / Budget | Best Val AP | Optimal F1 Operating Point | Max +P Scanned | Eligible Gates |
|---|---:|---:|---:|---|---:|---|
| **Cand 1 (Dilated d=2, Margin m=0.025, p=5.0)** | **1,961 / 2,048** | **91,330 / 100k** | **0.8651** | **th=0.709: Se 88.61%, +P 85.06%, FPR 0.0758%, F1 86.80%** | **93.22%** (th=0.996, **FP=25**, TP=344, FPR=0.0086%) | **0** |
| Cand 2 (4-bin MLP-7, Dilated d=2, Margin m=0.03) | 2,031 / 2,048 | 91,398 / 100k | 0.8232 | th=0.592: Se 85.93%, +P 77.54%, FPR 0.1213%, F1 81.52% | 89.24% (th=0.999, FP=31, TP=257, FPR=0.0107%) | 0 |
| **Cand 3 (Dilated d=2, w=1.1, Margin m=0.02, p=5.0)** | **1,961 / 2,048** | **91,330 / 100k** | **0.8645** | **th=0.728: Se 89.96%, +P 82.81%, FPR 0.0910%, F1 86.24%** | **92.37%** (th=0.998, **FP=30**, TP=363, FPR=0.0103%) | **0** |

- Diagnostic findings:
  - **Candidate 1 (Dilated Conv $d=2$ + Sweet-spot Margin $m=0.025, \gamma=5.0$)** set new all-time records across all major validation benchmarks:
    - **Best Val AP**: **0.8651** (up from 0.8487 in M3c, and 0.8316 in M2ac).
    - **Max +P**: **93.22%** (at th=0.996: 344 TPs, only **25 FPs** across 290,106 non-VEBs, FPR = **0.0086%**).
    - **At th=0.999**: **+P 93.10%**, **189 TPs**, only **14 FPs** across the entire 290k cohort (FPR = **0.0048%**).
    - **Optimal F1 Operating Point**: th=0.709 $\to$ **Se 88.61%** (1,253 / 1,414 true VEBs), **+P 85.06%**, **FPR 0.0758%** (220 FPs), **F1 86.80%** (all-time highest F1).
    - **Max Se under FPR $\le 0.25\%$**: th=0.423 $\to$ **Se 94.34%** (1,334 / 1,414 true VEBs detected).
  - The remaining gap to cross the $+P \ge 95.0\%$ gate has now shrunk to **only 5 false positives** ($14 \to 9$ at 189 TPs) and **7 false positives** ($25 \to 18$ at 344 TPs).

- Evidence: `docs/reports/20260831-203000-m3d-dilated-margin-hyperparameter-tuning/`
- Unverified items: seeds 29/43, internal test, external databases, quantization, RTL and hardware.

## Decision

- Decision: `回到训练`
- Candidate 1 confirmed as the new undisputed project state-of-the-art (AP 0.8651, max +P 93.22%, F1 86.80%).
- Next step: Address the final 5 false positives via Direction 2 (direct physiological pause gating) or refined multi-seed exploration.
