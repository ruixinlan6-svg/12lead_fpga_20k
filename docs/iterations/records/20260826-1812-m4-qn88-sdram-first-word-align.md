# Optimization Run: `20260826-1812-m4-qn88-sdram-first-word-align`

## Identity

- Run ID: `20260826-1812-m4-qn88-sdram-first-word-align`
- Stage: `hil`
- Status: `completed`
- Started/finished: 2026-08-26 18:05 Asia/Shanghai / 2026-08-26 18:07 Asia/Shanghai
- Agent/operator: Codex `/root`
- Baseline run: `20260826-1804-m4-qn88-sdram-lowword`
- Git commit: pending
- Config/contract paths: `fpga/sdram_probe/`, `contracts/hardware_contract.json`
- Environment: Gowin EDA V1.9.12.03; QN88 `GW2AR-LV18QN88C8/I7`; COM10

## Problem and evidence

- Observed problem: with the QN88 magic ports restored, the low-word diagnostic reports `D=0001 X=0000` and status `I1 P0 E1`.
- Evidence: the high word is correct (`A5A5`), so this is no longer a reset or package-data-path failure. The one-count low-word offset is consistent with the user-stream launch/expected-counter alignment.
- Primary metric or failure point: determine whether aligning the expected stream to the observed first returned word yields `P1 E0` across all four bursts.

## Optimization

- Method: change only the expected stream base from `A5A5_0000` to `A5A5_0001` (including each burst's expected base); preserve SDRAM ports, POR, write/read FSM, length, address, pattern high word, and SRAM-only programming.
- Why this method: it tests the smallest one-beat alignment hypothesis identified by direct low-word telemetry.
- Alternatives considered and why not selected: changing reset, SDRAM timing, or burst length would discard the already isolated evidence; Flash remains unauthorized.

## Frozen acceptance criteria

- Success threshold: build/PnR and SRAM transfer pass; five clean COM10 reads report stable `I1 P1 E0`.
- Failure/rollback threshold: any `E1`, `P0`, build/program failure, or inconsistent frame; keep the magic-port fix and form a new hypothesis.
- Fixed test condition: four 26-beat bursts, bank 2/row 2/column 5, 27 MHz clock, COM10 passive capture at 115200 8-N-1 after input-buffer flush, SRAM only.

## Execution

- Entry command or script: `fpga/sdram_probe/build_qn88.tcl`; SRAM program; passive COM10 capture.
- Hardware connection: local Tang Nano 20K/QN88 and COM10.
- Calibration/Golden sample manifest: fixed `A5A5_xxxx` write/read pattern; no model or Flash changes.

## Results

| Metric | Baseline | This run | Delta | Comparable? |
|---|---:|---:|---:|---|
| First read high word | `A5A5` | `A5A5` | unchanged | yes |
| First read low word | `0001` | `0019` | mismatch moved to tail | yes |
| First expected low word | `0000` | `001A` | mismatch moved to tail | yes |
| Status | `I1 P0 E1` | `I1 P0 E1 D=0019 X=001A` | still failing | yes |

- Logs and report paths: five flushed COM10 reads; stable frames were `SDRAM I1 P0 E1 D=0019 X=001A`.
- Artifact path and SHA-256: SRAM program passed; superseded by later diagnostic runs.
- Unverified items: read-valid boundary, full SDRAM pass, retention, Flash boot, and model-sized traffic.

## Decision

- Decision: `continue`
- Reason: the one-beat expected shift removes the initial mismatch but exposes a later tail/burst boundary; no reset or SDRAM port changes are implicated.
- One primary question for the next run: is the `0019/001A` mismatch the extra tail pulse after `data_len=25`?
