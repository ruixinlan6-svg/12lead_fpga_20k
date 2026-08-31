# Optimization Run: `20260830-141150-m2c-pilot-candidate-ablation`

## Identity

- Run ID: `20260830-141150-m2c-pilot-candidate-ablation`
- Stage: `M2 FP32 pilot candidate selection`
- Status: `completed`
- Started/finished: 2026-08-30 14:12 CST / 2026-08-30 14:28 CST
- Agent/operator: Codex
- Baseline run: `20260830-101200-m2b-continuous-sqi-repair`
- Git commit: `9ebc08357c427be37e029a4568498f01a64bb7a7`
- Data: accepted M2b native Icentia11k 1.0 pilot cache; train/validation/internal-test patients `24/24/24`, patient overlap zero

## Problem and evidence

- The only previous VEB checkpoints were trained from invalid heuristic pseudo-labels and remain revoked.
- The native-label cache now passes provenance and normalization gates, but no model has yet demonstrated a valid validation threshold.
- The internal-test split must remain inaccessible while selecting A/B/C.

## Optimization

- Method: run the three predeclared candidates independently on free GPUs, first for one smoke epoch and then with seed 17 for at most 50 epochs:
  - A: waveform, no scalar features, gain augmentation;
  - B: waveform plus four frozen scalar features, gain augmentation;
  - C: B plus frozen baseline-wander and 12–30 dB Gaussian-noise augmentation.
- Common settings: AdamW, lr `1e-3`, weight decay `1e-4`, batch `1024`, patience `8`, weighted cross-entropy, per-patient cap 10,000 beats/epoch, negative:positive at most 4:1.
- Threshold selection uses validation only, grid `0.001..0.999` step `0.001`; no fallback threshold is permitted.
- Why: this isolates morphology, RR/SQI features and augmentation without expanding the frozen search space after observing outcomes.
- Alternatives rejected before execution: larger network, focal loss, extra datasets, internal-test tuning, old checkpoints or a best-F1 fallback.

## Frozen acceptance criteria

- Before launch: verify SSH identity, GPU memory/utilization and active compute processes; do not interrupt other users.
- Three one-epoch smoke runs have finite loss, `[batch,2]` output and complete tracked artifacts.
- A candidate is eligible only if validation has at least one threshold with VEB `+P>=95%` and `FPR<=0.25%`; among eligible thresholds maximize Se, then +P, then proximity to 0.5.
- Candidate ranking: eligible candidates first, then validation VEB Se, then smaller hardware cost. Internal-test is not evaluated in this run.
- Model stays within 2,048 parameters and 100,000 MAC/beat; cache provenance and normalization hashes remain unchanged.
- If no candidate has an eligible threshold, decision is `回到训练`; do not inspect internal-test and do not call M2 complete.
- Even if a pilot candidate passes, this run only selects the architecture; full-cohort three-seed evidence is still required for M2 closure.

## Results

- GPU preflight: cards 0/1/2 were idle; no foreign compute process was stopped.
- Three one-epoch smoke runs completed on separate GPUs. All losses were finite and all models stayed at 1,546 parameters / 90,920 MAC:
  - A train/validation loss `0.680487 / 0.449005`, model SHA `d574815e...29aad`;
  - B `18.858697 / 7.362566`, SHA `adbc9a8d...ce257`;
  - C `18.873911 / 7.335343`, SHA `a4e4d8f...5c366`.
- Smoke artifact manifests verified 18/18 files with zero hash mismatch.
- Formal seed-17 validation-only runs: A, B and C were each rejected because no scanned threshold met VEB `+P>=95%` and `FPR<=0.25%` simultaneously.
- Internal-test NPZ was not loaded and no internal-test metric was computed.
- Formal failure happened before the legacy writer saved checkpoint/history/threshold diagnostics; this evidence-gap is the only purpose of the next run and does not change the model decision.
- Evidence: `docs/reports/20260830-141150-m2c-pilot-candidate-ablation/smoke/` and `formal_gate_failures.json`.

## Decision

- Decision: `回到训练`
- Reason: no eligible validation threshold exists for any frozen A/B/C candidate; no winner can be frozen and M2 remains open.
- Next gate: reproduce the three failures with fail-safe diagnostic artifact export, still without internal-test access.
