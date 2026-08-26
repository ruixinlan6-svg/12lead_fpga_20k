# Optimization Run: `20260826-1757-m4-qn88-sdram-magic-ports`

## Identity

- Run ID: `20260826-1757-m4-qn88-sdram-magic-ports`
- Stage: `hil`
- Status: `completed`
- Started/finished: 2026-08-26 17:57 Asia/Shanghai / 2026-08-26 18:00 Asia/Shanghai
- Agent/operator: Codex `/root`
- Baseline run: `20260826-1743-m4-qn88-sdram-por-reset`
- Git commit: pending (this working tree contains the tested source and documentation)
- Config/contract paths: `fpga/sdram_probe/`, `contracts/hardware_contract.json`
- Environment: Gowin EDA V1.9.12.03; QN88 `GW2AR-LV18QN88C8/I7`; COM10

## Problem and evidence

- Observed problem: controller initialization reports 1 but first-read telemetry remains `D=0000` instead of `X=A5A5`.
- Local synthesis evidence: when SDRAM signals are internal wires, the synthesized controller wrapper has no data ports; when the returned data is made observable, the data still collapses to a constant.
- External reference evidence: Tang Nano 20K designs declare `O_sdram_clk`, `O_sdram_cke`, `O_sdram_cs_n`, `O_sdram_cas_n`, `O_sdram_ras_n`, `O_sdram_wen_n`, `IO_sdram_dq`, `O_sdram_addr`, `O_sdram_ba`, and `O_sdram_dqm` as top-level ports so Gowin can connect the embedded SDRAM SIP.
- Primary metric or failure point: determine whether top-level magic ports restore the physical QN88 SDRAM data path and remove the zero first read.

## Optimization

- Method: promote the ten Gowin SDRAM magic ports to `qn88_sdram_probe` top-level ports and connect the existing SDRC_EMB instance directly to them; keep the POR, vendor-aligned burst/address, pattern, UART, and SRAM-only programming conditions unchanged.
- Why this method: it changes only the inferred package-level connection. The PnR pin report should show the magic ports mapped to the QN88 embedded-SDRAM sites, and the controller data ports should remain visible in the synthesized wrapper.
- Alternatives considered and why not selected: further reset duration, timing, address, or burst changes would confound a now-disproved reset hypothesis; Flash remains unauthorized.
- Expected mechanism: Gowin recognizes the exact top-level names, routes the SDRC command/data bus to the QN88 SIP, and returns the written `A5A5_xxxx` pattern.

## Frozen acceptance criteria

- Success threshold: build/PnR and SRAM transfer pass; clean COM10 capture reports stable `I1 P1 E0 D=A5A5 X=A5A5`.
- Failure/rollback threshold: data remains `D=0000`, status remains `E1`, or build/program fails; keep `read_write_test_passed=false` and form a new hypothesis.
- Fixed test condition: four 26-word bursts, bank 2/row 2/column 5 start, 27 MHz clock, COM10 passive capture at 115200 8-N-1 after input-buffer flush, SRAM only.

## Execution

- Entry command or script: `fpga/sdram_probe/build_qn88.tcl`; SRAM program with the BlueStar runner; passive COM10 capture.
- Hardware connection: local Tang Nano 20K/QN88 and COM10.
- Calibration/Golden sample manifest: fixed `A5A5_xxxx` write/read pattern; no model or Flash changes.

## Results

| Metric | Baseline | This run | Delta | Comparable? |
|---|---:|---:|---:|---|
| Synthesized controller data ports | absent | present (`sdrc_data_out`, `IO_sdram_dq`, address/command ports) | restored | yes |
| First read high word | `0000` | `A5A5` | `+A5A5` | yes |
| Status | `I1 P0 E1 B0` | `I1 P0 E1 D=A5A5 X=A5A5` | high-word path restored; full-word failure remains | yes |

- Logs and report paths: clean passive COM10 reads (five repetitions after input-buffer flush), all exactly `SDRAM I1 P0 E1 D=A5A5 X=A5A5`; the first long capture also showed the expected transition from stale buffered `D=0000` frames to `D=A5A5`.
- Artifact path and SHA-256: `fpga/sdram_probe/build/qn88_sdram_probe/impl/pnr/qn88_sdram_probe.fs`; SHA-256 `98C4B3AA2722FE86084A9A60C46C4E2ACE9BB763DF1E3C9E4158BBD8424B25ED`; SRAM programming reached 100% on `Gowin USB Cable(FT2CH)/0/None/null@2.5MHz`, target `GW2AR-18C`.
- Independent static evidence: post-fix netlist retains `sdrc_data_out`, `IO_sdram_dq`, SDRAM address/command ports, and the PnR pin report maps all magic ports to QN88 embedded-SDRAM sites.
- Unverified items: long-duration retention, Flash boot, and full ECG model traffic remain unverified; this is a volatile SDRAM controller smoke test.

## Decision

- Decision: `continue`
- Reason: exact top-level Gowin magic ports restored the synthesized high-word data path (`D=A5A5`), but `P0 E1` shows a remaining low-word or transfer-sequencing mismatch. This run localizes the original high-word zero to the port connection; it does not yet close the full SDRAM acceptance gate.
- One primary question for the next run: what low 16-bit value is returned on the first mismatching beat, and is the expected counter one beat out of phase?
