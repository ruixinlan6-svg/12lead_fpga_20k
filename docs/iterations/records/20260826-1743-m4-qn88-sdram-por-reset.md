# Optimization Run: `20260826-1743-m4-qn88-sdram-por-reset`

## Identity

- Run ID: `20260826-1743-m4-qn88-sdram-por-reset`
- Stage: `hil`
- Status: `completed`
- Started/finished: 2026-08-26 17:43 Asia/Shanghai / 2026-08-26 17:54 Asia/Shanghai
- Agent/operator: Codex `/root`
- Baseline run: `20260826-1711-m4-qn88-sdram-vendor-handshake`
- Git commit: working tree before magic-port fix; superseded by the next recorded run
- Data version and split hash: not applicable
- Config/contract paths: `fpga/sdram_probe/`, `contracts/hardware_contract.json`
- Environment: Gowin EDA V1.9.12.03; QN88 `GW2AR-LV18QN88C8/I7`; COM10

## Problem and evidence

- Observed problem: SDRAM initialization reports 1, but the first read remains `D=0000` instead of `X=A5A5`.
- Reference evidence: the local Gowin GW2AR SDRC_EMB testbench asserts `I_rst_n=0` for 5 clock periods and does not start user traffic until a long post-reset wait; the existing Tang Nano LED baseline also uses a power-on reset counter.
- Primary metric or failure point: determine whether missing deterministic reset release is the source of the first-read zero.

## Optimization

- Method: add a synthesizable 16-bit power-on reset counter to hold the SDRC_EMB and probe reset active for 65,536 system-clock cycles (~2.43 ms at 27 MHz); retain the active-high S1 button reset and all SDRAM parameters unchanged.
- Why this method: it tests exactly one reset-path hypothesis and gives the controller more than the vendor's minimum reset interval without changing the data-path experiment.
- Alternatives considered and why not selected: changing timing, address, burst length, or pattern would confound reset diagnosis; Flash remains unauthorized.
- Expected mechanism: after deterministic reset release, the controller should initialize and the first read should match `A5A5`.

## Frozen acceptance criteria

- Success threshold: Gowin build/PnR and SRAM transfer pass; clean COM10 capture reports stable `I1 P1 E0 D=A5A5 X=A5A5`.
- Failure/rollback threshold: status remains `E1`, first read remains zero, or build/download fails; keep `read_write_test_passed=false` and form a new hypothesis.
- Fixed test condition: vendor-aligned 26-beat / bank 2 / row 2 / column 5 probe, COM10 passive capture at 115200 8-N-1 after input-buffer flush, SRAM only.

## Execution

- Entry command or script: `fpga/sdram_probe/build_qn88.tcl`; SRAM program; passive COM10 capture.
- Hardware connection: local Tang Nano 20K/QN88 and COM10.
- Calibration/Golden sample manifest: fixed `A5A5_xxxx` four-burst pattern.
- Deviations from the plan: none; SRAM only, no Flash operation. The read-only COM10 capture was repeated after flushing the input buffer.

## Results

| Metric | Baseline | This run | Delta | Comparable? |
|---|---:|---:|---:|---|
| First read high word | `0000` | `0000` | `0x0000` | yes |
| First expected high word | `A5A5` | `A5A5` | unchanged | yes |
| Status | `I1 P0 E1 B0` | `I1 P0 E1 D=0000 X=A5A5` | unchanged failure | yes |

- Logs and report paths: five clean COM10 reads captured at 2026-08-26 17:53–17:54; each was `SDRAM I1 P0 E1 D=0000 X=A5A5`.
- Artifact path and SHA-256: POR-only SRAM artifact was programmed before the magic-port run; recorded SHA-256 `5EA2EC650FAE1618389A222CC249BB48C809AABA6823E88B5D3569E6C21AAD54`.
- Unverified items: physical SDRAM pass and controller data-path connection remained unverified in this run.

## Decision

- Decision: `reject`
- Reason: the deterministic 16-bit POR hold (~2.43 ms at 27 MHz) changed neither the initialization flag nor the first-read high word. Reset release is not the primary cause of `D=0000`; the next run isolates the QN88 SDRAM package connection.
- One primary question for the next run: are the Gowin SDRAM magic ports visible at the design top level and connected to the embedded SIP?
