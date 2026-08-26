# Optimization Run: `20260826-1818-m4-qn88-sdram-mismatch-index`

## Identity

- Run ID: `20260826-1818-m4-qn88-sdram-mismatch-index`
- Stage: `hil`
- Status: `completed`
- Started/finished: 2026-08-26 18:07 Asia/Shanghai / 2026-08-26 18:09 Asia/Shanghai
- Agent/operator: Codex `/root`
- Baseline run: `20260826-1812-m4-qn88-sdram-first-word-align`
- Git commit: pending
- Config/contract paths: `fpga/sdram_probe/`, `contracts/hardware_contract.json`
- Environment: Gowin EDA V1.9.12.03; QN88 `GW2AR-LV18QN88C8/I7`; COM10

## Problem and evidence

- Observed problem: after shifting the expected base by one, the first stable mismatch is `D=0019 X=001A`; the mismatch location is not yet visible.
- Primary metric or failure point: expose the current `read_count` alongside the mismatch while leaving traffic unchanged. (The implementation did not latch a separate mismatch index.)

## Optimization

- Method: expand the existing UART diagnostic frame to 32 bytes and add `C=xx` for the first mismatch's read counter; preserve all SDRAM and expected-data logic.
- Why this method: a counter index separates a fixed initial offset from a burst-end/length boundary without modifying the data path.
- Alternatives considered and why not selected: changing write/read counts before observing the index would conflate hypotheses; Flash remains unauthorized.

## Frozen acceptance criteria

- Success threshold for this diagnostic: clean COM10 frames consistently report the same `C=xx`, `D=xxxx`, and `X=xxxx`; no functional pass claim is made.
- Failure/rollback threshold: build/program failure or unavailable UART; retain the previous source and form the next single-variable hypothesis.
- Fixed test condition: four 26-beat bursts, bank 2/row 2/column 5, 27 MHz clock, COM10 passive capture at 115200 8-N-1 after input-buffer flush, SRAM only.

## Execution

- Entry command or script: `fpga/sdram_probe/build_qn88.tcl`; SRAM program; passive COM10 capture.
- Hardware connection: local Tang Nano 20K/QN88 and COM10.
- Calibration/Golden sample manifest: fixed `A5A5_xxxx` write/read pattern; no model or Flash changes.

## Results

| Metric | Baseline | This run | Delta | Comparable? |
|---|---:|---:|---:|---|
| Read counter at terminal failure | unknown | `1A` | observed | yes |
| First read low word | `0019` | `0019` | unchanged | yes |
| First expected low word | `001A` | `001A` | unchanged | yes |
| Status | `I1 P0 E1` | `SD I1 P0 E1 C=1A D=0019 X=001A` | unchanged | yes |

- Logs and report paths: five flushed COM10 reads; stable diagnostic frame `SD I1 P0 E1 C=1A D=0019 X=001A`.
- Artifact path and SHA-256: SRAM program passed; superseded by later runs.
- Unverified items: exact first-mismatch index, length cause, full SDRAM pass, retention, Flash boot, and model-sized traffic.

## Decision

- Decision: `continue`
- Reason: the added field confirmed a terminal count of `0x1A` but was not a latched first-mismatch index; the data/expected pair still points to a stale tail boundary.
- One primary question for the next run: does stopping the compare at the declared valid-word count remove the tail mismatch?
