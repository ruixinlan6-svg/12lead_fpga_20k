# Optimization Run: `20260830-091440-m2a-data-provenance-and-label-repair`

## Identity

- Run ID: `20260830-091440-m2a-data-provenance-and-label-repair`
- Stage: `data`
- Status: `completed`
- Started/finished: 2026-08-30 09:14 CST / 2026-08-30 10:12 CST
- Agent/operator: Codex
- Baseline run: `20260829-1815-m1-m2-central-audit-correction`; M1 prerequisite is now satisfied by `20260829-215835-m1g-formal-contract-and-acceptance`
- Git commit: `9ebc08357c427be37e029a4568498f01a64bb7a7`
- Data version and split hash: Icentia11k 1.0 native-annotation audit `cb05cc9a722cf50a8cb3b7288a4fcd6f3fd21a8261f55a3699fa0035b894fc10`; old `cache_ec57_beats_v1` remains rejected
- Config/contract paths: `contracts/ec57_label_mapping_v1.json`, `docs/datasets/data_role_registry.csv`, `contracts/ec57_hybrid_metrics_contract.json`
- Environment: remote alias `ecg-gpu-server`, Windows, Python `lrx_train`; data audit is CPU/read-only until acceptance

## Problem and evidence

- Observed problem: the revoked M2 run reports three-seed VEB Se `42.935%–55.046%`, +P `31.561%–40.840%`, and FPR `4.937%–9.474%`, far outside the frozen gate.
- Evidence from the baseline:
  - `prepare_beat_cache.py` maps a 15-second segment label to individual beat labels using the same RR, width and amplitude heuristics that are later supplied as model features; it does not load authoritative native N/S/V/Q beat annotations.
  - The remote raw cache exposes `windows`, integer segment `labels`, `record_ids`, `sources`, and `families`, but no native beat indices or native beat symbols.
  - Remote cache directory names include development mixtures containing databases frozen as locked by `data_role_registry.csv`; these caches are prohibited from M2 even if locally named `public_only`.
- Primary metric or failure point: data-label validity and leakage precede model optimization; training on heuristic pseudo-labels cannot prove the contracted N/V task.

## Optimization

- Method: audit every candidate cache at the source/record/patient/annotation boundary; fail closed unless each training example traces to a lawful Icentia11k native beat symbol and sample index. Replace the cache builder with a native-symbol pipeline only after a failing regression test proves the old heuristic path is rejected.
- Why this method: the current low metrics are consistent with target leakage and label noise introduced before the model. Architecture or loss changes cannot repair invalid ground truth.
- Alternatives considered and why not selected:
  - Increasing model size/class weight/focal loss: rejected before data validity because it optimizes against unproven labels.
  - PTB-XL record-level PVC labels converted to beat labels: prohibited by the frozen label contract.
  - MIT-BIH/INCART or other locked databases for training: prohibited by the data-role registry.
  - Reusing revoked checkpoints: prohibited by the central audit.
- Expected mechanism: authoritative native N/S/V/Q symbols remove circular heuristic labels and make validation metrics scientifically interpretable.

## Frozen acceptance criteria

- Success threshold:
  - Every sample preserves `database`, `database_version`, `patient_id`, `record_id`, native beat `sample_index`, native symbol, mapped class, and source-file SHA-256.
  - Only Icentia11k 1.0 development data may enter M2 train/validation/internal-test; N/S/V/Q mapping exactly matches `ec57_label_mapping_v1.json`; Q is counted then excluded.
  - Train/validation/internal-test patient intersections are all zero and split assignment is deterministic from patient identity.
  - No input root, source field, family field, record ID, or manifest entry names a locked database or resolves below a locked root.
  - No segment/record diagnosis, RR, amplitude, width, SQI, or model feature is allowed to generate a target label.
  - Cache manifest, split lists, class/source counts, exclusions, environment and SHA-256 inventory are complete.
- Failure/rollback threshold: missing native annotation provenance, any locked-database contamination, any patient overlap, or unavailable lawful Icentia data means no GPU training starts and this run records `reject/continue-to-acquisition` rather than fabricating M2 progress.
- Fixed test set, thresholds and measurement conditions: contract version 1.0.0; patient-level isolation; source-label counts reported separately; no locked external set opened or evaluated.

## Execution

- Entry command or script: `tools/remote/audit_icentia_annotations.py`, followed by `train/ec57/prepare_icentia_native_cache.py` on the remote host
- GPU/card or hardware connection used: none for audit; GPU inventory currently shows cards 0/1/2 without project compute load
- Calibration/Golden sample manifest: not applicable
- Deviations from the plan: none at start

## Results

| Metric | Baseline | This run | Delta | Comparable? |
|---|---:|---:|---:|---|
| Native beat-label provenance | absent | native `atr` symbols audited on 216/216 records | repaired at audit boundary | yes |
| Locked-source contamination | not audited | none; Icentia11k 1.0 only | repaired | yes |
| Patient overlap | claimed zero | deterministic 24/24/24 patient cohorts, overlap 0 | confirmed | yes |
| M2 model gate | failed | not run | - | no training before data acceptance |

- Native annotation audit totals across the frozen cohort: `N=856203`, `S=4338`, `V=4850`, `Q=270385`, other marker `+=13940`; annotation errors `0`.
- The native cache builder downloaded and parsed all 216 records. Before normalization it constructed train/validation/internal-test counts `13,157 / 291,589 / 288,363`.
- Failed samples/first mismatch: no record-level read failure; the first blocking invariant was train-only feature IQR index 3 (`SQI`) equal to zero.
- Logs and report paths: `docs/reports/20260830-091440-m2a-data-provenance-and-label-repair/annotation_audit/annotation_audit.json`; `cache_build_failure.json`.
- Artifact paths and SHA-256: annotation audit `cb05cc9a722cf50a8cb3b7288a4fcd6f3fd21a8261f55a3699fa0035b894fc10`; cache-build failure report `c1063ab37867a226affa707ad354ee17e2607fd113caaeca797ca162d975f7ca`.
- Unverified items: no accepted NPZ cache, no model training, no threshold calibration, no internal-test model evaluation.

## Decision

- Decision: `reject / 回到数据特征构建`
- Reason: native label provenance and isolation were repaired, but the frozen fail-closed normalization gate correctly rejected SQI feature IQR=0. No cache or model is accepted.
- What changed in the project baseline: a native-symbol-only builder and provenance tests now replace the invalid pseudo-label path; M2 remains open and the old model remains revoked.
- One primary question for the next run: can a label-independent, hardware-reproducible continuous SQI definition produce nonzero train IQR without weakening the frozen normalization rule?
