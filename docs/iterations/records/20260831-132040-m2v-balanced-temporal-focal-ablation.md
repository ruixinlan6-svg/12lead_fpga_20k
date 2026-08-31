# Optimization Run: `20260831-132040-m2v-balanced-temporal-focal-ablation`

## Identity

- Run ID: `20260831-132040-m2v-balanced-temporal-focal-ablation`
- Stage: `M2 combined measured-factor ablation`
- Status: `completed`
- Started/finished: 2026-08-31 13:20 CST / 2026-08-31 13:28 CST
- Agent/operator: Codex
- Baseline: rejected but diagnostically strongest M2u cap-2000 five-bin model
- Candidates: negative focal gamma `1/2/4`, seed 17

## Problem and evidence

- Five-bin temporal pooling plus cap 2000 improved FPR-gated Se to `94.629%`, but +P remained `65.896%` and no threshold met 95%.
- M2r showed the negative-focal family can reduce false positives and improve diagnostic precision, while M2u supplies a substantially stronger sensitivity baseline.
- Testing their interaction is now a combination of two independently measured factors, not an ungrounded multi-factor search.

## Optimization

- Retain M2u cap 2000, five temporal bins, exact cache, augmentation, optimizer, learning rate, seed and threshold gates.
- Change only weighted CE to asymmetric negative-focal gamma 1, 2 or 4; positive-example weighted-CE term and VEB weight 2.5 stay unchanged.
- Run all three candidates concurrently, validation-only. Internal test remains unopened.
- Alternatives rejected: more cap values, new architecture, validation mining or gate relaxation.

## Frozen acceptance criteria

- Config audit proves candidates differ only in identity/description and gamma; caps are 2000 and bins are five.
- All candidates remain 1,674 parameters / 91,048 MACs and use seed 17.
- Eligibility remains `VEB +P >= 95%` and `VEB FPR <= 0.25%`, selecting maximum Se.
- Every run writes a complete rejected/accepted artifact set and SHA-256 manifest; internal-test isolation is explicit.
- Zero passing candidates means reject this combination family and stop gamma tuning. Any passing candidate proceeds to separately recorded seeds 17/29/43 before internal test.

## Results

- Config-focused and complete EC57 suites passed (`181/181`); `git diff --check` returned no errors.
- Config SHA-256 values for gamma 1/2/4: `e3f298e9a4a6be0d3b8fb2a9772485d3eab6b1dd5b8dcc5200759e4d48def811`, `5d254cde503ee34d66cf5b57c0a979a5905af82355393d36ce925036f9799347`, `819dd3db852cf46708a30864fbe6d7c4258d533b2f39744fae4f2c7908ffa289`.
- All three seed-17 validation-only jobs were rejected with no +P-eligible threshold:

| gamma | best epoch / epochs | best-F1 TP/FN/FP | Se | +P | FPR | FPR-gated TP/FN/FP | Se | +P | FPR |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 10 / 18 | 1212/203/416 | 85.654% | 74.447% | 0.14336% | 1298/117/714 | 91.731% | 64.513% | 0.24606% |
| 2 | 5 / 13 | 1175/240/473 | 83.039% | 71.299% | 0.16301% | 1255/160/709 | 88.693% | 63.900% | 0.24434% |
| 4 | 3 / 11 | 1104/311/703 | 78.021% | 61.096% | 0.24227% | 1107/308/720 | 78.233% | 60.591% | 0.24813% |

- Every focal candidate is inferior to the weighted-CE M2u cap-2000 baseline (`FPR-gated Se 94.629%`, best-F1 +P `76.435%`).
- Evidence: `docs/reports/20260831-132040-m2v-balanced-temporal-focal-ablation/{g1_seed17,g2_seed17,g4_seed17}/`; all `18/18` manifest-listed artifacts verified.
- Unverified by design: seeds 29/43, internal test, external databases, quantization, RTL and hardware.

## Decision

- Decision: `回到训练`
- Reject all checkpoints and stop asymmetric focal tuning. Restore weighted CE and retain cap 2000 plus five-bin pooling.
- Next gate: a separately recorded shape-capacity intervention that preserves the existing waveform/feature contract and hardware envelope.
