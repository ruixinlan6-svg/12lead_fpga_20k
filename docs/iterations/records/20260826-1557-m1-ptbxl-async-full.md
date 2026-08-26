# Optimization Run: `20260826-1557-m1-ptbxl-async-full`

## Identity

- Stage: M1 PTB-XL full data acquisition
- Date: 2026-08-26
- Owner: Codex implementation agent
- Status: superseded_transient_failures
- Baseline: `20260826-1535-m1-ptbxl-parallel64`

## Problem and evidence

- The previous per-file `urllib` implementation suffered repeated `WinError 10060` timeouts under 64 workers.
- PhysioNet exposes the PTB-XL tree as many small files; a persistent async HTTP session should remove most connection setup overhead.

## Optimization

- Method: `aiohttp` connection pool with bounded concurrency, retry/backoff, atomic `.part` files, resume-by-hash, and verification against the published `SHA256SUMS.txt`.
- Why this method: improve transfer throughput without changing source bytes or silently accepting corrupt partial files.
- Alternatives considered: more threads in `urllib` (already failed), changing sampling rate (violates contract), or downloading an unverified mirror (provenance risk).

## Frozen acceptance criteria

- PTB-XL 1.0.3 `records100/*_lr.{hea,dat}` only.
- All metadata and waveform files selected by `RECORDS` pass the published SHA-256 values.
- Existing valid files are reused; no raw data or credentials enter Git.
- Any failed records are written to a retryable failure log and the run is not marked complete.

## Execution

- Remote root: private `LRX/12lead_fpga_20k_m1/data/ptb-xl/1.0.3`.
- Remote environment: `lrx_train` Python with `aiohttp` available.
- Candidate transfer concurrency: 32 workers; GPU processes are not touched.

## Results

- The 32-worker pass ended with 17 transient connection failures; no checksum mismatch was accepted. The finite failures were retried at lower concurrency.

## Decision

- Superseded by `20260826-1602-m1-ptbxl-async-retry`; a later parser audit also found the line-boundary omission documented in `20260826-1611-m1-ptbxl-record-parser-fix`.
