# Optimization Run: `20260830-145046-m2f-class-prior-loss-ablation`

## Identity

- Run ID: `20260830-145046-m2f-class-prior-loss-ablation`
- Stage: `M2 FP32 loss ablation`
- Status: `completed`
- Started/finished: 2026-08-30 14:51 CST / 2026-08-30 14:56 CST
- Agent/operator: Codex
- Baseline run: `20260830-144058-m2e-fp32-input-dequantization`
- Data/model: unchanged native M2b pilot cache, dequantized Candidate C, seed 17

## Problem and evidence

- Train cache has 2,632 VEB among 13,157 beats (`20.005%`), while validation has 1,415 VEB among 291,589 (`0.485%`).
- Baseline positive class weight 2.5 increases the effective positive pressure despite a roughly 41-fold prevalence shift, consistent with persistent false positives.
- Dequantization removed saturation but under the FPR gate still produced only +P `27.098%` and Se `18.940%`.

## Optimization

- Method: compare dequantized Candidate C with positive class weights `1.0`, `0.1`, and `0.02` on GPUs 0/1/2. The last value approximates validation/train positive-odds correction; the middle value tests a less aggressive correction.
- Keep cache, architecture, augmentation, optimizer, batch, epochs, patience, seed and threshold gates identical.
- Why: isolate whether the false-positive burden is driven by the training-loss prior before acquiring substantially more patients or changing the network.
- Alternatives deferred: focal loss, hard-negative mining, larger training cohort, larger network, threshold-grid changes.

## Frozen acceptance criteria

- Config tests prove the three files differ only in `veb_class_weight` and candidate name/description.
- Each run is validation-only and never opens internal-test; rejected runs retain complete diagnostics and hashes.
- Eligibility remains `+P>=95%` and `FPR<=0.25%`; eligible candidates rank by Se, then +P.
- Report TP/FN/FP/TN and deltas from M2e. No threshold fallback or test-set access.
- If none is eligible, reject this loss route and scale native training patients before further model tuning.
- This run cannot close M2; full-cohort three-seed evidence remains mandatory.

## Results

- All three variants stopped after 9 epochs with best epoch 1 and were rejected; internal-test was not loaded.
- At the frozen FPR gate:
  - weight 1.0: `TP/FN/FP/TN=1/1414/311/289863`, Se `0.071%`, +P `0.321%`, FPR `0.1072%`;
  - weight 0.1: `1/1414/331/289843`, Se `0.071%`, +P `0.301%`, FPR `0.1141%`;
  - weight 0.02: `1/1414/341/289833`, Se `0.071%`, +P `0.292%`, FPR `0.1175%`.
- No variant had any threshold with +P 95%; reducing positive weight caused near-total sensitivity collapse rather than a useful specificity tradeoff.
- Eighteen artifact hashes were independently checked with zero mismatch.
- Evidence: `docs/reports/20260830-145046-m2f-class-prior-loss-ablation/validation/`.

## Decision

- Decision: `回到训练`
- Reason: class-prior loss weights are rejected. Per the frozen fallback, scale native training patients before further model/loss tuning.
