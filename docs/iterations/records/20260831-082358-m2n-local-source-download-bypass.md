# Optimization Run: `20260831-082358-m2n-local-source-download-bypass`

## Identity

- Run ID: `20260831-082358-m2n-local-source-download-bypass`
- Stage: `M2 cache source acquisition performance repair`
- Status: `completed`
- Started/finished: 2026-08-31 08:23 CST / 2026-08-31 08:47 CST
- Agent/operator: Codex
- Baseline: M2m restart using the unchanged M2l audit and already downloaded source tree
- Model config: unchanged `candidate_c_dequantized`, seed `17`, validation-only threshold selection

## Problem and evidence

- The restarted builder made no local read progress across two checks and accumulated only about 0.6 seconds of CPU in more than one minute.
- PID `20848` had two established HTTPS connections to `18.25.8.254:443`, proving it was still inside remote WFDB acquisition checks rather than local hashing or feature construction.
- M2i already downloaded all `2,736` selected source files and M2l verified their presence; calling `wfdb.dl_files(..., overwrite=False)` again performs unnecessary network work and can stall independently of the local dataset.

## Optimization

- Add a deterministic acquisition helper: if every required relative source path is already a regular file, do not call WFDB download; if any path is missing, retain the original `wfdb.dl_files` behavior for the complete requested set.
- Regardless of branch, retain the existing subsequent per-file presence check and SHA-256 computation before any annotations or signals are used.
- Add TDD for the all-present bypass and missing-file download path without network access.
- Why: removes a redundant remote dependency while preserving byte-level source verification and fail-closed behavior.
- Alternatives rejected: wait indefinitely on remote checks, disable hashes, accept partial files, or modify the source manifest.

## Frozen acceptance criteria

- New tests are red before implementation and green after it.
- With all required files present, downloader call count is zero and the returned mode is explicitly `existing_verified_later`.
- With any required file absent, downloader is called once with the unchanged database, root, ordered relative-file list, `keep_subdirs=True`, `overwrite=False`.
- Existing per-file presence and SHA-256 verification remain unchanged and occur before cache construction.
- Full EC57 suite passes and `git diff --check` has no errors.
- M2l audit SHA, 912-record cohort, source paths, output directory, cache gates and training configuration remain unchanged.

## Results

- RED: the new focused test failed because `ensure_source_files` did not yet exist.
- GREEN: with all files present, downloader calls were zero and mode was `existing_verified_later`; after removing one test file, the original WFDB call arguments were preserved exactly. Focused data tests passed `30/30` at this stage.
- The stalled process was proven to hold two established HTTPS connections to `18.25.8.254:443` while local read bytes were unchanged; it was our owned cache process and had produced no artifacts before termination.
- Deployed local/remote builder SHA-256 matched: `365d8fcfd4f8ece5f3dd47ad3d1a2b2e73061f1c711ce82a61672308446ac428`.
- On restart, the process read about `1.97 GB` in the first 30 seconds, demonstrating that it bypassed redundant network checks and entered local hashing. The unchanged later presence and SHA-256 checks completed successfully.
- The full cache completed, and all six artifact hashes were independently recomputed and matched `sha256_manifest.txt`.

## Decision

- Decision: `接受`（仅源获取性能与完整性范围）
- Next gate: M2o patient-coverage audit.
