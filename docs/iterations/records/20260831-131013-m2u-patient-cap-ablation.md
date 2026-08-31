# Optimization Run: `20260831-131013-m2u-patient-cap-ablation`

## Identity

- Run ID: `20260831-131013-m2u-patient-cap-ablation`
- Stage: `M2 patient-balanced training ablation`
- Status: `completed`
- Started/finished: 2026-08-31 13:10 CST / 2026-08-31 13:19 CST
- Agent/operator: Codex
- Baseline: rejected M2s five-bin representation plus accepted M2t train-only sampling audit
- Candidates: five-bin model, seed 17, per-patient epoch caps `500/1000/2000`

## Problem and evidence

- M2t measured selected p99/median patient counts `3790/421 = 9.002`, Gini `0.4068`; the current 10,000 cap affects zero patients.
- M2p measured validation false positives concentrated in a few patients. The inactive cap permits large train patients to dominate gradient updates and is therefore a measured generalization risk.

## Optimization

- Use the M2s five-bin temporal model and restore unchanged weighted CE.
- Change only `data.max_beats_per_patient_epoch` to 500, 1000 or 2000; retain the exact cache, 1:4 global negative ratio, augmentation, optimizer, learning rate, seed, epoch/patience and gates.
- Run the three validation-only candidates concurrently on independently idle GPUs. Internal test remains unopened.
- Why these values: 500 is near the measured median 421, 1000 is above p90 825, and 2000 is above p95 1656.5 while still suppressing the p99/max tail.
- Alternatives rejected for this round: focal loss combination, class-conditional patient caps, validation hard-negative mining or further architecture changes.

## Frozen acceptance criteria

- Config audit proves the three candidates differ only in identity/description and patient cap; caps are exactly 500/1000/2000.
- Each candidate remains 1,674 parameters / 91,048 MACs and uses seed 17, weighted CE and validation-only evaluation.
- Eligibility remains `VEB +P >= 95%` and `VEB FPR <= 0.25%`, then maximum Se.
- Every accepted or rejected candidate writes a complete SHA-256 manifest and full threshold diagnostics.
- If no candidate passes, retain the best measured diagnostic only as the next baseline; do not run more cap values or internal test.
- If at least one passes, use the frozen priority and proceed to separately recorded seeds 17/29/43 before internal test.

## Results

- Config-focused test and complete EC57 suite passed (`180/180`); `git diff --check` returned no errors.
- Config SHA-256 values for caps 500/1000/2000 were respectively `fb88ac0bdf8660beb84d252caa9fe7dbf398c816a34a25104ce6b65f0974261e`, `3560fb49ea3ce9d39e2c8be9f58664ef5e83ec4ed3034110e97f1ad8b0aa5c74`, and `92c16d96a78595d3017a78fd5e12cf28ce220bfd8de79f7901894db9e6b2e83c`.
- Three seed-17 validation-only jobs ran concurrently. All retained `1,674` parameters / `91,048` MACs, weighted CE and internal-test isolation.
- No candidate had an eligible threshold. Diagnostics:

| cap | best epoch / epochs | best-F1 threshold | TP/FN/FP | Se | +P | FPR | max-Se threshold under FPR gate | Se | +P | FPR |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 500 | 15 / 23 | 0.829 | 1192/223/434 | 84.240% | 73.309% | 0.14957% | 0.718 | 90.177% | 63.864% | 0.24882% |
| 1000 | 9 / 17 | 0.749 | 1230/185/467 | 86.926% | 72.481% | 0.16094% | 0.609 | 92.226% | 64.349% | 0.24916% |
| 2000 | 12 / 20 | 0.841 | 1252/163/386 | 88.481% | 76.435% | 0.13302% | 0.655 | 94.629% | 65.896% | 0.23882% |

- Cap 2000 is the strongest measured diagnostic: versus uncapped M2s it raises FPR-gated Se from `87.703%` to `94.629%` and best-F1 Se/+P from `78.799/75.954%` to `88.481/76.435%`.
- Evidence: `docs/reports/20260831-131013-m2u-patient-cap-ablation/{cap500_seed17,cap1000_seed17,cap2000_seed17}/`; all `18/18` manifest-listed artifacts verified after download.
- Unverified by design: seeds 29/43, internal test, external databases, quantization, RTL and hardware.

## Decision

- Decision: `回到训练`
- Reject all checkpoints for freezing. Retain cap 2000 with five-bin pooling as the next diagnostic baseline because it maximizes Se at both reported operating points without violating the FPR gate.
- Next gate: separately recorded negative-focal loss ablation on this retained representation/sampler; no further cap tuning.
