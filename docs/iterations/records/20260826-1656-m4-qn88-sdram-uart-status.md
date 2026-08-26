# Optimization Run: `20260826-1656-m4-qn88-sdram-uart-status`

## Identity

- Run ID: `20260826-1656-m4-qn88-sdram-uart-status`
- Stage: `hil`
- Status: `completed`
- Started/finished: 2026-08-26 16:56 Asia/Shanghai / 2026-08-26 17:02 Asia/Shanghai
- Agent/operator: Codex `/root`
- Baseline run: `20260826-1618-m4-qn88-sdram-probe`
- Git commit: pending
- Data version and split hash: not applicable
- Config/contract paths: `contracts/hardware_contract.json`, `fpga/sdram_probe/`
- Environment: Gowin EDA V1.9.12.03; QN88 `GW2AR-LV18QN88C8/I7`; local Tang Nano 20K; UART COM10

## Problem and evidence

- Observed problem: the SDRAM probe was downloaded to SRAM successfully, but LEDs could not be independently observed by software.
- Evidence from the baseline: the QN88 `SDRC_EMB` PnR and SRAM transfer passed, while `read_write_test_passed` remained false pending status observation.
- Primary metric or failure point: obtain a UART frame reporting SDRAM initialization, pass, error, and burst state from the running probe.

## Optimization

- Method: add a periodic read-only ASCII status frame to the existing QN88 SDRAM probe on schematic PIN69/PIN70; keep SDRAM algorithm and SRAM-only programming unchanged.
- Why this method: COM10 was just proven to carry the FPGA UART path; serial status is less ambiguous than LED observation and does not alter the memory test.
- Alternatives considered and why not selected: visual LED-only observation is not machine-auditable; Flash programming is unauthorized; changing the SDRAM pattern would confound comparison.
- Expected mechanism: `SDRAM I1 P1 E0 B0\r\n`-style frames will be emitted every 250 ms and captured passively on COM10.

## Frozen acceptance criteria

- Success threshold: build/PnR and SRAM download pass; at least one COM10 frame reports `I1 P1 E0` after the controller finishes.
- Failure/rollback threshold: no status frame, status reports `E1`, or any SDRAM RTL behavior/build/download failure; keep `read_write_test_passed=false`.
- Fixed test condition: QN88 SDRC_EMB four-burst pattern test, 115200 8-N-1, COM10 passive capture for 3 s, SRAM only.

## Execution

- Entry command or script: `fpga/sdram_probe/build_qn88.tcl`; BlueStar runner SRAM program; serial skill passive capture.
- GPU/card or hardware connection used: local Tang Nano 20K/QN88 and COM10.
- Calibration/Golden sample manifest: SDRAM probe's four fixed 32-word patterns.
- Deviations from the plan: host input buffer was explicitly flushed before the clean capture to exclude bytes from the preceding UART heartbeat image.

## Results

| Metric | Baseline | This run | Delta | Comparable? |
|---|---:|---:|---:|---|
| PnR | pass | pass | unchanged | yes |
| SRAM transfer | pass | pass (`0x00006020`, 100%) | unchanged | yes |
| UART `I1 P1 E0` frame | unverified | not observed; stable `SDRAM I1 P0 E1 B0` | fail | yes after same capture condition |
| `read_write_test_passed` | false/unverified | false; gate remains closed | no change | gate |

- Per-class or per-layer findings: initialization reaches 1, but the probe enters error before completing burst 0.
- Failed samples/first mismatch: first read mismatch was not yet included in this frame format; later diagnostic runs captured it.
- Logs and report paths: `fpga/sdram_probe/build/qn88_sdram_probe/impl/pnr/qn88_sdram_probe.rpt.txt`; COM10 passive capture after buffer flush.
- Artifact paths and SHA-256: generated `.fs` is ignored and superseded by later diagnostic builds; SRAM programming succeeded.
- Unverified items: SDRAM root cause and non-destructive read/write pass remain unverified/failed; no Flash was touched.

## Decision

- Decision: `continue`
- Reason: the UART path is valid, but the physical SDRAM test reports a real error; keep `read_write_test_passed=false` and diagnose the first mismatch.
- What changed in the project baseline: UART status output only; no model or memory-pattern change.
- One primary question for the next run: what exact value does the first QN88 SDRAM read return?
