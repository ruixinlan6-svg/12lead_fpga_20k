# Optimization Run: `20260826-1634-m2-ptq-full-checkpoint`

## Identity

- Stage: M2 complete-checkpoint INT8 PTQ
- Date: 2026-08-26
- Owner: Codex implementation agent
- Status: passed_ptq
- Baseline: `20260826-1613-m1-ptbxl-full-fp32-retry`

## Problem and evidence

- The full PTB-XL FP32 reference is now valid across all 21,388 labeled records and three seeds. The previous PTQ result was a bounded smoke and cannot support deployment claims.
- Seed1 is selected using validation only (highest macro AUROC/AUPRC/F1 among the three completed seeds); the test fold remains untouched for model selection.

## Optimization

- Method: run the existing static per-tensor symmetric INT8 PTQ on the complete seed1 checkpoint, with 2,048 deterministic train records for activation calibration and all validation/test rows for evaluation; emit INT8 weights, scales, contract, golden vectors, and metrics.
- Why this method: increase calibration/evaluation coverage while preserving the frozen arithmetic semantics and avoiding a new architecture or quantizer.

## Frozen acceptance criteria

- Checkpoint SHA-256 matches the recorded seed1 artifact from M1.
- Registry/manifest SHA-256 matches the complete-data registry; no missing waveform is tolerated.
- Outputs include `weights_int8.pt`, `quantization_contract.json`, `golden_vectors.npz`, and `metrics_int8.json` with explicit calibration/evaluation sizes and FP32-to-INT8 deltas.
- No FPGA or Flash operation is part of this run.

## Execution

- Remote root: private `C:/Users/Administrator/Desktop/LRX/12lead_fpga_20k_m1`.
- Planned output: `runs/20260826-1634-m2-ptq-full-checkpoint/seed1`.

## Results

- Output artifacts were generated on the complete registry using 2,048 calibration records and all available validation/test rows (the script limit 2,158 exceeds both split sizes). Seed1 FP32 vs INT8:
  - validation macro AUROC `0.8728871482` -> `0.8724959775` (delta `-0.0003911708`); macro F1 `0.6591438906` -> `0.6560869986` (delta `-0.0030568921`).
  - test macro AUROC `0.8578462158` -> `0.8577429873`; macro AUPRC `0.6833083776` -> `0.6829404874`; macro F1 `0.6344021345` -> `0.6287488427`.
- Artifact SHA-256: `weights_int8.pt` `2AF6FF4FC65E2C9F9B4A70714B6776CE85D7E3122C5C8CBFC9ECD12E3E7E6D9F`; `quantization_contract.json` `6FB4B332DBBE42F2FEC25A4256F402185F49E7CAAF9FEF2425AA0C59A9686E76`; `golden_vectors.npz` `2FAF8B77D7BFC03BF52C4AF891F2D71007BDD8B92CDE079B58CE1A4B24C08877`; `metrics_int8.json` `86AC6A49E03773901508EA1F3A172EFC675EA04EC2494413B3111AF5DA9D4C64`.

## Decision

- PTQ accepted as the full-checkpoint INT8 research artifact. The small validation delta supports proceeding to golden-vector RTL integration; it is not a clinical accuracy claim.
