# Optimization Run: `20260830-212025-m2j-q-only-duplicate-timestamps`

## Identity

- Run ID: `20260830-212025-m2j-q-only-duplicate-timestamps`
- Stage: `M2 native annotation duplicate repair and cache build`
- Status: `completed`
- Started/finished: 2026-08-30 21:20 CST / 2026-08-31 07:30 CST
- Agent/operator: Codex
- Baseline: failed M2i cache build; all `2,736` audited source files already present
- Data/model target: unchanged M2i audit, cohort, cache contract and Candidate C configuration

## Problem and evidence

- M2i failed at `p01538_s46`, where the official native annotation has two `Q` symbols at sample `1009032`.
- The builder currently sorts all native beats and requires strictly increasing samples before excluding `Q` from saved model examples. It therefore rejects an exact duplicate unknown-beat marker without distinguishing it from an N/S/V label conflict.
- The scope of duplicate timestamps across all `912` audited records is not yet known and must be measured before changing behavior.

## Optimization

- Audit every downloaded `atr` named by the accepted M2h audit and emit every same-sample native-symbol group with patient, record, sample, ordered symbols and source-file hash.
- Allow only exact `Q-only` duplicate groups. For temporal RR/amplitude feature state, collapse each `Q-only` group to one representative marker; preserve every original Q in the raw audit and `q_excluded_count`. `Q` still produces no training example.
- Any same-sample group containing `N`, `S` or `V`, including mixed `Q` plus an eligible symbol, remains a fatal ambiguity. Out-of-range or decreasing annotations remain fatal.
- Why: this is the smallest deterministic repair that preserves unknown-beat timing while preventing a duplicate source marker from creating a zero RR interval.
- Alternatives rejected: silently drop every duplicate, skip all Q from temporal history, keep one arbitrary N/S/V label, jitter timestamps, or remove the affected record/patient.

## Frozen acceptance criteria

- TDD proves: duplicate Q-only markers produce exactly the same saved examples/features as one Q marker; raw Q counting remains unchanged outside feature normalization; duplicate groups containing N/S/V fail closed; ordinary strictly increasing records are unchanged.
- Full duplicate audit covers exactly the M2h `912` records and `2,736` hashed source files, lists every same-sample group, reports zero unreadable files, and has zero non-Q-only duplicate groups. If this condition is false, stop and create a new decision run.
- Cache build reuses the already downloaded source files without network-dependent label substitution and meets every unchanged M2i cache gate: audit hash, record/file counts, `256/24/24` patients, zero overlap, validation/internal identities, native N/S/V, Q counted/excluded, four positive train IQRs, provenance validation and hash-complete manifest.
- Formal validation-only seed-17 training may start only after the cache audit passes. Its configuration and `+P >=95%`, `FPR <=0.25%`, then max-Se threshold rule remain unchanged from M2i.
- No internal-test model evaluation occurs in this run unless a later, separately recorded full-cohort three-seed freeze explicitly authorizes it.

## Results

- TDD completed: the M2 data-provenance suite passed `24/24`. Exact Q-only duplicates are collapsed only for feature-state processing; raw beat inputs are not mutated; any duplicate group containing N/S/V fails closed.
- Full remote duplicate audit covered `912` records and rehashed all `2,736` source files. It found `7` same-sample groups: `7` Q-only, `0` containing N/S/V, with `0` read errors and no locked database access.
- Duplicate audit evidence: `docs/reports/20260830-212025-m2j-q-only-duplicate-timestamps/duplicate_audit/`; JSON SHA-256 `c4d52eab779084f63d8ef9b11b2f81e6155034b8a453c653eac49e64c6fdf950`.
- The rebuilt cache passed the original duplicate-Q failure point but stopped at record position `461/912`, train record `p05750_s31`, because its physical signal contains two NaN samples at indices `95720` and `101495`.
- Direct source inspection showed both NaNs map to WFDB digital missing-value sentinel `-32768`; signal length is `1,048,577`, sampling rate `250 Hz`, and source `.dat` SHA-256 is `23447882b420fedd38979ff6ed38a2dbb5e7b4db1bf72d1780e093bd9f679090`.
- Cache failure evidence: `docs/reports/20260830-212025-m2j-q-only-duplicate-timestamps/cache_build_failure.json`, SHA-256 `64f55f7001fd54b33fb0c2770b014445d2e006495ce7b9334166fb5cfd1053a4`.
- No cache manifest was written, GPU training did not start, and internal-test model evaluation did not occur.

## Decision

- Decision: `部分接受；回到训练`（接受重复 Q 修复，拒绝不完整缓存）
- Reason: duplicate-timestamp policy is proven, but the unchanged complete-cache gate failed on a separate source-signal integrity defect. A full signal audit must precede any repair policy.
