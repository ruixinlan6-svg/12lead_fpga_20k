# Optimization Run: `20260826-1704-m4-qn88-sdram-mismatch-diagnose`

## Identity

- Run ID: `20260826-1704-m4-qn88-sdram-mismatch-diagnose`
- Stage: `hil`
- Status: `completed`
- Started/finished: 2026-08-26 17:04 Asia/Shanghai / 2026-08-26 17:05 Asia/Shanghai
- Agent/operator: Codex `/root`
- Baseline run: `20260826-1656-m4-qn88-sdram-uart-status`
- Git commit: pending
- Data version and split hash: not applicable
- Config/contract paths: `fpga/sdram_probe/`, `contracts/hardware_contract.json`
- Environment: Gowin EDA V1.9.12.03; QN88 `GW2AR-LV18QN88C8/I7`; COM10

## Problem and evidence

- Observed problem: clean UART capture reports `SDRAM I1 P0 E1 B0`; the first-burst read-back mismatch is not yet observable.
- Evidence from the baseline: UART path is proven on COM10, initialization is reported as 1, pass is 0, error is 1, burst remains 0.
- Primary metric or failure point: capture the first mismatching 16-bit read value and expected value without changing the SDRAM pattern or controller configuration.

## Optimization

- Method: latch the first `sdrc_data_out` and `expected_data` values when a mismatch occurs and append their low 16-bit hexadecimal fields to the periodic UART status frame.
- Why this method: it distinguishes a data-path/handshake mismatch from a status-only bug while preserving the existing volatile four-burst test.
- Alternatives considered and why not selected: changing burst length or SDRAM timing before observing evidence would conflate diagnosis with repair; Flash programming remains unauthorized.
- Expected mechanism: frames will include `D=xxxx X=xxxx` after `E1`, where `D` is the first read value and `X` the expected value.

## Frozen acceptance criteria

- Success threshold: build/PnR and SRAM download pass; UART reports the first mismatch fields consistently across two captures.
- Failure/rollback threshold: no diagnostic frame or build/download failure; retain the prior `E1` result and keep the memory gate closed.
- Fixed test condition: unchanged SDRC_EMB four-burst pattern, COM10 at 115200 8-N-1, 2-second passive capture after input-buffer flush, SRAM only.

## Execution

- Entry command or script: `fpga/sdram_probe/build_qn88.tcl`; SRAM program with BlueStar runner; passive COM10 capture.
- GPU/card or hardware connection used: local Tang Nano 20K/QN88 and COM10.
- Calibration/Golden sample manifest: existing four fixed 32-word patterns; no data change.
- Deviations from the plan: the first diagnostic intentionally exposed low 16-bit words; this is an accepted observability alias because the fixed pattern's low word is zero.

## Results

| Metric | Baseline | This run | Delta | Comparable? |
|---|---:|---:|---:|---|
| First read value | unobserved | low word `0000` | now observable but aliased | yes |
| First expected value | unobserved | low word `0000` | now observable but aliased | yes |
| Status | `I1 P0 E1 B0` | stable `I1 P0 E1`, burst 0 | unchanged | yes |

- Per-class or per-layer findings: the status and mismatch telemetry are repeatable on COM10.
- Failed samples/first mismatch: `D=0000 X=0000` for low 16 bits; this cannot distinguish a zero read from the chosen `A5A5_0000` pattern.
- Logs and report paths: `fpga/sdram_probe/` UART status frame; raw bytes were captured passively after buffer flush.
- Artifact paths and SHA-256: superseded local `.fs` build; no persistent artifact added to Git.
- Unverified items: high-word mismatch and root cause remain unverified at this stage.

## Decision

- Decision: `continue`
- Reason: the run is diagnostic only and keeps the baseline hardware behavior intact.
- What changed in the project baseline: first-mismatch telemetry in UART status; no controller or pattern change.
- One primary question for the next run: does the high 16-bit read value equal the expected `A5A5` marker?
