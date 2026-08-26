# Optimization Run: `20260826-1611-m1-ptbxl-record-parser-fix`

## Identity

- Stage: M1 PTB-XL full-acquisition integrity repair
- Date: 2026-08-26
- Owner: Codex implementation agent
- Status: passed_full_acquisition
- Baseline: `20260826-1602-m1-ptbxl-async-retry`

## Problem and evidence

- Three formal FP32 candidates failed before completing validation because `records100/21000/21837_lr.hea` was absent.
- The official `RECORDS` file contains 21,799 low-resolution paths, but one section boundary lacks a newline. The previous line-based parser selected 21,798 paths and silently dropped `records100/21000/21837_lr`.
- The downloaded files therefore passed a self-consistent but incomplete count; this is not an acceptable full-data gate.

## Optimization

- Method: parse `RECORDS` with a strict `records100/[0-9]{5}/[0-9]{5}_lr` path pattern, de-duplicate, sort, and fail if no paths are found.
- Why this method: it repairs the source-format edge case without changing the dataset, URL layout, checksum contract, labels, or model code.

## Frozen acceptance criteria

- Selected low-resolution paths: 21,799, including `records100/21000/21837_lr`.
- Every selected `.hea` and `.dat` matches the published `SHA256SUMS.txt` entry.
- No `.part` files remain; a fresh registry and at least one training data-loader pass can open every labeled entry.
- No Flash write; this run changes only private remote dataset files and local scripts/records.

## Execution

- Rerun completed on `ecg-gpu-server` under `C:/Users/Administrator/Desktop/LRX/12lead_fpga_20k_m1` with 8 workers and 8 retries.

## Results

- Selected 21,799 paths; `.hea=21,799`, `.dat=21,799`, `.part=0`; the retry reported `failures=0` and published SHA-256 verification passed. The repaired path `records100/21000/21837_lr` is present.
- Regenerated registry: 21,388 labeled records, 18,617 patients, official folds 1–8/9/10, manifest SHA-256 `b1ee5de4ee2efd25cb76797444d89c19e5d21c25678532ea347fca6459b2aad0`.

## Decision

- Full acquisition and registry gates passed. The resulting registry is accepted for the M1 FP32 retry; historical first-pass failure logs remain as provenance and are not treated as current failures.
