# Optimization Run: `20260830-150859-m2h-deterministic-annotation-fallback`

## Identity

- Run ID: `20260830-150859-m2h-deterministic-annotation-fallback`
- Stage: `M2 data acquisition repair`
- Status: `completed`
- Started/finished: 2026-08-30 15:09 CST / 2026-08-30 19:33 CST
- Agent/operator: Codex
- Baseline run: `20260830-145534-m2g-train-cohort-scale256`
- Target cohort: unchanged train/validation/internal-test patients `256/24/24`, three valid native-annotation records per patient

## Problem and evidence

- Source inventory listed two train records whose official `.atr` files return 404, leaving one patient with fewer than three accepted records and audit errors.
- Other deterministic records for that patient are available; choosing only the first three inventory entries without checking annotation readability is too brittle.

## Optimization

- Method: order every patient record by the existing SHA-256 rule, then scan in that order until three readable native `atr` records are accepted. Record each unavailable candidate as an exclusion with patient, record and exception; fail only if three valid records cannot be obtained.
- Preserve the same patient lists and the original selected records for every patient that has no unavailable annotation.
- Why: deterministic fallback maintains sample count and provenance without fabricating labels or silently dropping a patient.
- Alternatives rejected: ignore the two errors, reduce that patient to one record, replace the patient, or hand-pick record IDs.

## Frozen acceptance criteria

- Unit test proves fallback is deterministic, records every failed candidate, and takes the next readable records.
- Audit has exactly 912 accepted records, 304 patients, zero fatal errors, and explicit exclusions for the two known 404 records.
- Validation/internal-test patient and record lists are byte-for-byte identical to M2b.
- Only native Icentia annotations are used; no signal/model/internal-test evaluation occurs during audit.
- Subsequent cache and training gates remain those frozen in M2g.

## Results

- Added deterministic readable-record fallback and an explicit exclusion ledger. The focused red test failed with the expected missing import before implementation; the completed M2 data-provenance suite passed `21/21`.
- Remote native-annotation audit accepted exactly `912/912` records from `304` patients (`256/24/24`), with `exclusion_count=2` and `error_count=0`.
- Both exclusions are source-side HTTP 404 annotation files for train patient `p09486`: `p09486_s36.atr` and `p09486_s49.atr`. The next two readable records in the frozen digest order were selected; no patient or label was fabricated or silently dropped.
- Native audit totals: `N=3,457,560`, `S=30,620`, `V=31,258`, `Q=1,171,551`; other marker `+=56,607`.
- The validation and internal-test patient arrays and ordered `(patient_id, record_id)` arrays are exactly equal to the M2b audit (`24` patients and `72` records in each split).
- The audit declares `signals_downloaded=false` and `locked_databases_accessed=false`; no cache, model training, GPU evaluation or internal-test model evaluation occurred.
- Evidence: `docs/reports/20260830-150859-m2h-deterministic-annotation-fallback/annotation_audit/`.
- SHA-256: audit JSON `b12a91abe18e7247d6afe7973c4f1df2e4539f35172a241f0fb9c63f7fc52e7c`; audit tool `35648d06c12685109d9d3fcaa717e67c275e2faee7023012562de5b3ecbbf106`; test file `c8c1d4f984c9b0c0bf1516ec1aeb6604cbc81fb53bc16bad149ef337a630b186`.

## Decision

- Decision: `接受`（仅限确定性数据审计修复）
- Next gate: a new run must build and audit the signal cache before validation-only GPU training.
