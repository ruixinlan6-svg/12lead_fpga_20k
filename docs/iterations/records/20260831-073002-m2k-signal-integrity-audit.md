# Optimization Run: `20260831-073002-m2k-signal-integrity-audit`

## Identity

- Run ID: `20260831-073002-m2k-signal-integrity-audit`
- Stage: `M2 source signal integrity audit`
- Status: `completed`
- Started/finished: 2026-08-31 07:30 CST / 2026-08-31 07:35 CST
- Agent/operator: Codex
- Baseline: M2j duplicate-Q repair; cache build stopped on non-finite source samples
- Scope: read-only audit of the same M2h `912` Icentia records and `2,736` already-hashed files

## Problem and evidence

- `p05750_s31` contains two physical NaNs whose digital samples are both WFDB missing-value sentinel `-32768`.
- The prevalence, run lengths, split distribution and model-window overlap of missing samples across the full cohort are unknown.
- Choosing interpolation, window exclusion or record replacement from one observed record would be post-hoc and could change validation/internal identities without evidence.

## Optimization

- Read every audited signal in both physical and digital modes without modifying source files. For each record, report signal contract, non-finite count, contiguous missing runs, corresponding digital values, and source `.dat` SHA-256.
- Using native annotation timestamps, report overlap between every missing sample/run and each beat's complete feature support `[R-404, R+96)`; stratify affected beats by N/S/V/Q and split.
- Preserve the exact M2h record list and report all clean and affected records. This run performs measurement only: no imputation, deletion, record replacement, cache build, model training or internal-test logits evaluation.
- Why: freeze the complete defect distribution before selecting a deterministic data-quality policy.
- Alternatives deferred to the next recorded run: bounded interpolation, affected-window exclusion, full-record exclusion with deterministic replacement, or cohort reduction.

## Frozen acceptance criteria

- TDD proves contiguous-run extraction, digital-sentinel capture, half-open feature-support overlap at both boundaries, and no mutation of input arrays.
- Audit covers exactly `912` records from the accepted annotation audit and verifies the expected `.dat` hash for every record; unreadable or contract-invalid records are explicit fatal errors.
- Output includes per-record and aggregate counts by split, affected native symbol, missing-run length and affected feature window; zero missing samples is reported explicitly for clean records.
- Audit artifact and SHA-256 manifest verify locally. `locked_databases_accessed=false`, `signals_modified=false`, `cache_built=false`, `gpu_training_started=false`, and `internal_test_model_evaluated=false`.
- Any subsequent handling method and thresholds require a new run whose rationale is based on this audit; M2k itself cannot authorize cache training.

## Results

- TDD completed and the M2 data-provenance suite passed `26/26`, including contiguous-run extraction, WFDB sentinel capture, half-open `[R-404, R+96)` boundary checks and input immutability.
- Remote audit covered `912/912` records, verified `912/912` `.dat` hashes against the `2,736`-file M2j inventory, and reported `error_count=0`.
- `911` records are fully finite. Exactly one train record, `p05750_s31`, contains two isolated one-sample missing runs at `[95720,95721)` and `[101495,101496)`; validation and internal-test contain zero missing samples.
- The missing samples overlap four native Q feature supports at R samples `95721`, `95822`, `101571`, `101797`; affected N/S/V counts are all zero.
- The audit modified no signal, built no cache, started no GPU training and evaluated no internal-test model logits.
- Evidence: `docs/reports/20260831-073002-m2k-signal-integrity-audit/signal_audit/`; JSON SHA-256 `c13abef95fc3ad509b48fbb8ca94336d5590d432f1ee68bfcae74ea4d1984c6d`.
- Audit tool SHA-256 `5ce5cacc245ac8188218e2d6cf5285bbe66e81ee72ff9610ffe36551e6156f0c`; test file SHA-256 `0f68f41da6954fc92fc5f15b18447a26a227aa6722fffa727bcaed058a005a8c`.

## Decision

- Decision: `接受`（只读信号完整性审计范围）
- Next gate: a separately recorded deterministic replacement policy; M2k does not authorize imputation or training.
