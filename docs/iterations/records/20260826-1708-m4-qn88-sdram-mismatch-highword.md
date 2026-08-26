# Optimization Run: `20260826-1708-m4-qn88-sdram-mismatch-highword`

## Identity

- Run ID: `20260826-1708-m4-qn88-sdram-mismatch-highword`
- Stage: `hil`
- Status: `completed`
- Started/finished: 2026-08-26 17:08 Asia/Shanghai / 2026-08-26 17:08 Asia/Shanghai
- Agent/operator: Codex `/root`
- Baseline run: `20260826-1704-m4-qn88-sdram-mismatch-diagnose`
- Git commit: pending
- Data version and split hash: not applicable
- Config/contract paths: `fpga/sdram_probe/`, `contracts/hardware_contract.json`
- Environment: Gowin EDA V1.9.12.03; QN88 `GW2AR-LV18QN88C8/I7`; COM10

## Problem and evidence

- Observed problem: the first-mismatch frame was captured, but its low 16-bit fields were `D=0000 X=0000`; the expected pattern has low word zero, so this did not distinguish a zero read from the intended `A5A5_0000` value.
- Evidence from the baseline: status is stable `I1 P0 E1 B0`; telemetry framing works.
- Primary metric or failure point: expose the high 16-bit words so the first read value can be compared to the `A5A5` expected marker.

## Optimization

- Method: change only the diagnostic field selection from bits `[15:0]` to `[31:16]` for both first-read and first-expected values.
- Why this method: it removes the known low-word alias without changing the SDRAM algorithm or test pattern.
- Alternatives considered and why not selected: changing the pattern would invalidate comparison with the preceding runs; increasing frame size is unnecessary for this distinction.
- Expected mechanism: a zero/empty read should report `D=0000 X=A5A5`; a correctly aligned first read should report `D=A5A5 X=A5A5`.

## Frozen acceptance criteria

- Success threshold: build/PnR and SRAM download pass; two captures report a stable, interpretable high-word pair.
- Failure/rollback threshold: no frame or build/download failure; keep the SDRAM gate closed.
- Fixed test condition: unchanged SDRC_EMB four-burst pattern and COM10 passive capture at 115200 8-N-1 after input-buffer flush.

## Execution

- Entry command or script: `fpga/sdram_probe/build_qn88.tcl`; SRAM program; passive COM10 capture.
- GPU/card or hardware connection used: local Tang Nano 20K/QN88 and COM10.
- Calibration/Golden sample manifest: existing four fixed 32-word patterns.
- Deviations from the plan: none; only the diagnostic field selection changed.

## Results

| Metric | Baseline | This run | Delta | Comparable? |
|---|---:|---:|---:|---|
| First read high word | not distinguishable | `0000` | zero vs expected | yes |
| First expected high word | not distinguishable | `A5A5` | marker exposed | yes |
| Status | `I1 P0 E1 B0` | stable `I1 P0 E1 B0` | unchanged | yes |

- Per-class or per-layer findings: the first read is stably zero in the high word while the expected marker is `A5A5`.
- Failed samples/first mismatch: `D=0000 X=A5A5`, repeated across the clean capture.
- Logs and report paths: COM10 passive capture; `fpga/sdram_probe/build/qn88_sdram_probe/impl/pnr/qn88_sdram_probe.rpt.txt`.
- Artifact paths and SHA-256: local diagnostic `.fs` was superseded by the vendor-handshake build; no generated file is committed.
- Unverified items: the exact controller/board cause is not yet isolated; physical SDRAM read/write gate remains failed.

## Decision

- Decision: `continue`
- Reason: this run only removes an observability alias in the diagnostic telemetry.
- What changed in the project baseline: high-word mismatch reporting; no controller or pattern change.
- One primary question for the next run: does matching the local vendor testbench's burst length and non-zero bank/row address remove the first-read zero?
