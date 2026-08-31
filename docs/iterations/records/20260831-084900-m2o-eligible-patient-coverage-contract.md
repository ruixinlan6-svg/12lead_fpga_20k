# Optimization Run: `20260831-084900-m2o-eligible-patient-coverage-contract`

## Identity

- Run ID: `20260831-084900-m2o-eligible-patient-coverage-contract`
- Stage: `M2 cache cohort-contract correction`
- Status: `completed`
- Started/finished: 2026-08-31 08:49 CST / 2026-08-31 08:50 CST
- Agent/operator: Codex
- Baseline: completed M2l cache, with 256 audited train-source patients but 251 patients in the supervised train NPZ
- Model config: unchanged `candidate_c_dequantized`, seed `17`, validation-only threshold selection

## Problem and evidence

- The M2l cache passed its per-split native-label/provenance validator and all six generated artifact hashes match `sha256_manifest.txt`.
- Its train NPZ contains 251 patients, not the previously frozen 256. Exact comparison identified five absent source-cohort patients: `p01101`, `p01670`, `p01966`, `p05750`, `p10757`.
- Across all 15 selected records for those patients, the native annotation audit contains only `Q` markers and zero `N/S/V`. Therefore they cannot legally contribute a supervised example under the frozen native mapping.
- Requiring 256 patients in the loss cache conflicts with the stronger frozen rule that `Q` is counted and excluded rather than relabelled.

## Optimization

- Separate `source cohort coverage` from `supervised loss-cache eligibility`.
- Keep the selected source cohort frozen at `256/24/24` patients and `912` records. The train loss cache may contain exactly the source patients with at least one native `N/S/V` example; every absent patient must be proven Q-only from the audited records.
- Add a read-only coverage audit that compares annotation-audit cohorts with NPZ patient IDs, reports expected/actual/missing identities per split, aggregates missing-patient native counts, and fails if any missing patient has an `N/S/V` annotation or if any unexpected patient appears.
- For this frozen cache the expected result is train `256 source / 251 eligible`, with exactly the five named Q-only exclusions; validation/internal-test remain `24/24` with no exclusions.
- Why: preserves native-label semantics and all source provenance while correcting an impossible acceptance conjunction.
- Alternatives rejected: map Q to N/V, inject unlabeled patients, weaken Q exclusion, drop the source patients from the audited cohort, or silently accept 251 without an evidence report.

## Frozen acceptance criteria

- TDD covers Q-only missing patients, missing patients with any N/S/V (reject), unexpected NPZ patients (reject), and exact full coverage.
- Full cache coverage audit accepts only train `256 source / 251 eligible` with missing set exactly `p01101,p01670,p01966,p05750,p10757`, all having N/S/V counts zero and Q count positive.
- Validation and internal-test each remain exact `24/24`, with no missing or unexpected patients.
- Existing NPZ validation remains accepted for all three splits; all six artifact hashes match the cache hash manifest.
- No source, NPZ, label, split, normalization, threshold gate or Candidate C config is modified.
- Only after this audit passes may seed-17 validation-only training begin; internal-test loading/evaluation remains prohibited.

## Results

- RED: the focused test failed because the coverage-audit module did not yet exist.
- GREEN: Q-only train absence is accepted; trainable-label absence, unexpected patients and held-out absence are rejected. Focused data tests passed `32/32`; the combined EC57 suite passed `169/169` before remote execution.
- Full remote report accepted. Source/cache patient counts were train `256/251`, validation `24/24`, internal-test `24/24`, with zero unexpected patients.
- Exact train exclusions and native totals: `p01101 Q=14,436`, `p01670 Q=15,709`, `p01966 Q=17,685`, `p05750 Q=13,983`, `p10757 Q=13,810`; all have `N=S=V=0`.
- Annotation audit SHA-256 remained `cf3687eacabd8ea9cc772019f9666a6fb24d9b8f4bcc384e3579c7e861c9c4a4`.
- NPZ SHA-256 values matched the cache manifest: train `762c61f7520b4d1f5cb9a0e648bee083a74c6bdf8bd2f42468a114ba869c674a`, validation `792149cb7948b0f88235bc619361ce5d05a78edba0a4bf9dc8abe23fcd0f0fc9`, internal-test `c95e3b95d4d2e61cb45e4ed86eb11302e7231bf2d9b1adb0598fb5ac20364c36`.
- Evidence: `docs/reports/20260831-073532-m2l-finite-record-replacement-and-cache/cache_audit/patient_coverage.json`.

## Decision

- Decision: `接受`（纠正后的监督患者覆盖合同）
- Next gate: unchanged Candidate C seed-17 validation-only training; internal test remains prohibited.
