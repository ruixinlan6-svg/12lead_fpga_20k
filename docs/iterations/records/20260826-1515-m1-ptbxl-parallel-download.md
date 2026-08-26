# Optimization Run: `20260826-1515-m1-ptbxl-parallel-download`

## Identity

- Stage: M1 PTB-XL data acquisition
- Date: 2026-08-26
- Owner: Codex implementation agent
- Status: aborted_superseded_by_parallel64
- Baseline run: `20260826-1455-m1-ptbxl-fp32` (sequential download attempt)

## Problem and evidence

- Sequential per-file download was too slow for the 21,798-record `records100` tree and was stopped after partial progress.
- Existing partial files are valid and must be reused only after SHA-256 verification.

## Optimization

- Method: bounded parallel download with a fixed worker count, atomic `.part` files, reuse of existing non-empty files, and per-file SHA-256 logging.
- Why this method: reduce wall-clock time without changing dataset contents or touching unrelated remote directories.
- Alternatives considered: download the 500 Hz tree or use unrelated cached datasets. Both rejected because they violate the 100 Hz contract or task provenance.

## Frozen acceptance criteria

- Only PTB-XL 1.0.3 `records100/*_lr.{hea,dat}` plus official metadata.
- No deletion of partial/complete files; failed requests remain retryable.
- Registry must report 21,388 labeled records, no patient overlap across folds, and metadata hashes matching the downloaded source.
- Dataset remains remote/private; no raw waveform enters Git.

## Execution

- Remote root: private `LRX/12lead_fpga_20k_m1/data/ptb-xl/1.0.3`.
- Worker count: 16; the attempt was stopped after throughput remained too low. Partial files are retained for safe reuse.

## Results

- No data integrity error was observed; the transfer was stopped for performance, before completion. No training started.

## Decision

- Decision: **supersede with a 64-worker attempt**; the bounded parallel method remains unchanged, but the concurrency setting is recorded as a new run.
