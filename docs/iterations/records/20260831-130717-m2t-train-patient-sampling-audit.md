# Optimization Run: `20260831-130717-m2t-train-patient-sampling-audit`

## Identity

- Run ID: `20260831-130717-m2t-train-patient-sampling-audit`
- Stage: `M2 sampling diagnostic`
- Status: `completed`
- Started/finished: 2026-08-31 13:07 CST / 2026-08-31 13:10 CST
- Agent/operator: Codex
- Baseline: rejected M2s five-bin temporal pooling seed 17

## Problem and evidence

- M2p showed that a small number of validation patients dominate false positives; M2s improved morphology but still produced no +P-eligible threshold.
- The current epoch sampler caps each patient at 10,000 beats and then applies a global 1:4 positive/negative cap. It is not yet measured whether this selected epoch remains dominated by large train patients.
- Changing the sampler without this measurement would be an ungrounded training intervention.

## Optimization

- Read only `train_beats.npz`; do not access validation or internal-test files.
- Reproduce the exact seed-17 epoch-1 indices with the production `build_epoch_sample_indices` function.
- Report raw and selected per-patient counts, positive/negative counts, min/median/p90/p95/p99/max, top-1/top-5/top-10 shares, Gini coefficient and number of patients affected by the 10,000 cap.
- Save JSON plus SHA-256 manifest. Do not train or modify the cache.

## Frozen acceptance criteria

- The audit fails closed unless labels and patient IDs are aligned, all selected indices are valid and deterministic replay is identical.
- Selected total and class counts must exactly match the training loader contract used by M2l/M2s.
- If top-five selected patients contribute at least 25% or selected p99/median is at least 5, prioritize a patient-balancing ablation.
- Otherwise retain the sampler and test one separately recorded combination of five-bin pooling with the strongest precision-focused loss from M2r.
- Internal-test and validation files remain unopened.

## Results

- Two fail-fast tooling defects were corrected before any result was accepted: direct execution initially lacked the project root in `sys.path`, then the production keyword was corrected from `max_negative_to_positive` to `max_negative_per_positive`. Neither failure produced an accepted audit artifact or changed sampling semantics.
- Final audit tool SHA-256: `cc6accb98371b8eb78fff42541ec05f26415fb797448c0fe119fb4b42fc3395c`.
- Scope explicitly records `train_only`; validation and internal-test were not loaded. Deterministic replay was bit-identical and every selected index passed bounds checks.
- Raw train cache: 251 patients, 145,172 beats (`116,139` negative, `29,033` VEB). Selected epoch 0: 145,165 beats (`116,132` negative, `29,033` VEB); the seven-beat difference is the exact global 4:1 negative cap.
- Selected per-patient distribution: min/median/p90/p95/p99/max `78/421/825/1656.5/3790/9013`; p99/median `9.002`; top-1/top-5/top-10 shares `6.209%/17.717%/25.386%`; Gini `0.4068`.
- No patient exceeded the configured 10,000 cap, so the current patient cap is inactive. The frozen p99/median criterion (`>=5`) is met and requires a patient-balancing ablation.
- Evidence: `docs/reports/20260831-130717-m2t-train-patient-sampling-audit/`; manifest verified `1/1`.
- Unverified by design: validation metrics, internal test, model training, quantization, RTL and hardware.

## Decision

- Decision: `接受诊断；回到训练`
- Next gate: validation-only seed-17 ablation of lower patient caps on the retained five-bin representation. Do not combine the focal loss in the same iteration.
