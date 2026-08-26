# Optimization Run: `20260826-1840-m4-qn88-sdram-burst-reseed`

## Identity

- Run ID: `20260826-1840-m4-qn88-sdram-burst-reseed`
- Stage: `hil`
- Status: `completed`
- Started/finished: 2026-08-26 18:13 Asia/Shanghai / 2026-08-26 18:14 Asia/Shanghai
- Agent/operator: Codex `/root`
- Baseline run: `20260826-1830-m4-qn88-sdram-valid-length`
- Git commit: pending
- Config/contract paths: `fpga/sdram_probe/`, `contracts/hardware_contract.json`
- Environment: Gowin EDA V1.9.12.03; QN88 `GW2AR-LV18QN88C8/I7`; COM10

## Problem and evidence

- Observed problem: after limiting comparison to 25 valid words, the first stable mismatch is on the next burst: `D=001E X=0101`.
- Evidence: the expected stream changes to the next burst base (`0x0101`), while the producer continues the previous burst's low-word counter (`0x001E`).
- Primary metric or failure point: reload the write pattern at each burst transition and verify all four burst bases.

## Optimization

- Method: when advancing `burst`, reload `write_data` and `user_data` to `A5A5_0000 + (burst+1)*0x0100`; preserve magic ports, POR, expected base `A5A5_0001`, 25-word read comparison, and all SDRAM parameters.
- Why this method: it fixes the directly observed burst-to-burst producer state leak without changing reset, timing, or controller configuration.
- Alternatives considered and why not selected: changing SDRAM timing or resetting the whole controller would hide a deterministic RTL state bug; Flash remains unauthorized.

## Frozen acceptance criteria

- Success threshold: build/PnR and SRAM transfer pass; eight clean COM10 reads report `I1 P1 E0`.
- Failure/rollback threshold: any `E1`, `P0`, inconsistent frame, or build/program failure; retain the trace and form a new hypothesis.
- Fixed test condition: four 25-valid-word bursts using `data_len=25`, bank 2/row 2/column 5, 27 MHz clock, COM10 passive capture at 115200 8-N-1 after input-buffer flush, SRAM only.

## Execution

- Entry command or script: `fpga/sdram_probe/build_qn88.tcl`; SRAM program; passive COM10 capture.
- Hardware connection: local Tang Nano 20K/QN88 and COM10.
- Calibration/Golden sample manifest: burst bases `A5A5_0000`, `A5A5_0100`, `A5A5_0200`, `A5A5_0300`; no model or Flash changes.

## Results

| Metric | Baseline | This run | Delta | Comparable? |
|---|---:|---:|---:|---|
| First burst low base | `0001` actual | `0001` actual | unchanged | yes |
| Second burst low base | `001E` actual (wrong) | `0101` actual | corrected | yes |
| Second burst expected | `0101` | `0101` | matched | yes |
| Status | `I1 P0 E1` | `SD I1 P1 E0 C=19 D=0000 X=0000` | pass | yes |

- Logs and report paths: eight flushed COM10 reads after SRAM programming; all stable frames were `SD I1 P1 E0 C=19 D=0000 X=0000`.
- Artifact path and SHA-256: `fpga/sdram_probe/build/qn88_sdram_probe/impl/pnr/qn88_sdram_probe.fs`; SHA-256 `1B1ACF201B380AD6B3F1D4AB807C73CFF6E2022DB521CFAEAF873A000B9EDE50`; SRAM programming reached 100%, programmer status `0x00006020`.
- Independent static evidence: synthesis retains the SDRAM data ports and PnR maps them to the QN88 embedded-SDRAM sites.
- Unverified items: long-duration retention, Flash boot, and full ECG model traffic; this remains a volatile controller smoke test.

## Decision

- Decision: `accept`
- Reason: reloading each burst base closes the remaining RTL state leak; the QN88 returns `P1 E0` for all four bursts in eight consecutive clean COM10 reads. The original first-read-zero symptom was the internal SDRAM-port connection; reset was not the cause.
- One primary question for the next run: keep the accepted QN88 port/reset/stream contract while integrating the smallest model-backed SDRAM buffer.
