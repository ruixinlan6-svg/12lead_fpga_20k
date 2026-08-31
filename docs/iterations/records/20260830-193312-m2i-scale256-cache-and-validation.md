# Optimization Run: `20260830-193312-m2i-scale256-cache-and-validation`

## Identity

- Run ID: `20260830-193312-m2i-scale256-cache-and-validation`
- Stage: `M2 native cache scale and FP32 validation`
- Status: `completed`
- Started/finished: 2026-08-30 19:33 CST / 2026-08-30 21:20 CST
- Agent/operator: Codex
- Baseline: M2e dequantized Candidate C; M2h accepted annotation audit
- Data: Icentia11k 1.0, train/validation/internal-test patients `256/24/24`, three audited records per patient
- Model config: `train/ec57/configs/candidate_c_dequantized.json`, SHA-256 `ec33db895e8dc9a59cc3c5578bd4e7d8ceec93d534859eea3134e020ed140356`

## Problem and evidence

- The 24-patient M2e pilot had no threshold satisfying VEB `+P >=95%` and `FPR <=0.25%`; loss-weight sweeps in M2f worsened sensitivity.
- M2h repaired the only annotation-availability defect without changing validation/internal-test identities. The clean annotation audit SHA-256 is `b12a91abe18e7247d6afe7973c4f1df2e4539f35172a241f0fb9c63f7fc52e7c`.
- The next unresolved hypothesis is insufficient train-patient morphology coverage, not loss weight or threshold search.

## Optimization

- Reuse the existing remote Icentia source cache only as a content-addressed download cache, download every missing `.atr/.dat/.hea` named by the accepted M2h audit, and build a new run-scoped native cache.
- Use exactly the audited `912` records. Preserve native `V -> VEB`, `N/S -> non_VEB`, count and exclude `Q`; compute waveform and four-feature normalization from train only.
- Train only Candidate C dequantized with original VEB class weight `2.5`, seed `17`, at most `50` epochs and frozen augmentation/optimizer/early stopping. Search thresholds on validation only.
- Why: increase independent train morphology from 24 to 256 patients while keeping the comparison benchmark and all other variables fixed.
- Alternatives deferred: full 8,800-patient train cohort, hard-negative mining, focal loss, architecture expansion and any internal-test-guided tuning.

## Frozen acceptance criteria

- Before download/training, remote identity, GPU/process occupancy and target-volume free space are recorded; free space must be at least `10 GiB`. No other process is stopped.
- Cache consumes annotation audit SHA-256 `b12a91abe18e7247d6afe7973c4f1df2e4539f35172a241f0fb9c63f7fc52e7c`, contains exactly `912` source records and `2,736` individually SHA-256-hashed source files, and declares no locked source.
- Patient counts are exactly train/validation/internal-test `256/24/24`, with zero overlap. Validation/internal-test patient and record identities remain exactly equal to M2b/M2h.
- Train contains nonzero `N/S/V`; `Q` is counted then excluded from loss cache. All four train-only feature IQR values are strictly positive. Every saved split passes the provenance contract and the cache hash manifest verifies.
- Formal model training loads only train and validation. Candidate config and seed are exactly those above; rejected runs still save config, history, threshold scan, checkpoint/model hash, normalization, metrics and failure samples.
- Validation eligibility is unchanged: choose only a threshold with VEB `+P >=95%` and VEB `FPR <=0.25%`, then maximize VEB Se. If none exists, reject this run and retain diagnostics; do not open internal test.
- Passing this 256-patient validation gate does not complete M2. It only authorizes a separately recorded full-train-cohort freeze and the required seeds `17/29/43` before a one-time internal-test evaluation.

## Results

- Remote preflight passed: identity matched the configured host; no Python training process was running; GPUs 0/1/2 were idle; C: had approximately `104.7 GiB` free, above the frozen `10 GiB` floor.
- All `2,736` audited `.atr/.dat/.hea` files were downloaded (`1,950,602,060` bytes). No missing source remained and no GPU training started.
- Cache construction failed at record position `182/912`, train record `p01538_s46`, because the native annotation contains two `Q` symbols at the same sample `1009032`. The builder raised `ValueError: non-increasing native beat annotation` before writing any cache.
- A direct read of the source annotation confirmed the exact local sequence `[(4030, 1009032, 'Q'), (4031, 1009032, 'Q')]`; this is an exact duplicate unknown-beat marker, not an N/S/V label conflict.
- Failure evidence: `docs/reports/20260830-193312-m2i-scale256-cache-and-validation/cache_build_failure.json`, SHA-256 `1a2d8677c2570cc940427eae9d9c001d17ad2c94bbadfbf94e8404ceadc13dc6`.
- Cache manifest/splits were not written, model training did not start, and internal-test model evaluation did not occur.

## Decision

- Decision: `回到训练`（数据构建）
- Reason: the frozen complete-cache gate failed. Duplicate-timestamp policy must be explicitly audited and implemented in a new run rather than silently deduplicated.
