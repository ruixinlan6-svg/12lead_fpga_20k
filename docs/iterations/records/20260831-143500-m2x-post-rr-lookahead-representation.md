# Optimization Run: `20260831-143500-m2x-post-rr-lookahead-representation`

> 中央审查补充（2026-08-31）：本轮仅接受为探索性结果。原缓存给首末搏合成 RR，且未先建立一搏延迟 v2 契约；所列指标不得作为部署一致基线。该缺陷由 `20260831-180114-m2ab-lookahead-contract-boundary-repair` 修复后重测。

## Identity

- Run ID: `20260831-143500-m2x-post-rr-lookahead-representation`
- Stage: `M2 feature & representation ablation`
- Status: `completed`
- Started/finished: 2026-08-31 14:35 CST / 2026-08-31 15:05 CST
- Agent/operator: Antigravity
- Baseline: M2u cap-2000 standard convolution five-bin model (FPR-gated Se 94.629%, +P 65.896%, best-F1 Se 88.481%, +P 76.435%)
- Candidates: 1-beat lookahead (post-RR ratio and compensatory-pause coupling ratio), five-bin temporal pooling, cap 2000, seed 17, validation-only threshold search

## Problem and evidence

- M2u achieved high sensitivity (Se 94.629% at FPR <= 0.25%), but precision (+P) remained stalled at 65.9% (best F1 point 76.4%).
- Analysis from M2p and M2w shows that single-beat morphology alone cannot unambiguously separate true VEBs from aberrantly conducted supraventricular beats (S) or wide-QRS sinus variants (N).
- In cardiac electrophysiology, ventricular ectopic beats (VEB/PVC) possess a full compensatory pause ($RR_{\text{pre}} + RR_{\text{post}} \approx 2 \times RR_{\text{sinus}}$ with $RR_{\text{post}} > 1.15 \times RR_{\text{sinus}}$), whereas premature atrial contractions (PAC/S) exhibit an incomplete compensatory pause, and non-premature wide beats exhibit $RR_{\text{pre}} \approx 1.0, RR_{\text{post}} \approx 1.0$.
- With user explicit authorization under `/goal`, introducing a 1-beat decision latency allows extracting $RR_{\text{post}}$ and $RR_{\text{comp}}$ without violating causal streaming in hardware.

## Optimization

- Extend scalar auxiliary features from 4 to 6:
  1. `pre_rr_over_recent_8_rr_median` = $(R_i - R_{i-1}) / \text{median}(RR_{\text{recent8}})$
  2. `post_rr_over_recent_8_rr_median` = $(R_{i+1} - R_i) / \text{median}(RR_{\text{recent8}})$
  3. `compensatory_pause_ratio` = $((R_i - R_{i-1}) + (R_{i+1} - R_i)) / (2.0 \times \text{median}(RR_{\text{recent8}}))$
  4. `qrs_width_ms`
  5. `peak_over_recent_8_peak_median`
  6. `main_lead_sqi`
- Update `prepare_icentia_native_cache.py` to extract all 6 features from the local 256-patient source tree and normalize with train-only median and IQR.
- Build run-scoped cache: `runs/20260831-143500-m2x-post-rr-lookahead-representation/native_cache`.
- Model architecture: `TinyECGCNN_NV` with `temporal_pool_bins=5` and `num_features=6`.
- Static envelope: 1,678 parameters ($\le 2,048$) and 91,052 MACs/beat ($\le 100,000$).
- Train on GPU with AdamW, lr=1e-3, cap=2000, weighted CE (class weight 2.5), 50 epochs, early stopping patience 8.
- Validation-only threshold search [0.001, 0.999]. Internal test remains unopened.

## Frozen acceptance criteria

- TDD confirms 6-feature extraction, normalization, positive train IQRs, model backward-compatibility, parameter count = 1,678, MACs = 91,052.
- Scale-256 cache builds with 912 records, 0 patient overlap, valid train/validation/internal_test splits.
- Validation eligibility gate: `VEB +P >= 95.0%` and `VEB FPR <= 0.25%`, selecting threshold with maximum Se among eligible thresholds.
- If seed 17 passes, proceed to seeds 29 and 43 before one-time internal-test evaluation.
- If seed 17 fails, record full diagnostics and determine the next step under `/goal`.

## Execution

- Entry commands:
  1. Local unit tests: 184/184 PASS
  2. Sync code to remote server
  3. Build 6-feature cache on remote GPU server: completed 912 records, train 145,172, val 291,589, test 288,363 samples.
  4. Train Candidate on remote GPU server (seed 17, validation-only)
  5. Error taxonomy audit on validation set
- GPU: remote GPU server (RTX 5060 Ti, CUDA:0)

## Results

| Metric | Baseline (M2u Cap2000) | This run (M2x Lookahead-6) | Delta | Comparable? |
|---|---:|---:|---:|---|
| Parameters | 1,674 | 1,678 | +4 | yes |
| MACs / beat | 91,048 | 91,052 | +4 | yes |
| Best Val VEB F1 | 0.819 (th=0.841) | 0.797 (th=0.706) | -0.022 | yes |
| Best-F1 Se / +P / FPR | 88.481 / 76.435 / 0.133% | 84.452 / 75.490 / 0.134% | -4.029 / -0.945 pp | yes |
| Max Se under FPR <= 0.25% | 94.629% (+P 65.896%, FPR 0.239%) | 91.378% (+P 64.232%, FPR 0.248%) | -3.251 pp | yes |
| Max +P scanned | 76.435% | 83.644% (th=0.987, Se=28.55%) | +7.209 pp | yes |
| Eligible thresholds (+P>=95%, FPR<=0.25%) | 0 | 0 | 0 | yes |

- Diagnostic findings:
  - The 6 features show sharp physiological separation: True VEB median $pre\_rr = -45.0, post\_rr = +61.0, comp = +24.0, width = +64.0$ vs Normal $pre\_rr = +5.0, post\_rr = -5.0, comp = +3.0, width = -13.0$.
  - Training stopped early at epoch 13 (best epoch 5 with val F1 0.7466). The high learning rate (lr=1e-3) combined with heavy class weighting (`veb_class_weight=2.5`) caused loss oscillations after epoch 5.
  - Maximum precision reachable across the threshold scan increased from 76.4% in M2u to 83.6% in M2x.
  - Tuning the learning rate (3e-4 / 5e-4) and reducing positive class weighting pressure (veb_class_weight 1.0 vs 1.5) is indicated to prevent optimization oscillation and boost precision toward >= 95%.

- Evidence: `docs/reports/20260831-143500-m2x-post-rr-lookahead-representation/seed17/`
- Unverified items: seeds 29/43, internal test, external databases, quantization, RTL and hardware.

## Decision

- Decision: `回到训练`
- Reject seed 17 checkpoint for freezing. The 6-feature lookahead cache is verified and retained.
- Next step: Run M2y multi-GPU learning rate and class weight ablation on the verified 6-feature cache to stabilize training and target +P >= 95%.
