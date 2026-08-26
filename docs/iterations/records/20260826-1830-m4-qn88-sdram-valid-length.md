# Optimization Run: `20260826-1830-m4-qn88-sdram-valid-length`

## Identity

- Run ID: `20260826-1830-m4-qn88-sdram-valid-length`
- Stage: `hil`
- Status: `completed`
- Started/finished: 2026-08-26 18:12 Asia/Shanghai / 2026-08-26 18:13 Asia/Shanghai
- Agent/operator: Codex `/root`
- Baseline run: `20260826-1824-m4-qn88-sdram-read-boundary`
- Git commit: pending
- Config/contract paths: `fpga/sdram_probe/`, `contracts/hardware_contract.json`
- Environment: Gowin EDA V1.9.12.03; QN88 `GW2AR-LV18QN88C8/I7`; COM10

## Problem and evidence

- Observed problem: after aligning the expected base to `A5A5_0001`, the last compared value is `D=0019 X=001A`; the prior threshold still compares one stale tail pulse.
- Evidence: `data_len=25` and the direct QN88 capture show valid data through low word `0019`; the next returned value repeats `0019` while the expected stream advances to `001A`.
- Primary metric or failure point: compare exactly 25 valid words and ignore the controller's extra tail `rd_valid`.

## Optimization

- Method: change only the read completion threshold from `read_count >= BURST_WORDS - 1` to `read_count >= BURST_WORDS - 2`, i.e. finish after 25 valid words for `data_len=25`; preserve magic ports, POR, expected base `A5A5_0001`, write stream, and all SDRAM parameters.
- Why this method: it matches the observed QN88 valid-word count and avoids comparing stale data without changing the physical interface.
- Alternatives considered and why not selected: changing reset, timing, or write data before fixing the measured read-valid boundary would conflate hypotheses; Flash remains unauthorized.

## Frozen acceptance criteria

- Success threshold: build/PnR and SRAM transfer pass; five clean COM10 reads report `I1 P1 E0`.
- Failure/rollback threshold: any `E1`, `P0`, inconsistent frame, or build/program failure; retain the diagnostic evidence and form a new hypothesis.
- Fixed test condition: four 25-valid-word bursts using `data_len=25`, bank 2/row 2/column 5, 27 MHz clock, COM10 passive capture at 115200 8-N-1 after input-buffer flush, SRAM only.

## Execution

- Entry command or script: `fpga/sdram_probe/build_qn88.tcl`; SRAM program; passive COM10 capture.
- Hardware connection: local Tang Nano 20K/QN88 and COM10.
- Calibration/Golden sample manifest: fixed `A5A5_xxxx` write/read pattern; no model or Flash changes.

## Results

| Metric | Baseline | This run | Delta | Comparable? |
|---|---:|---:|---:|---|
| First read low word | `0019` | `001E` | moved to next-burst first word | yes |
| First expected low word | `001A` | `0101` | moved to next-burst base | yes |
| Status | `I1 P0 E1` | `SD I1 P0 E1 C=19 D=001E X=0101` | still failing | yes |

- Logs and report paths: five flushed COM10 reads; stable frames were `SD I1 P0 E1 C=19 D=001E X=0101`.
- Artifact path and SHA-256: SRAM program passed; superseded by the burst-reseed run.
- Unverified items: burst producer reset, full SDRAM pass, retention, Flash boot, and model-sized traffic.

## Decision

- Decision: `continue`
- Reason: limiting the compare to 25 words exposed an independent RTL bug: the next burst inherited the previous burst's write counter. No reset or package-port changes are implicated.
- One primary question for the next run: does reloading the producer at each burst base close all four comparisons?
