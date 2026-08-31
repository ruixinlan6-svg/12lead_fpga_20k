# Optimization Run: `20260831-124340-m2s-five-bin-temporal-pooling`

## Identity

- Run ID: `20260831-124340-m2s-five-bin-temporal-pooling`
- Stage: `M2 representation ablation`
- Status: `completed`
- Started/finished: 2026-08-31 12:43 CST / 2026-08-31 13:06 CST
- Agent/operator: Codex
- Baseline: rejected M2l Candidate C seed 17 and rejected M2r focal-loss family
- Candidate: Candidate C data, augmentation and weighted CE restored; replace final global average pooling with five non-overlapping temporal means over the `16 x 40` activation map

## Problem and evidence

- M2r changed the loss emphasis substantially but all gamma candidates still had zero eligible thresholds, so additional gamma tuning is not justified.
- The current three-convolution encoder ends with global average pooling across all 40 time positions. That makes pre-R, R-centered and post-R activations position-invariant even though the beat is aligned at a fixed R index.
- M2p showed patient-concentrated, high-confidence validation false positives; preserving coarse temporal morphology is a direct representation intervention rather than validation mining.

## Optimization

- Partition the final length-40 activation into five contiguous bins of eight samples and average each bin independently, yielding 80 waveform features instead of 16.
- Concatenate the unchanged four causal scalar features and train the same two-logit head.
- Use exact bin size eight so the later integer implementation can use an arithmetic right shift by three; do not introduce attention, recurrence or a non-power-of-two divisor.
- Keep the cache, normalization, sampler, augmentation, optimizer, learning rate, weighted CE, VEB class weight, epoch/patience, seed and threshold scan unchanged.
- First run seed 17 validation-only on one idle GPU. Internal test must remain unopened.
- Alternatives rejected for this iteration: more focal gamma values, validation hard-negative mining, larger convolution widths, bidirectional/post-R RR features, or simultaneous data and model changes.

## Frozen acceptance criteria

- TDD proves default one-bin behavior remains shape/API compatible and five-bin pooling preserves temporal-bin separation.
- Candidate config differs from the M2l Candidate C only in identity/description and declared `temporal_pool_bins=5`; weighted CE is restored.
- Static envelope before training: no more than 2,048 parameters and 100,000 MACs per beat. Exact counts and source/config SHA-256 are recorded.
- Validation eligibility remains `VEB +P >= 95%` and `VEB FPR <= 0.25%`, selecting maximum Se only among eligible thresholds.
- Rejected runs still write config, normalization, model, metrics, full threshold failure and a complete SHA-256 manifest.
- If seed 17 has no eligible threshold, reject this representation and do not inspect internal test or run seeds 29/43.
- If seed 17 passes, run separately recorded seeds 17/29/43 before one-time internal-test evaluation.

## Results

- TDD red condition was observed (`TinyECGCNN_NV.__init__()` rejected `temporal_pool_bins`), then the implementation passed the two focused tests and the complete EC57 suite `179/179`; `git diff --check` returned no errors.
- Static envelope: `1,674` parameters and `91,048` MACs/beat. Default one-bin construction remains covered at the original `1,546` parameters and `90,920` MACs.
- Local/remote inputs matched before execution:
  - `model_nv.py`: `d51e6755cde7e0fa1e7b7db20b6f1cacc04f6eef6846a70dfc81648be0f83e9a`
  - `train_nv.py`: `92e033a2bcc3ec76608e4e07737a975a414fb2a009fe36c38dfa89c27c809c59`
  - config: `9889a60c318b2b08a62d718405693ff779685a6fbdac01aee745a63a8dad8906`
- Seed 17 ran for 43 epochs (best epoch 35), validation-only; console evidence states `Internal test: not loaded (validation-only isolation)`.
- No threshold met both frozen gates. Diagnostics:
  - best F1 `0.745015` at threshold `0.743`: TP/FN/FP/TN `1115/300/353/289821`, Se `78.799%`, +P `75.954%`, FPR `0.12165%`;
  - maximum Se under the FPR gate at threshold `0.480`: `1241/174/699/289475`, Se `87.703%`, +P `63.969%`, FPR `0.24089%`;
  - no scanned threshold reached `+P >= 95%`.
- Relative to M2l, the representation is materially better diagnostically: FPR-gated Se increased from `66.926%` to `87.703%`; nevertheless it remains `31.031` percentage points below the +P gate at that operating point and is not checkpoint-freezable.
- Evidence: `docs/reports/20260831-124340-m2s-five-bin-temporal-pooling/seed17/`. All `6/6` manifest-listed artifacts matched after download; `console.log` SHA-256 is `f7561850108680ec180d52d6a661e72d1fae21644c070392aa405ce6f5d4f447`.
- Runtime: approximately 20 minutes, with low GPU utilization caused by per-sample Python/NumPy augmentation. This did not stall or invalidate the run, but requires a separately verified tooling optimization before a broad sweep.
- Unverified by design: seeds 29/43, internal test, external databases, quantization, RTL and QN88 hardware.

## Decision

- Decision: `回到训练`
- Reject seed 17 for freezing and do not run seeds 29/43 or internal test. Retain five-bin pooling as the strongest measured representation baseline for the next independently recorded training intervention.
- Next gate: audit train-patient sampling concentration, then choose a patient-generalizing sampler or a measured combination with the prior precision-focused loss.
