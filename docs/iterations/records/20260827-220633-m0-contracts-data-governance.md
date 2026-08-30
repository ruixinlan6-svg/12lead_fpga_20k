# Optimization Run: `20260827-220633-m0-contracts-data-governance`

## Identity

- Run ID: `20260827-220633-m0-contracts-data-governance`
- Stage: `data`
- Status: `completed`
- Started/finished: `2026-08-27T22:06:33+08:00 / 2026-08-27T22:17:03+08:00`
- Agent/operator: Codex
- Baseline run: None; M0 contract and data-governance baseline was absent
- Git commit: `6e618a2cb509fb8eb252d2ac346bdf3c3694e776` (pre-existing dirty worktree preserved)
- Data version and split hash: No database downloaded; split manifests intentionally not created in M0
- Config/contract paths: M0 exclusive deliverables listed in the user task
- Environment: Windows PowerShell; Python standard-library `unittest`; no GPU, database, FPGA tool, board, or network use

## Problem and evidence

- Observed problem: The QN88 EC57 hybrid contract, label mapping, dataset-role registry, contamination ledger, locked-run receipt schema, M0 README, and contract tests did not exist.
- Evidence from the baseline: All nine M0 deliverable paths were missing. The existing PTB-XL contract `contracts/ecg_io_contract.json` existed and had pre-change SHA-256 `8719A3D537A4A76315ED4C42075B1A56B3A3E86DFBB7CC4227E16F7486110C71`.
- Primary metric or failure point: No auditable contract existed to reject wrong lead order, sampling rate, window/R index, locked-data contamination, patient leakage, invalid metric denominators, or missing schema fields.

## Optimization

- Method: Create the M0 JSON contracts, JSON Schemas, CSV governance ledgers, training/evaluation boundary README, and executable standard-library contract tests from the 2026-08-27 QN88 EC57 hybrid plan and its referenced research documents.
- Why this method: It establishes a single machine-readable source for the frozen 250 Hz/12-lead/int16 interface, 160-point beat window, R index 64, four auxiliary features, non_VEB/VEB output, error states, research events, EC57-style metric formulas, and development-versus-locked data roles before any data or model execution.
- Alternatives considered and why not selected: No data download, training, PTQ, GPU connection, RTL change, synthesis, board operation, or update to the central iteration index is in scope for M0; those would introduce external state or exceed the exclusive file list.
- Expected mechanism: Contract validation fails closed on schema omissions and incompatible values; governance validation fails closed when a locked database appears in train/calibration/golden/debug use or when patient IDs cross splits.

## Frozen acceptance criteria

- Success threshold:
  - All nine user-listed M0 deliverables plus this record exist and JSON files parse.
  - IO contract freezes 250 Hz; exact lead order `I, II, III, aVR, aVL, aVF, V1, V2, V3, V4, V5, V6`; signed int16 little-endian; `5 µV/LSB`; 160-point beat window; R index 64; four auxiliary features; `[non_VEB, VEB]` output; error states and research event definitions.
  - Metrics contract contains QRS Se, QRS +P, VEB Se, VEB +P, VEB FPR with raw counts/formulas and nonzero-denominator rules; HR; quantization degradation; bit-exact; LUT/BSRAM/DSP resource; timing; and HIL thresholds.
  - Data roles explicitly encode Icentia11k as development/internal and research-license restricted; LUDB as QRS/delineation development; INCART as complete locked 12-lead external evaluation; MIT-BIH Arrhythmia, AHA, and NST as locked and prohibited for training, PTQ/calibration, tuning, or golden/debug use.
  - Label mapping explicitly preserves Icentia `V` as positive, named `N`/`S` as `non_VEB`, reports `S` separately, excludes `Q` from loss/metric denominators while counting it, and forbids silent conversion.
  - Contract tests cover wrong lead order, wrong sampling rate, wrong window/R index, locked data in train/calibration, patient cross-split, invalid metric denominator, and missing schema fields; locked databases in train/calibration must fail.
  - `python -m unittest discover -s tests/ec57 -p "test_contracts.py" -v` returns success.
  - Existing `contracts/ecg_io_contract.json` remains byte-identical.
- Failure/rollback threshold: Any schema parse failure, missing required field, permissive locked-data configuration, patient leakage acceptance, numeric output for a zero denominator, old-contract hash change, or unauthorized file change rejects M0. No rollback of unrelated pre-existing dirty files is allowed.
- Fixed test set, thresholds and measurement conditions: Standard-library tests only, no network, no database paths required, no GPU, no FPGA tools, and no board/Flash/SDRAM action. Central `docs/iterations/INDEX.md` is intentionally not edited per task instruction; therefore this run cannot be formally closed until central review registers it.

## Execution

- Entry command or script: `python -m unittest discover -s tests/ec57 -p "test_contracts.py" -v`
- GPU/card or hardware connection used: None; explicitly prohibited for this run
- Calibration/Golden sample manifest: None; database and golden data are out of scope
- Deviations from the plan: The plan requests updating `docs/iterations/INDEX.md`; the user explicitly prohibits that update. The final status must remain pending central review/index registration even if all local checks pass.

## Results

| Metric | Baseline | This run | Delta | Comparable? |
|---|---:|---:|---:|---|
| M0 deliverable files | 0/9 | 9/9 | +9 | Yes |
| Contract test cases | 0 | 15 passed | +15 | Yes |
| Existing PTB-XL contract SHA-256 | `8719A3D537A4A76315ED4C42075B1A56B3A3E86DFBB7CC4227E16F7486110C71` | `8719A3D537A4A76315ED4C42075B1A56B3A3E86DFBB7CC4227E16F7486110C71` | 0 | Yes |
| Database downloads / GPU / training / FPGA operations | 0 | 0 | 0 | Yes |

- Per-class or per-layer findings: IO freeze and negative validation cover the exact lead order, 250 Hz, 5 µV/LSB, 160/64 beat window, four auxiliary features, non_VEB/VEB output, integrity states, event definitions, five EC57-style metrics, HR, quantization, bit-exact, resource, timing, and HIL gates. Data governance covers the required development/internal and locked roles, patient grouping, contamination downgrade, and explicit Icentia N/S/V/Q mapping.
- Failed samples/first mismatch: None; no ECG samples or database files were accessed.
- Logs and report paths: `python -m unittest discover -s tests/ec57 -p "test_contracts.py" -v` — `Ran 15 tests in 0.005s`, `OK`.
- Artifact paths and SHA-256:
  - `contracts/ec57_hybrid_io_contract.json`: `b8807311d36f42a141ac169c109bb707127e84d414f08e76f6c77d81f6adf718`
  - `contracts/ec57_hybrid_metrics_contract.json`: `45a91e61ac4fd5f02a882b7a3ecc8c31d3d6f8c5e845f31bca7114fe5776aa95`
  - `contracts/ec57_label_mapping_v1.json`: `e32911ceb539aa4844d81bffb02c6970b4ed1014db7e683be51e6a113308849e`
  - `docs/datasets/ec57_dataset_manifest.schema.json`: `e52ab49698abff1645c95e1cc1a9da5b71baa3d5e7b66627f23c54fc4a5f8ba6`
  - `docs/datasets/data_role_registry.csv`: `dd231aac7514cacf30190de1a6c3cced0a104b722c5a8c11a122f23b50f13b9e`
  - `docs/datasets/contamination_log.csv`: `570de70fb111cdababe091e8482b6f8737c9c64fc71cf0637adb38bacbe077a9`
  - `docs/datasets/locked_run_receipt.schema.json`: `1513b009b09cf1eb3a0d2a0795346ac5ec1c0dc16e8bc6be4237b90d80640027`
  - `train/ec57/README.md`: `5da9d62551b5bb19875cc51e170fdfc74be0680dca299c56b9cf4402ee6264cc`
  - `tests/ec57/test_contracts.py`: `eda104742f3bc96794299d5124d29850c93edee0f9fc37206e50afdeeb23d729`
  - The final SHA-256 of this iteration record is reported after this file is finalized; a file cannot contain its own final hash without changing that hash.
- Unverified items: No real database manifest, license acquisition, WFDB `bxb` execution, model metrics, PTQ, integer golden, RTL, synthesis/PnR, SRAM/HIL, SDRAM, or board behavior is verified in M0. The JSON files were parsed and required-field regression cases were exercised; full external JSON Schema validation is deferred to the later tooling environment.

## Decision

- Decision: `continue`
- Reason: All local M0 deliverables and contract tests pass, but the user explicitly prohibited updating `docs/iterations/INDEX.md`. Awaiting central review registration in INDEX means M0 is not formally closed.
- What changed in the project baseline: Added only the nine user-listed M0 deliverables and this unique iteration record. The existing PTB-XL contract is byte/hash unchanged; no database, GPU, training, FPGA, synthesis, download, Flash, or SDRAM operation was performed.
- One primary question for the next run: After central review registers this run in `docs/iterations/INDEX.md`, can M1 consume these contracts without changing their frozen semantics?
