# Optimization Run: `20260831-180114-m2ab-lookahead-contract-boundary-repair`

## Identity

- Run ID: `20260831-180114-m2ab-lookahead-contract-boundary-repair`
- Stage: `data`
- Status: `completed`
- Started/finished: `2026-08-31 18:01 CST / 2026-08-31 18:50 CST`
- Agent/operator: Codex
- Baseline run: `20260831-155500-m3a-ectopic-coupling-representation`
- Git commit: `b1d5b9150a158025cb36134c78d7db2a0f7a9e3e`
- Data version and split hash: Icentia11k 1.0; reuse frozen patient split; rebuilt cache hashes pending
- Config/contract paths: `contracts/ec57_hybrid_io_contract.json`; new lookahead addendum pending
- Environment: local Python `D:/software/anaconda/envs/torch_evn/python.exe`; remote GPU only after local contract/tests pass

## Problem and evidence

- Observed problem: exploratory 6/8-feature caches fabricate first/last post-RR context and silently change the 4-feature cache-builder default; the frozen 450 ms output latency cannot describe a next-QRS-triggered decision.
- Evidence from the baseline: independent specification and standards reviews both identified the contract conflict; M3a validation max `VEB +P=90.00%` at `VEB Se=34.98%`, so the clinical development gate remains closed.
- Primary metric or failure point: deployment-faithful causality/provenance first; then validation `VEB +P >=95%`, `VEB Se >=90%`, `VEB FPR <=0.25%` at one frozen threshold.

## Optimization

- Method: preserve the 4-feature v1 default; introduce an explicit versioned one-beat-lookahead addendum and exact cache feature metadata; exclude and count beats without real previous/next QRS context; fail closed on model/cache schema mismatch.
- Why this method: removes synthetic evidence and makes the approved post-RR experiment reproducible without silently changing the deployed v1 interface.
- Alternatives considered and why not selected: synthetic median post-RR is non-deployable; silently replacing the v1 contract breaks compatibility; proceeding directly to more GPU search would optimize against invalid inputs.
- Expected mechanism: regenerated validation metrics will represent exactly the information available when `R[i+1]` arrives, with explicit start/end boundary accounting.

## Frozen acceptance criteria

- Success threshold: old 4-feature behavior remains the default; lookahead cache carries exact feature order/version; no emitted lookahead example lacks real previous and next beat context; all EC57 tests pass; no database-derived NPZ is staged for Git.
- Failure/rollback threshold: any v1 default regression, fabricated boundary feature, internal-test access during tuning, contract/schema mismatch accepted, or test failure.
- Fixed test set, thresholds and measurement conditions: local unit/contract suite only for this repair; no internal-test metric and no locked database access.

## Execution

- Entry command or script: pending
- GPU/card or hardware connection used: none until repair passes locally
- Calibration/Golden sample manifest: not applicable
- Deviations from the plan: first rebuild incorrectly used the pre-signal-integrity M2h audit and failed closed at record 461/912 on non-finite `p05750_s31`. No output cache files were produced. Retry uses the accepted M2l revised audit (`SHA-256 cf3687eacabd8ea9cc772019f9666a6fb24d9b8f4bcc384e3579c7e861c9c4a4`), which deterministically replaces that record with finite same-patient records `s18/s26/s48`; retry output is isolated as `native_cache_retry1`.

## Results

| Metric | Baseline | This run | Delta | Comparable? |
|---|---:|---:|---:|---|
| EC57 tests | 186/186 | 192/192 | +6 tests | yes |
| Boundary feature fabrication | present | none; real-context exclusion | repaired | yes |
| VEB gate | fail | not evaluated | N/A | no |
| Quantization/parity error | not evaluated | not evaluated | N/A | no |

- Per-class or per-layer findings: corrected cache counts are train `145,134` (`V=29,027`), validation `291,520` (`V=1,414`), internal_test `288,303` (`V=802`); patient counts remain `251/24/24` with zero cross-split overlap. Real-context exclusions are `66/112/118` respectively.
- Failed samples/first mismatch: first attempt stopped at `p05750_s31` because of non-finite source samples; root cause was selection of the obsolete M2h audit rather than the accepted M2l revised audit.
- Logs and report paths: remote `runs/20260831-180114-m2ab-lookahead-contract-boundary-repair/native_cache_retry1`; public metadata mirror `docs/reports/20260831-180114-m2ab-lookahead-contract-boundary-repair/native_cache/`.
- Artifact paths and SHA-256: `config.json d69ef5e3090d6d35722085f0e099147240bf59107b569f96605afc2675da8a4c`; `dataset_manifest.json 984839a123032587731f590dd570029dc553d901cf1dfe25b2136f3763f8d812`; `normalization.json 255ed904237d9f5577233d0124b238f9dd7be4bbb70567a68a0c6f90030cb2e7`; NPZ hashes are retained in `sha256_manifest.txt` but database-derived NPZ files are not committed.
- Unverified items: regenerated cache, GPU training, internal test, quantization, RTL, FPGA

## Decision

- Decision: `accept`
- Reason: data/contract repair passed all local tests and rebuilt all 912 records with explicit real context, exact feature schema and complete boundary accounting; this accepts only the M2 lookahead data baseline, not a VEB model.
- What changed in the project baseline: v1 four-feature default is preserved; experimental v2 lookahead contract and corrected cache become the only valid post-RR research input.
- One primary question for the next run: can ranking-aligned AP checkpoint selection reach the frozen validation target without changing deployment cost?
