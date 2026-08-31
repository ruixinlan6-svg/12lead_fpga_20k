# Optimization Run: `20260830-144058-m2e-fp32-input-dequantization`

## Identity

- Run ID: `20260830-144058-m2e-fp32-input-dequantization`
- Stage: `M2 FP32 training`
- Status: `completed`
- Started/finished: 2026-08-30 14:41 CST / 2026-08-30 14:51 CST
- Agent/operator: Codex
- Baseline run: `20260830-142821-m2d-threshold-failure-diagnostics`, Candidate C
- Data: unchanged M2b native pilot cache and train-only normalization hashes

## Problem and evidence

- Candidate C is the strongest diagnostic baseline but still has Se/+P/FPR `66.996% / 40.774% / 0.4745%` at probability threshold 0.999.
- Candidates B/C feed raw signed-int8 scalar values directly to the FP32 classifier. Their valid operating point is pinned at the maximum threshold, indicating severe logit/probability saturation.
- Candidate A, which zeros scalar features, does not exhibit the same threshold saturation but has very poor separation.

## Optimization

- Method: after all LSB-domain augmentations, dequantize waveform and four feature tensors by the explicit divisor 128 before FP32 forward. Add the divisor to the candidate config and exported config; do not change cached int8 bytes or the external input contract.
- Keep Candidate C architecture, data, seed 17, weighted CE, optimizer, augmentation, epoch/patience and threshold gates unchanged.
- Why: this is the smallest reversible change that directly addresses saturation while preserving the frozen INT8 deployment interface.
- Alternatives deferred: changing class weight, focal loss, hard-negative mining, more patients, larger network or threshold grid.

## Frozen acceptance criteria

- Unit tests prove int8 `[-128,127]` maps to FP32 `[-1,127/128]` after augmentation and formal configs remain immutable.
- One-epoch smoke is finite and hash-complete; formal seed-17 run is validation-only and never opens internal-test.
- Formal eligibility remains at least one threshold with VEB `+P>=95%` and `FPR<=0.25%`; maximize Se by the existing rule.
- Compare against M2d Candidate C using raw TP/FN/FP/TN and Se/+P/FPR. No threshold fallback or gate change.
- If no eligible threshold exists, reject and use the saved threshold diagnostics to choose exactly one next optimization.
- This pilot run cannot close full M2; full-cohort three-seed evidence remains mandatory.

## Results

- TDD passed signed-int8 mapping `[-128,127] -> [-1,127/128]` after LSB-domain augmentation.
- One-epoch smoke completed; its selected non-gating diagnostic threshold moved from the saturated 0.999 region to 0.255.
- Formal validation-only run trained 30 epochs (best epoch 22) and was rejected. Internal-test was not loaded.
- Best-F1 diagnostic point at threshold 0.501: `TP/FN/FP/TN=422/993/1272/288902`, Se `29.823%`, +P `24.911%`, FPR `0.4384%`.
- Under the frozen FPR gate, threshold 0.552 gave `268/1147/721/289453`, Se `18.940%`, +P `27.098%`, FPR `0.2485%`.
- Relative to M2d C, threshold saturation was removed, but discrimination worsened: best-F1 Se `66.996% -> 29.823%`, +P `40.774% -> 24.911%`. No point reached +P 95%.
- Twelve smoke/formal artifact hashes were independently checked with zero mismatch; rejected model SHA `b000a40f...18c8e`.
- Evidence: `docs/reports/20260830-144058-m2e-fp32-input-dequantization/`.

## Decision

- Decision: `回到训练`
- Reason: dequantization correctly repaired calibration but did not meet any model gate. The next isolated variable is positive-class loss weight under the large train/validation prevalence shift.
