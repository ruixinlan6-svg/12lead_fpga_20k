# Optimization Run: `20260826-1602-m1-ptbxl-async-retry`

## Identity

- Stage: M1 PTB-XL failed-file retry
- Date: 2026-08-26
- Owner: Codex implementation agent
- Status: superseded_incomplete
- Baseline: `20260826-1557-m1-ptbxl-async-full`

## Problem and evidence

- The async full-tree pass completed all but a small finite set of records; the failure log contains 17 connection failures and no checksum mismatch. Its apparent 21,798-record completion was later shown to omit one path because the published `RECORDS` file has a missing newline.

## Optimization

- Method: rerun the same checksum-verifying async downloader with lower concurrency (8 workers) so only missing/failed files are fetched and existing verified files are reused.
- Why this method: reduce transient connection pressure while preserving the exact PTB-XL source and hash contract.

## Frozen acceptance criteria

- All 21,799 `records100/*_lr` pairs have matching published SHA-256 values.
- No `.part` files remain and the failure log is absent or empty after completion.
- No GPU or FPGA state is modified by this data-only retry.

## Execution

- Remote root: private `LRX/12lead_fpga_20k_m1/data/ptb-xl/1.0.3`.
- Concurrency: 8 workers; retries: 8.

## Results

- Remote retry reported `failures=0`, but selected only 21,798 paths. A later parser audit found `records100/21000/21837_lr` was silently omitted.

## Decision

- Superseded by `20260826-1611-m1-ptbxl-record-parser-fix`; do not use this run as a full-data acceptance.
