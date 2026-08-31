# Optimization Run: `20260830-101200-m2b-continuous-sqi-repair`

## Identity

- Run ID: `20260830-101200-m2b-continuous-sqi-repair`
- Stage: `data feature construction`
- Status: `completed`
- Started/finished: 2026-08-30 10:12 CST / 2026-08-30 14:12 CST
- Agent/operator: Codex
- Baseline run: `20260830-091440-m2a-data-provenance-and-label-repair`
- Git commit: `9ebc08357c427be37e029a4568498f01a64bb7a7`
- Data version: Icentia11k 1.0, same frozen 24/24/24-patient, 3-record-per-patient audit cohort

## Problem and evidence

- M2a processed all 216 records and obtained native labels, but failed before cache output because feature index 3 had train IQR=0.
- The current SQI feature is `1 - differential_noise_fraction - saturation_fraction` for valid signals. Clean Icentia windows usually have both counts equal to zero, so the feature collapses to exactly 1.0.
- GPU training did not start and no internal-test model result was observed.

## Optimization

- Method: audit the existing fixed SQI component distributions on the already downloaded source cohort, then define one bounded continuous SQI using only causal signal-quality statistics already available in `SQIResult`. Preserve native labels, windows, split membership and every other feature unchanged.
- Why: the feature must vary for train-only robust scaling yet remain label-independent and reproducible in an integer/RTL implementation.
- Rejected alternatives: adding epsilon to IQR, silently zeroing the feature, using V/N labels to shape the score, or relaxing the nonzero-IQR gate.

## Frozen acceptance criteria

- Original SQI degeneracy is measured and reported rather than assumed.
- Replacement score is finite, bounded `[0,1]`, causal, label-independent, and derived only from fixed SQI fields.
- Train SQI IQR is strictly greater than zero; all four feature IQR values are strictly greater than zero.
- Rebuilt cache passes exact Icentia11k 1.0 provenance, N/S/V mapping, Q exclusion, patient disjointness, source hashes and locked-database rejection.
- Any zero IQR, non-finite score, source mismatch or patient overlap rejects the run; GPU training remains blocked.

## Results

- SQI audit on all 13,157 selected train beats confirmed the old score was exactly 1.0 for every beat (`IQR=0`, one unique value).
- The causal pure-integer Q15 replacement produced range `0..30635`, median `23997`, IQR `6643`, and 8,602 unique values. The audit file SHA-256 is `8cb7df64f7230b0787e798ab7e19d20ecaa6b12a752cb80318a0f3281e85f5b2`.
- Rebuilt native cache completed all 216 records and 648 source files:
  - train: 13,157 samples, 24 patients, `N=10049`, `S=476`, `V=2632`, Q excluded `92,574`;
  - validation: 291,589 samples, 24 patients, `N=288499`, `S=1675`, `V=1415`, Q excluded `87,807`;
  - internal_test: 288,363 samples, 24 patients, `N=285375`, `S=2186`, `V=802`, Q excluded `90,004`.
- Train-only normalization feature IQR values are `[0.13206625, 16.0, 0.10352010, 0.20273447]`; all are strictly positive.
- Patient overlap is zero; label source is native WFDB `atr` only; locked-database access is false.
- Remote hashes exactly match `sha256_manifest.txt`: train NPZ `635da350...0c2a3`, validation NPZ `676315e4...2f7b`, internal-test NPZ `0fcbd4ad...67307`, dataset manifest `43199a8f...bfbd`, normalization `9285ddc7...318a`.
- Local EC57 regression: 152/152 passed.
- Evidence: `docs/reports/20260830-101200-m2b-continuous-sqi-repair/sqi_audit/` and `native_cache_pilot/` (small manifests only; NPZ remains remote and is not committed).
- Unverified: model training, threshold calibration and internal-test model metrics.

## Decision

- Decision: `接受`（仅限原生数据缓存与连续 SQI 构建）
- Next gate: validation-only A/B/C pilot candidate selection. This 24/24/24-patient cohort is not sufficient by itself to close the full M2 milestone.
