# Optimization Run: `20260828-0855-m0-central-review`

## Identity

- Run ID: `20260828-0855-m0-central-review`
- Stage: `data`
- Status: `completed`
- Started/finished: `2026-08-28T08:54:45+08:00 / 2026-08-28T08:57:25+08:00`
- Agent/operator: Codex central reviewer
- Baseline run: `20260827-220633-m0-contracts-data-governance`
- Git commit: `6e618a2cb509fb8eb252d2ac346bdf3c3694e776` (working-tree review; no commit created)
- Data version and split hash: N/A; no database downloaded or opened
- Config/contract paths: `contracts/ec57_hybrid_*.json`, `contracts/ec57_label_mapping_v1.json`, `docs/datasets/*`, `train/ec57/README.md`
- Environment: Windows PowerShell; Python standard-library `unittest`; no GPU, network, database, FPGA tool or board use

## Problem and evidence

- Observed problem 1: the original registry allowed Icentia11k for development/training but prohibited `golden or RTL debug; board debug`, while the frozen M3/M4/M5 plan requires development/internal manifests to generate integer Golden vectors and perform RTL/HIL development. Keeping that prohibition would make the planned closed loop impossible.
- Observed problem 2: the M0 plan explicitly requires rejecting a locked database root in a training configuration, but the original 15-test suite rejected only registered database names and had no path-root negative test.
- Evidence boundary: the original JSON files parse and the original 15 tests pass, but full third-party JSON Schema validation is not claimed because the local Python environment does not contain `jsonschema`.

## Optimization

- Method:
  1. Correct the Icentia11k registry to permit frozen integer Golden generation and RTL/HIL development from development/internal manifests, while retaining the research-license restriction and all locked-database prohibitions.
  2. Add a filesystem-independent Windows path containment validator and a negative test covering a locked root and its descendants in `train`.
  3. Add a positive regression proving Icentia development/internal data remains available for frozen Golden and debug contexts.
  4. Update the M0 README so the role boundary matches the registry and main plan.
- Why this method: it resolves the smallest contract contradiction without changing sampling, lead order, label semantics, metric thresholds, dataset roles, locked-data policy or the old PTB-XL contract.
- Alternatives rejected: allowing locked databases for debug; weakening the M3/M4 Golden requirement; relying on substring path matching that would confuse sibling paths.

## Frozen acceptance criteria

- All 15 original tests continue to pass.
- A locked root and any descendant are rejected in a training context; an unrelated development root is accepted.
- Icentia11k is accepted for frozen Golden, RTL debug and board-development debug, but remains research-only and patient/manifest isolated.
- Core IO, metrics and label-contract SHA-256 values remain unchanged.
- `contracts/ecg_io_contract.json` remains byte-identical.
- No data download, GPU, training, quantization, RTL, synthesis, board, Flash or SDRAM action occurs.

## Execution

- Command: `python -m unittest discover -s tests/ec57 -p "test_contracts.py" -v`
- Hardware/GPU used: None
- Deviation: the central review fixes began during review before this separate superseding record was created. This record makes that sequence explicit; the original worker record is preserved and not overwritten.

## Results

| Metric | Baseline | Reviewed result | Status |
|---|---:|---:|---|
| Contract tests | 15/15 | 17/17 | PASS |
| Locked-root path rejection | absent | root and descendant rejected | PASS |
| Icentia Golden/RTL/HIL role consistency | contradictory | consistent with M3–M5 | PASS |
| Core IO/metrics/label hashes | frozen | unchanged | PASS |
| Old PTB-XL contract hash | `8719A3D537A4A76315ED4C42075B1A56B3A3E86DFBB7CC4227E16F7486110C71` | unchanged | PASS |

- Artifact paths and SHA-256:
  - `contracts/ec57_hybrid_io_contract.json`: `B8807311D36F42A141AC169C109BB707127E84D414F08E76F6C77D81F6ADF718`
  - `contracts/ec57_hybrid_metrics_contract.json`: `45A91E61AC4FD5F02A882B7A3ECC8C31D3D6F8C5E845F31BCA7114FE5776AA95`
  - `contracts/ec57_label_mapping_v1.json`: `E32911CEB539AA4844D81BFFB02C6970B4ED1014DB7E683BE51E6A113308849E`
  - `docs/datasets/ec57_dataset_manifest.schema.json`: `E52AB49698ABFF1645C95E1CC1A9DA5B71BAA3D5E7B66627F23C54FC4A5F8BA6`
  - `docs/datasets/data_role_registry.csv`: `3AD5AB75840AEA3E78F14814566383D0FEDD6365A8E7E8EFA532B677DE2B6F4C`
  - `docs/datasets/contamination_log.csv`: `570DE70FB111CDABABE091E8482B6F8737C9C64FC71CF0637ADB38BACBE077A9`
  - `docs/datasets/locked_run_receipt.schema.json`: `1513B009B09CF1EB3A0D2A0795346AC5EC1C0DC16E8BC6BE4237B90D80640027`
  - `train/ec57/README.md`: `EE10F923678885E22D7618BD4EB09592803204E96EFFFB447F4C6B2A47D94DA3`
  - `tests/ec57/test_contracts.py`: `E8215AA5D62BC4770855F6BDA9A3C86B36FB6169C34F46EAECF951AAA3B9C094`
- Unverified items: real dataset manifests, data licenses, authorized EC57 mapping, full JSON Schema engine behavior, data download, training, PTQ/QAT, integer Golden contents and all hardware behavior.

## Decision

- Decision: `接受`
- Scope: M0 contract/data-governance baseline only; this is not acceptance of any clinical claim, database validation, model or hardware implementation.
- Reason: the central review contradiction and missing locked-root test are corrected, 17/17 tests pass, frozen core contract hashes remain unchanged, and the index can now register the reviewed baseline.
