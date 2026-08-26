# Optimization Run: `20260826-1824-m4-qn88-sdram-read-boundary`

## Identity

- Run ID: `20260826-1824-m4-qn88-sdram-read-boundary`
- Stage: `hil`
- Status: `completed`
- Started/finished: 2026-08-26 18:09 Asia/Shanghai / 2026-08-26 18:12 Asia/Shanghai
- Agent/operator: Codex `/root`
- Baseline run: `20260826-1818-m4-qn88-sdram-mismatch-index`
- Git commit: pending
- Config/contract paths: `fpga/sdram_probe/`, `contracts/hardware_contract.json`
- Environment: Gowin EDA V1.9.12.03; QN88 `GW2AR-LV18QN88C8/I7`; COM10

## Problem and evidence

- Observed problem: the first mismatch is consistently `C=1A D=0019 X=001A` after 26 expected data beats.
- Evidence: `read_count` is incremented on each `sdrc_rd_valid`, and the old `>= BURST_WORDS` condition accepts a 27th pulse although `data_len=25` represents 26 words. The extra pulse returns a stale tail value.
- Primary metric or failure point: stop comparing after the threshold used in this run and verify whether `P1 E0` appears.

## Optimization

- Method: change only the read completion threshold from `read_count >= BURST_WORDS` to `read_count >= BURST_WORDS - 1`; preserve magic ports, POR, expected base `A5A5_0001`, write stream, and all SDRAM parameters.
- Why this method: it matches the declared 26-word transfer and removes the observed extra valid comparison without changing the physical interface.
- Alternatives considered and why not selected: changing SDRAM timing or write count would conflate a read-side boundary issue; Flash remains unauthorized.

## Frozen acceptance criteria

- Success threshold: build/PnR and SRAM transfer pass; five clean COM10 reads report `I1 P1 E0`.
- Failure/rollback threshold: any `E1`, `P0`, inconsistent frame, or build/program failure; retain the evidence and form a new hypothesis.
- Fixed test condition: four 26-beat bursts, bank 2/row 2/column 5, 27 MHz clock, COM10 passive capture at 115200 8-N-1 after input-buffer flush, SRAM only.

## Execution

- Entry command or script: `fpga/sdram_probe/build_qn88.tcl`; SRAM program; passive COM10 capture.
- Hardware connection: local Tang Nano 20K/QN88 and COM10.
- Calibration/Golden sample manifest: fixed `A5A5_xxxx` write/read pattern; no model or Flash changes.

## Results

| Metric | Baseline | This run | Delta | Comparable? |
|---|---:|---:|---:|---|
| Terminal read counter | `1A` | `1A` | unchanged | yes |
| First read low word | `0019` | `0019` | unchanged | yes |
| First expected low word | `001A` | `001A` | unchanged | yes |
| Status | `I1 P0 E1` | `SD I1 P0 E1 C=1A D=0019 X=001A` | no improvement | yes |

- Logs and report paths: five flushed COM10 reads; stable frame remained `SD I1 P0 E1 C=1A D=0019 X=001A`.
- Artifact path and SHA-256: SRAM program passed; superseded by the valid-length run.
- Unverified items: correct valid-word count, full SDRAM pass, retention, Flash boot, and model-sized traffic.

## Decision

- Decision: `reject`
- Reason: the `-1` boundary did not change the observed terminal mismatch; the next run tests the declared `data_len=25` valid-word count directly.
- One primary question for the next run: does comparing only 25 valid words avoid the stale tail pulse?
