# Optimization Run: `20260831-133023-m2w-depthwise-morphology-capacity`

## Identity

- Run ID: `20260831-133023-m2w-depthwise-morphology-capacity`
- Stage: `M2 morphology architecture`
- Status: `completed`
- Started/finished: 2026-08-31 13:30 CST / 2026-08-31 13:43 CST
- Agent/operator: Codex
- Baseline: M2u cap-2000 five-bin weighted-CE model; M2v focal family rejected
- Candidate: depthwise-separable 8→24→32-channel morphology encoder, five temporal bins, cap 2000, weighted CE, seed 17

## Problem and evidence

- Sampling balance raises FPR-gated Se to `94.629%`, but precision remains far below 95%; focal loss degrades results.
- The original standard-convolution encoder spends `90,880` convolution MACs on only 16 final channels. More morphology channels are needed to separate supraventricular/normal hard negatives from VEB without changing the public four-feature contract.

## Optimization

- Keep the first 1→8 kernel-7 convolution and first max pool.
- Replace the next two standard convolutions by depthwise/pointwise blocks: depthwise kernel 5 plus 8→24 pointwise and pooling, then depthwise kernel 7 plus 24→32 pointwise.
- Retain five fixed eight-sample temporal means, four existing scalar features, cap 2000, weighted CE and all training/gate settings.
- Expected static envelope: 1,650 parameters and 65,288 MACs/beat. Depthwise layers map to independent per-channel FIRs and pointwise 1×1 MACs; no unsupported attention/recurrent operator is introduced.
- Run seed 17 validation-only on one idle GPU. Internal test remains unopened.

## Frozen acceptance criteria

- TDD verifies forward/output shapes, exact 1,650 parameter and 65,288 MAC counts, five-bin ordering, invalid config failure and unchanged legacy-model budget tests.
- Candidate config differs from M2u cap 2000 only in identity/description and architecture declaration.
- Validation eligibility remains `VEB +P >= 95%`, `VEB FPR <= 0.25%`, then maximum Se.
- Rejected output remains hash-complete. No seeds 29/43 or internal-test evaluation unless seed 17 passes.

## Results

- TDD red condition was observed as the new class import failed, then focused tests and the complete EC57 suite passed (`183/183`); `git diff --check` returned no errors.
- Static audit matched the frozen budget: `1,650` parameters and `65,288` MACs/beat. Legacy-model budget tests remained unchanged and passing.
- Local/remote inputs matched before execution: `model_nv.py` `149a0d80028db7c959a8d20b975bfd0231a03ac5a736b59a3d852af16f2137ba`, `train_nv.py` `9be6282fee3173cb69dd97d9ec3c863ef9a9a5d66f251f3ad819863daa50a879`, config `2d5627ecdb7c28bb61dc6984613dc64ef22944a83e969440637693253b4c76f7`.
- Seed 17 ran 31 epochs (best epoch 23), validation-only, with internal test unopened. No threshold reached +P 95%.
- Best-F1 threshold `0.918`: TP/FN/FP/TN `1206/209/413/289761`, Se `85.230%`, +P `74.490%`, FPR `0.14233%`.
- Maximum-Se threshold under the FPR gate `0.770`: `1303/112/725/289449`, Se `92.085%`, +P `64.250%`, FPR `0.24985%`.
- The candidate is inferior to M2u cap-2000 standard convolution at both best-F1 and FPR-gated operating points; reduced MACs do not compensate for the clinical metric regression.
- Evidence: `docs/reports/20260831-133023-m2w-depthwise-morphology-capacity/seed17/`; all `6/6` manifest-listed artifacts verified.
- Unverified by design: seeds 29/43, internal test, external databases, quantization, RTL and hardware.

## Decision

- Decision: `回到训练`
- Reject this checkpoint and retain M2u cap-2000 standard-convolution five-bin model as the strongest diagnostic baseline.
- Current single-beat/four-feature interface is the limiting hypothesis. Any next iteration adding post-RR/compensatory-pause context changes the shared feature and output-latency contract and requires explicit approval before implementation.
