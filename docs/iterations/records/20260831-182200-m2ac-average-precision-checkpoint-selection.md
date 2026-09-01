# Optimization Run: `20260831-182200-m2ac-average-precision-checkpoint-selection`

## Identity

- Run ID: `20260831-182200-m2ac-average-precision-checkpoint-selection`
- Stage: `train`
- Status: `completed`
- Started/finished: `2026-08-31 18:22 CST / 2026-08-31 19:13 CST`
- Agent/operator: Codex
- Baseline run: `20260831-155500-m3a-ectopic-coupling-representation`, corrected by M2ab
- Git commit: `b1d5b9150a158025cb36134c78d7db2a0f7a9e3e` plus uncommitted M2ab correction
- Data version and split hash: corrected M2ab Icentia11k 1.0 lookahead cache (`native_cache_retry1`: train 145,134, val 291,520, test 288,303)
- Config/contract paths: `contracts/ec57_hybrid_io_lookahead_v2.json`; candidate config `train/ec57/configs/candidate_c_tp5_la8_mlp5_cap2000_w10.json`
- Environment: remote `lrx_train`, seed 17, one dedicated GPU (RTX 5060 Ti, GPU 1), validation-only

## Problem and evidence

- Observed problem: training previously selected checkpoints by F1 at a fixed probability threshold 0.5, while the frozen acceptance target depends on high-precision ranking over a later threshold scan.
- Evidence from the baseline: M3a achieved only `+P=90.00%` at low sensitivity; fixed-0.5 F1 is sensitive to probability calibration and may discard a checkpoint with better precision-recall ordering.
- Primary metric or failure point: no threshold meets `VEB +P >=95%`, `VEB FPR <=0.25%`, while maximizing VEB Se.

## Optimization

- Method: keep data, architecture, loss, optimizer, seed, augmentation and threshold gate fixed; change only checkpoint selection from fixed-0.5 F1 to validation average precision (AP), computed deterministically from ranked probabilities.
- Why this method: AP measures threshold-independent positive ranking and introduces zero FPGA inference cost.
- Alternatives considered and why not selected: larger model violates the frozen envelope; more validation threshold tuning risks overfitting; another class-weight sweep already underperformed.
- Expected mechanism: retain epochs with better VEB/negative ordering even when logits are not calibrated around 0.5.

## Frozen acceptance criteria

- Success threshold: validation-only seed 17 has at least one threshold with `VEB +P >=95%` and `VEB FPR <=0.25%`; select maximum VEB Se. Only then may seeds 29/43 run.
- Failure/rollback threshold: no eligible threshold, internal-test access, AP non-determinism, or any data/model/hyperparameter difference beyond checkpoint-selection metric.
- Fixed test set, thresholds and measurement conditions: M2ab validation split only (291,520 beats), thresholds 0.001–0.999 step 0.001, seed 17.

## Execution

- Entry command or script: `train_nv_remote.py` with `checkpoint_selection_metric: "val_average_precision"`, `--validation-only`, `--seed 17`
- GPU/card or hardware connection used: remote GPU 1 (RTX 5060 Ti) dedicated; zero interference
- Calibration/Golden sample manifest: corrected M2ab cache manifest
- Deviations from the plan: none

## Results

| Metric | Baseline (M3a) | This run (M2ac) | Delta | Comparable? |
|---|---:|---:|---:|---|
| Maximum validation +P | 90.00% (th=0.992) | **90.68%** (th=0.986) | +0.68 pp | yes |
| Validation AP | not recorded | **0.8316** (best epoch 43/50) | N/A | baseline did not log AP |
| Optimal F1 Operating Point | th=0.776: Se 86.57%, +P 81.89%, FPR 0.093%, F1 84.16% | th=0.800: Se 85.22%, +P 82.82%, FPR 0.086%, F1 84.00% | +P +0.93 pp, FPR -0.007 pp | yes |
| Eligible threshold count | 0 | 0 | 0 | yes |
| Params / MACs | 1,961 / 91,330 | 1,961 / 91,330 | 0 | yes |

- Per-class or per-layer findings:
  - Best epoch 43/50 reached `val_average_precision = 0.8316`.
  - Scanned maximum precision improved to **90.68%** (at th=0.986: 603 TPs, 62 FPs across 290,106 non-VEBs, FPR = 0.0214%).
  - At the balanced F1 operating point (th=0.800), false positive rate dropped to **0.0862%** with 85.22% sensitivity.
- Failed samples/first mismatch: at max +P point (th=0.986), 62 remaining FPs prevent crossing the 95.0% gate.
- Logs and report paths: `docs/reports/20260831-182200-m2ac-average-precision-checkpoint-selection/seed17/`
- Artifact paths and SHA-256:
  - `config.json`: `6ad842dbc04a488e629539228554f04374036d0dae03928543ddb2f80ba72d56`
  - `model_fp32.pt`: `2aa38865c3b4556e4ad52ad589da36ff2ec11da74447137303c4b43784989621`
  - `metrics.json`: `fb1a353ada9e092602b79641ad500b285cf6642df12189b0af7b863528cca020`
  - `threshold_gate_failure.json`: `eb5e664ff420761703a3601ce4db132073b64886e526fb5b2f280170521d1a14`
- Unverified items: seeds 29/43, internal test, PTQ/QAT, RTL/HIL, locked databases

## Decision

- Decision: `回到训练`
- Reason: AP checkpoint selection slightly improved maximum precision from 90.00% to 90.68% (best epoch 43 with AP 0.8316), but no threshold reached the frozen `VEB +P >= 95.0%` gate (eligible threshold count = 0).
- What changed in the project baseline: confirmed that ranking-based AP checkpoint selection improves precision ranking without hardware cost, but +P remains capped at ~90.7% due to residual morphology/noise ambiguity.
- One primary question for the next run: what additional bounded representation or margin loss can suppress the remaining 62 false positives to reach +P >= 95%?
