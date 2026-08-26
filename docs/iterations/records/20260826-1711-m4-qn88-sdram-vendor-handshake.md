# Optimization Run: `20260826-1711-m4-qn88-sdram-vendor-handshake`

## Identity

- Run ID: `20260826-1711-m4-qn88-sdram-vendor-handshake`
- Stage: `hil`
- Status: `completed`
- Started/finished: 2026-08-26 17:06 Asia/Shanghai / 2026-08-26 17:10 Asia/Shanghai
- Agent/operator: Codex `/root`
- Baseline run: `20260826-1708-m4-qn88-sdram-mismatch-highword`
- Git commit: pending
- Data version and split hash: not applicable
- Config/contract paths: `fpga/sdram_probe/`, `contracts/hardware_contract.json`
- Environment: Gowin EDA V1.9.12.03; QN88 `GW2AR-LV18QN88C8/I7`; COM10

## Problem and evidence

- Observed problem: clean QN88 status is `SDRAM I1 P0 E1 D=0000 X=A5A5`; the first read returns zero instead of the expected high word.
- Evidence from local Gowin materials: the official GW2AR SDRC_EMB testbench uses `sdrc_data_len=25`, bank address 2, row address 2, and keeps write/read streams for `data_len+2` cycles.
- Primary metric or failure point: determine whether matching the vendor handshake/transfer length removes the zero read.

## Optimization

- Method: align the probe's user burst length and bank/row address with the local vendor GW2AR embedded-SDRAM example (`BURST_WORDS=26`, `sdrc_data_len=25`, bank=2, row=2); leave UART telemetry and SRAM-only operation intact.
- Why this method: it is the smallest evidence-backed parameter correction before changing controller timing or board assumptions.
- Alternatives considered and why not selected: changing SDRAM clock/timing without matching the documented interface would confound the diagnosis; Flash is not touched.
- Expected mechanism: the vendor-compatible transfer length should produce a nonzero first read and allow `P1 E0` if the QN88 embedded SDRAM path is healthy.

## Frozen acceptance criteria

- Success threshold: build/PnR and SRAM transfer pass; status reports `I1 P1 E0` with first-read high word `A5A5`.
- Failure/rollback threshold: status remains `E1`, read remains zero, or build/download fails; keep `read_write_test_passed=false`.
- Fixed test condition: four bursts using the vendor-compatible transfer length, COM10 passive capture at 115200 8-N-1 after input-buffer flush, SRAM only.

## Execution

- Entry command or script: `fpga/sdram_probe/build_qn88.tcl`; SRAM program; passive COM10 capture.
- GPU/card or hardware connection used: local Tang Nano 20K/QN88 and COM10.
- Calibration/Golden sample manifest: unchanged fixed pattern, only transfer-length/address parameters changed.
- Deviations from the plan: none; the run ID names the planned handoff minute, while the measured build/program/capture window is recorded above.

## Results

| Metric | Baseline | This run | Delta | Comparable? |
|---|---:|---:|---:|---|
| First read high word | `0000` | `0000` | unchanged | yes |
| First expected high word | `A5A5` | `A5A5` | unchanged | yes |
| Status | `I1 P0 E1 B0` | stable `I1 P0 E1 B0` | unchanged | yes |

- Per-class or per-layer findings: local vendor-compatible `data_len=25`, bank 2, row 2, column 5 did not remove the first-read zero.
- Failed samples/first mismatch: `D=0000 X=A5A5`, repeated throughout the 3.1 s clean COM10 capture (360 bytes).
- Logs and report paths: `fpga/sdram_probe/build/qn88_sdram_probe/impl/pnr/qn88_sdram_probe.rpt.txt`; SRAM programmer returned status `0x00006020`.
- Artifact paths and SHA-256: `fpga/sdram_probe/build/qn88_sdram_probe/impl/pnr/qn88_sdram_probe.fs`; `8F26D6883C5C304271575E1F8AD962A2F57FDF1566FD9999F231811740863EAD`.
- Unverified items: SDRAM controller/board root cause, SDRAM physical read/write pass, and LED state remain unresolved; Flash was not touched.

## Decision

- Decision: `reject`
- Reason: the evidence-backed vendor parameter change built and downloaded successfully but produced the same deterministic mismatch; reject this variant and keep the SDRAM gate closed.
- What changed in the project baseline: SDRC user transfer length and bank/row address only.
- One primary question for the next run: inspect controller reset/clock/pin-level behavior or use a lower-level SDRAM readback probe before changing the data pattern again.
