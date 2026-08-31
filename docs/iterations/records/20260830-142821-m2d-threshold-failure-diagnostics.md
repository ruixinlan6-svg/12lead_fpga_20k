# Optimization Run: `20260830-142821-m2d-threshold-failure-diagnostics`

## Identity

- Run ID: `20260830-142821-m2d-threshold-failure-diagnostics`
- Stage: `M2 validation diagnostics`
- Status: `completed`
- Started/finished: 2026-08-30 14:28 CST / 2026-08-30 14:41 CST
- Agent/operator: Codex
- Baseline run: `20260830-141150-m2c-pilot-candidate-ablation`
- Data/model search space: unchanged native M2b pilot cache and unchanged frozen A/B/C definitions, seed 17

## Problem and evidence

- A/B/C all failed the formal validation gate, but the fail-fast exception occurred before model, history and threshold-table artifacts were written.
- Without the best near-miss confusion counts and training curves, changing loss, preprocessing or architecture would be guesswork.
- Internal-test was not loaded and remains sealed.

## Optimization

- Method: make threshold-gate failure an auditable exception carrying the complete 999-point threshold scan and near-miss summaries; always save the rejected checkpoint, config, train-only normalization, training history, diagnostics and SHA-256 manifest before returning failure.
- Re-run A/B/C with the same data, seed, GPUs and hyperparameters solely to recover comparable diagnostics.
- Why: identify whether failure is primarily sensitivity, precision/FPR, calibration, or unstable feature scaling before selecting the next permitted M2 optimization.
- Alternatives rejected: lowering the gate, using internal-test, ranking by accuracy/AUROC, or changing architecture before diagnostics.

## Frozen acceptance criteria

- A rejected candidate still produces a hash-complete evidence package with `status=rejected`, all threshold counts, best-F1 diagnostic point, best point under the FPR constraint, and best point under the +P constraint.
- The raised exception remains fail-closed; rejected checkpoints are marked non-freezable.
- Data and normalization hashes match M2b; internal-test file is not opened.
- Three runs reproduce the gate decision, or any changed decision is explained by a code/hash difference.
- This diagnostic run cannot accept M2 or select a model by itself.

## Results

- All three seed-17 validation-only runs reproduced rejection; internal-test was not loaded.
- Each rejected package contains 999 thresholds, model, config, train-only normalization, history, non-freezable status and SHA-256 manifest. Eighteen manifest entries were independently checked with zero mismatch.
- Candidate A: 12 epochs, best epoch 4. Best-F1 point `threshold=0.613`, `TP/FN/FP/TN=235/1180/928/289246`, Se `16.608%`, +P `20.206%`, FPR `0.3198%`. Under the FPR gate its best Se was only `13.781%` with +P `21.335%`.
- Candidate B: 44 epochs, best epoch 36. Even at `threshold=0.999`, counts were `981/434/5459/284715`, Se `69.329%`, +P `15.233%`, FPR `1.8813%`; no scanned threshold met even the FPR constraint alone.
- Candidate C: 50 epochs, best epoch 48. At `threshold=0.999`, counts were `948/467/1377/288797`, Se `66.996%`, +P `40.774%`, FPR `0.4745%`; no scanned threshold met the FPR constraint alone.
- B/C probabilities remain saturated at the maximum frozen scan threshold. Their shared four int8 scalar features are concatenated directly into the FP32 head without dequantization, while A omits those features and does not show the same saturation pattern.
- Evidence: `docs/reports/20260830-142821-m2d-threshold-failure-diagnostics/validation/`.

## Decision

- Decision: `接受诊断；回到训练`
- Reason: diagnostic evidence is complete, but all candidates remain below gate. The next isolated change is FP32 input dequantization; loss and architecture remain fixed.
