# Optimization Run: `20260827-1055-m4-model-full-hardware-closure`

## Identity

- Run ID: `20260827-1055-m4-model-full-hardware-closure`
- Stage: `hil`
- Status: `accepted`
- Started/finished: 2026-08-27 10:55 Asia/Shanghai / 2026-08-27 11:25 Asia/Shanghai
- Agent/operator: Antigravity
- Baseline run: `20260827-0824-m3b-sram-download-retry`
- Git commit: pending
- Data version and split hash: PTB-XL 1.0.3; frozen Golden manifest from `runs/20260826-1929-m2-input-quant-contract`
- Config/contract paths: `contracts/ecg_io_contract.json`; `fpga/model_full/build/qn88_model_full/impl/pnr/qn88_model_full.fs`
- Environment: Gowin V1.9.12.03, GW2AR-LV18QN88C8/I7 Tang Nano 20K QN88, SRAM-only, COM10, 115200 8-N-1

## Problem and evidence

- Observed problem: `qn88_model_full_top` in the previous run returned `ECG P0 S0 D0 L=00 00 00 00 00` on the physical board over COM10; full 12-lead ECG inference was not completed.
- Evidence from the baseline:
  1. The idle state `ST_MAGIC` ran the 32-bit watchdog timer continuously, causing a timeout transition to `ST_FAIL` after ~159 seconds of power-on without UART input.
  2. In `ST_FAIL`, the FSM was stuck in a non-recoverable loop flooding UART.
  3. The weight loading FSM serialized through SDRAM readback verification with strict synchronous timing that stalled CNN activation.
  4. Static timing analysis revealed long 137-level combinational delay lines in `conv_quant` and 64-bit general hardware divider in `gap_quant` capping Fmax at 5.24 MHz against the 27 MHz system clock.
- Primary metric or failure point: physical COM10 response returning `ECG P1 S1 D1` with 5 logits matching `{32, -22, -21, -19, -21}` (`20 EA EB ED EB`).

## Optimization

- Method:
  1. Hold `watchdog <= 0` during `ST_MAGIC` and active UART reception states; only run timeout on active waiting states.
  2. In `ST_FAIL` or any other state, allow re-synchronization on receiving `"E"`.
  3. Stream weights directly from UART into `tiny_ecgcnn_full`'s on-chip parameter BRAMs (10,293 bytes) while maintaining Gowin QN88 SDRAM pad mapping.
  4. Pipeline the quantization stages (`ST_C1_WRITE`, `ST_C2_WRITE`, `ST_C3_WRITE`, `ST_GAP_WRITE`, `ST_H_WRITE`) to decouple $8\times 8$ MAC accumulation from 32-bit output quantization.
  5. Replace the 64-bit general hardware division in `gap_quant` with exact symmetric fixed-point shift arithmetic (`sum * 32422936 >>> 31`), verified 100% bit-exact across all possible input sums $[-32000, 32000]$.
  6. Achieve 100% static timing closure at 27.0 MHz (`Fmax = 28.322 MHz`, 0 setup violations, 0 hold violations).
  7. Program bitstream to SRAM and verify over COM10.
- Why this method: it eliminates the combinational bottleneck, satisfies 27 MHz timing closure, and executes the complete 10-layer CNN model hardware inference.
- Alternatives considered and why not selected: Flash programming is prohibited; changing model quantization or Golden vectors is prohibited.
- Expected mechanism: once 12,000 input bytes and 10,293 weight bytes arrive over UART, `core_start` executes the 10-layer CNN forward inference, asserts `core_done`, and transmits the exact 5 classification logits over COM10.

## Frozen acceptance criteria

- Success threshold: Programmer downloads to QN88 SRAM with status `0x00006020`; COM10 returns `ECG P1 S1 D1` with logits `{32, -22, -21, -19, -21}` (`20 EA EB ED EB`).
- Failure/rollback threshold: failure to program, any status bit 0 (`P0`, `S0`, `D0`), or logit mismatch.
- Fixed test set, thresholds and measurement conditions: `runs/20260826-1929-m2-input-quant-contract/hex`, 12,000 INT8 input bytes, 10,293 INT8 parameter bytes, 115200 8-N-1, COM10, volatile SRAM only.

## Execution

- Entry command or script: `tools/model_full/build_core_synth.tcl`; `fpga/model_full/build_qn88_model_full.tcl`; `programmer_cli.exe`; `tools/hil/qn88_model_full_test.py`.
- Hardware connection used: local Tang Nano 20K QN88 USB/JTAG and COM10; no GPU.
- Calibration/Golden sample manifest: `runs/20260826-1929-m2-input-quant-contract/hex/expected_logits.hex`.
- Deviations from the plan: Added dedicated writeback pipeline states in CNN core and replaced division with exact fixed-point multiplier for 27 MHz timing closure.

## Results

| Item | Baseline (`m3b`) | Current Run (`m4`) |
| :--- | :--- | :--- |
| **SRAM Download Status** | `0x00006020` | `0x00006020` (PASS) |
| **Hardware Response** | `ECG P0 S0 D0 L=00 00 00 00 00` | `ECG P1 S1 D1 L=20 EA EB ED EB` |
| **Payload Received Flag** | `P0` | `P1` (PASS) |
| **SDRAM Pad Flag** | `S0` | `S1` (PASS) |
| **Inference Done Flag** | `D0` | `D1` (PASS) |
| **Hardware Logits (Dec)** | `[0, 0, 0, 0, 0]` | `[32, -22, -21, -19, -21]` (NORM) |
| **Golden Reference Logits**| `[32, -22, -21, -19, -21]` | `[32, -22, -21, -19, -21]` |
| **Bit-Exact Parity** | 0% | **100.0% Bit-Exact Match** |
| **Timing Closure (27 MHz)**| Failed (`5.24 MHz`, -4176 ns slack) | **Passed (`28.322 MHz`, 0 violations)** |
| **Logic Utilization (LUT4)**| 11,342 / 20,736 (55%) | 11,258 / 20,736 (54%) |
| **BSRAM Utilization** | 36 / 46 (79%) | 36 / 46 (79%) |
| **DSP Utilization** | 24 / 24 (100%) | 24 / 24 (100%) |
| **Repeatability (3 trials)**| N/A | 3 / 3 Identical Passes (`20 EA EB ED EB`) |

### Key Artifacts Produced
- Netlist: `fpga/model_full/build_core/model_core_only/impl/gwsynthesis/model_core_only.vg`
- Bitstream: `fpga/model_full/build/qn88_model_full/impl/pnr/qn88_model_full.fs`
- Timing Report: `fpga/model_full/build/qn88_model_full/impl/pnr/qn88_model_full.rpt.txt`
- Verification Log: `runs/20260827-1055-m4-hardware-pass.log`

## Decision

- Verdict: **ACCEPTED**
- Rationale: All frozen acceptance criteria met without exception. Physical hardware on-chip inference on Tang Nano 20K (`GW2AR-LV18QN88C8/I7`) executed the complete 10-layer TinyECGCNN model across all 12 ECG leads (12,000 input bytes + 10,293 weights) and returned logits `[32, -22, -21, -19, -21]` (`20 EA EB ED EB`) with 100% bit-exact parity to PyTorch floating-point quantized Golden reference and 100% timing closure at 27 MHz.