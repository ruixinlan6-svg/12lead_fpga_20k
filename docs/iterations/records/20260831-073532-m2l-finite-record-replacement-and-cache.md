# Optimization Run: `20260831-073532-m2l-finite-record-replacement-and-cache`

## Identity

- Run ID: `20260831-073532-m2l-finite-record-replacement-and-cache`
- Stage: `M2 deterministic train-record replacement, cache and validation`
- Status: `completed`
- Started/finished: 2026-08-31 07:35 CST / 2026-08-31 12:02 CST
- Agent/operator: Codex
- Baseline: M2j duplicate-Q repair plus accepted M2k full signal-integrity audit
- Model config: unchanged `candidate_c_dequantized`, seed `17`, validation-only threshold selection

## Problem and evidence

- M2k proved that only train record `p05750_s31` is non-finite: two isolated WFDB missing-value samples, affecting Q supports only.
- Imputation would alter source waveforms; dropping the record would violate the three-record-per-patient cohort; retaining it would violate the finite-cache contract.
- The same patient has additional source records that can be selected without changing patient identity or validation/internal-test cohorts.

## Optimization

- Start from the accepted M2h ordered `912`-record audit. For each M2k-affected record, enumerate that patient's source records in the existing SHA-256 digest order, excluding records already selected.
- Evaluate candidates in order and accept the first whose `.atr/.dat/.hea` are available and hashed, annotation is readable with no non-Q-only duplicate group, signal contract is 250 Hz/one lead, and every physical sample is finite. Log every candidate and rejection reason.
- Replace only `p05750_s31`; preserve patient `p05750`, split `train`, three records for that patient, total `912` records, and byte-identical validation/internal-test patient and record arrays. Do not impute or modify any signal.
- Build a new run-scoped cache from the revised manifest and retain the M2j Q-only duplicate normalization. Then, and only if the cache passes, run unchanged Candidate C validation-only training on an idle GPU.
- Why: deterministic same-patient replacement removes a documented source defect while preserving cohort size and every held-out identity.
- Alternatives rejected: interpolation, zero/nearest fill, affected-window deletion, whole-patient replacement, cohort reduction, or any validation/internal-test change.

## Frozen acceptance criteria

- TDD proves candidate ordering is input-order independent, already-selected records are excluded, the first fully valid candidate is chosen, all failed candidates are logged, and no valid candidate fails closed.
- Revised manifest has exactly `912` records and `304` patients (`256/24/24`), differs from M2h only by one train record for `p05750`, and has byte-identical validation/internal-test lists.
- Every selected record has readable annotation, only Q-only duplicate groups, 250 Hz/one lead, fully finite signal and three verified source-file SHA-256 values. No source waveform is modified.
- Cache meets all unchanged M2i gates: `912` records, `2,736` selected source files, zero patient overlap, native N/S/V nonzero, Q counted/excluded, four positive train IQRs, provenance contract and hash manifest verification.
- Formal seed-17 training loads train+validation only and uses the unchanged config SHA-256 `ec33db895e8dc9a59cc3c5578bd4e7d8ceec93d534859eea3134e020ed140356`. Eligibility remains VEB `+P >=95%`, `FPR <=0.25%`, then maximum Se. Rejection artifacts remain hash-complete.
- Internal-test model evaluation remains prohibited. A passing validation run only authorizes a separately recorded full-train three-seed freeze; it does not complete M2 by itself.

## Results

- Deterministic replacement succeeded: `p05750_s31` was replaced by same-patient `p05750_s48`; the revised audit retained `912` records and source cohort `256/24/24`, with validation/internal identities byte-equal to M2h. Revised audit SHA-256: `cf3687eacabd8ea9cc772019f9666a6fb24d9b8f4bcc384e3579c7e861c9c4a4`.
- Cache completed after the separately recorded M2m/M2n performance repairs. All three NPZ contracts accepted; six artifact hashes independently matched `sha256_manifest.txt`.
- Cache samples/native symbols: train `145,172` (`N=89,386/S=26,753/V=29,033`), validation `291,589` (`N=288,499/S=1,675/V=1,415`), internal-test `288,363` (`N=285,375/S=2,186/V=802`).
- M2o corrected the impossible 256-supervised-patient conjunction: source cohort remains 256 train patients, loss cache contains 251 legally labelled patients, and the five absent patients are proven Q-only. Held-outs remain exact `24/24`.
- Formal Candidate C seed-17 run used validation-only scope; stdout explicitly reported `Internal test: not loaded`.
- Training ran all `50` epochs; best epoch `50`, best validation VEB F1 `0.324807`. Model remains inside hardware envelope: `1,546` parameters and `90,920` MACs/beat.
- Frozen threshold scan tested `999` thresholds and found zero eligible thresholds. At best-F1 threshold `0.899`: VTP/VFN/VFP/VTN=`856/559/435/289739`, Se `60.495%`, +P `66.305%`, FPR `0.14991%`. At best Se under FPR gate threshold `0.841`: `947/468/725/289449`, Se `66.926%`, +P `56.639%`, FPR `0.24985%`. Even threshold `0.999` reached only +P `83.851%` with Se `19.081%` (`270/1145/52/290122`).
- All rejection artifacts are hash-complete; model SHA-256 `1b2d30d21d35f1171480f15939bfdd6851c0aed17d4a6c54056213e61341fb56`. Internal test was not evaluated.
- Evidence: `docs/reports/20260831-073532-m2l-finite-record-replacement-and-cache/`.

## Decision

- Decision: `回到训练`（数据缓存接受；Candidate C seed 17 验证门禁拒绝）
- Next gate: M2p validation-only error taxonomy before changing sampling, loss or architecture.
