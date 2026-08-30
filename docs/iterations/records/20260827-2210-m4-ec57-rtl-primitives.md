# Optimization Run: `20260827-2210-m4-ec57-rtl-primitives`

## Identity

- Run ID: `20260827-2210-m4-ec57-rtl-primitives`
- Stage: `rtl`
- Status: `completed`
- Started/finished: 2026-08-27 22:05 Asia/Shanghai / 2026-08-27 22:15 Asia/Shanghai
- Agent/operator: Antigravity (FPGA Generic RTL Infrastructure Agent)
- Baseline run: None (First clean baseline for EC57 hybrid pipeline RTL infrastructure)
- Git commit: `da66332`
- Data version and split hash: N/A (Generic RTL infrastructure primitives independent of model weights and training datasets)
- Config/contract paths: `contracts/hardware_contract.json`; `docs/superpowers/plans/2026-08-27-qn88-ec57-hybrid-implementation.md`
- Environment: Windows, Icarus Verilog V12 (g2012), Target Device GW2AR-LV18QN88C8/I7 (27 MHz)

## Problem and evidence

- Observed problem: The twelve-lead ECG EC57 hybrid architecture requires clean, hardware-inferable synchronous Block RAM primitives (SP RAM, Simple DP RAM) and an exact fixed-point requantization MAC unit. Improper memory descriptions (e.g. asynchronous read or reset loops on memory arrays) cause synthesis failure or 45k+ LUT logic explosion on Gowin BSRAM.
- Evidence from baseline: Prior project iterations noted that memory arrays must follow pure synchronous read templates with `(* ram_style = "block" *)`, and arithmetic requantization must adhere strictly to symmetric round-half-away-from-zero to avoid negative DC bias.
- Primary metric or failure point: 1-cycle read latency with read-first collision semantics, zero memory array resets in hardware, and 100% bit-exact requantization across shift range 0..31, INT32 boundaries, and signed INT8 saturation.

## Optimization

- Method:
  1. Implemented `ecg_sync_sp_ram.sv`: Parameterized single-port synchronous RAM with 1-cycle read latency, read-first collision semantics, pure synchronous clocking, and unreset memory array.
  2. Implemented `ecg_sync_dp_ram.sv`: Parameterized simple dual-port synchronous RAM with independent read/write ports, 1-cycle read latency, read-first collision handling on identical read/write addresses, and unreset memory array.
  3. Implemented `ecg_requant_mac.sv`: Parameterized 32x32 signed multiplier into 64-bit product, symmetric round-half-away-from-zero logic (shift 0..31), signed INT8 dynamic saturation `[-128, +127]`, optional ReLU activation, and 2-stage pipeline.
  4. Documented all contracts, port assumptions, latency, collision semantics, rounding mathematics, and M0 audit checklist in `fpga/ec57_hybrid/INTERFACE_ASSUMPTIONS.md`.
- Why this method: Complies directly with Gowin BSRAM inference guidelines (`SUG550` / `UG300`) to guarantee mapping to 46 on-chip BSRAM blocks on GW2AR-18C without consuming LUT arrays. 2-stage pipelining guarantees timing closure at 27 MHz.
- Alternatives considered and why not selected: Asynchronous RAM reads (unsupported by BRAM primitives, rejected by FPGA architecture); array reset loops (triggers Gowin loop count limit and 45k LUT explosion); unpipelined combinational multipliers (introduces long critical paths).
- Expected mechanism: Synchronous registered read; non-blocking assignment read-first conflict resolution; 64-bit full product + symmetric rounding offset + dynamic saturation clamp.

## Frozen acceptance criteria

- Success threshold:
  - `tb_ram_primitives.sv`: 100% pass across normal read/write, boundary addresses, same-address read-first collision, memory retention across reset, and multi-width parameterization.
  - `tb_requant_mac.sv`: 100% pass across shift=0, positive/negative half-values, shift 0..31 sweep, INT32 extremes, saturation bounds (+127/-128), ReLU mode, and 2-cycle pipeline latency.
  - No asynchronous memory reads or array reset loops in RTL.
  - No modifications to contracts, training scripts, old FPGA projects, or public index.
  - No Gowin synthesis, PnR, SRAM download, UART, or SDRAM operations executed.
- Failure/rollback threshold: Any test failure, non-bit-exact rounding result, array reset loop, or modified forbidden file.
- Fixed test set, thresholds and measurement conditions: `tb_ram_primitives.sv` (557 tests) and `tb_requant_mac.sv` (124 tests) run via Icarus Verilog.

## Execution

- Entry commands:
  ```powershell
  iverilog -g2012 -o sim_ram.vvp fpga/ec57_hybrid/ecg_sync_sp_ram.sv fpga/ec57_hybrid/ecg_sync_dp_ram.sv fpga/ec57_hybrid/tb/tb_ram_primitives.sv
  vvp sim_ram.vvp

  iverilog -g2012 -o sim_requant.vvp fpga/ec57_hybrid/ecg_requant_mac.sv fpga/ec57_hybrid/tb/tb_requant_mac.sv
  vvp sim_requant.vvp
  ```
- GPU/card or hardware connection used: None (Local RTL simulation only).
- Calibration/Golden sample manifest: Exhaustive arithmetic golden function and boundary test matrices inside testbenches.
- Deviations from the plan: None.

## Results

| Metric | Target / Specification | This run | Status |
|---|---|---|---|
| RAM Primitives Test Count | 557 | 557 | 557 PASS / 0 FAIL |
| RAM Read Latency | Fixed 1 cycle | Fixed 1 cycle | PASS |
| RAM Collision Semantics | Read-First | Read-First verified | PASS |
| Memory Array Reset Policy | Unreset array (No loop) | Pure synchronous data path | PASS |
| Requant MAC Test Count | 124 | 124 | 124 PASS / 0 FAIL |
| Requant Rounding Mode | Round-half-away-from-zero | 100% bit-exact | PASS |
| Requant Saturation Range | Signed INT8 [-128, +127] | Clamped correctly | PASS |
| Requant Pipeline Latency | Fixed 2 cycles | Fixed 2 cycles verified | PASS |

- Per-class or per-layer findings: Both testbenches passed completely on the first full regression run.
- Failed samples/first mismatch: None (0 failures).
- Logs and report paths: `fpga/ec57_hybrid/INTERFACE_ASSUMPTIONS.md`
- Artifact paths and SHA-256:
  - `fpga/ec57_hybrid/ecg_sync_sp_ram.sv`: `01259FA38BD08EB2A344FC6D9DD2D511393E1DC5AB6240ECFE81417494F56EAD`
  - `fpga/ec57_hybrid/ecg_sync_dp_ram.sv`: `F478AB557FF67A0137094A1BDD54078D2D6FD7B78369DE529A7006A73974C30C`
  - `fpga/ec57_hybrid/ecg_requant_mac.sv`: `BAEEC28BE9F7D8A11697958D7A381BDCAA22534842CACD01BDB8C7B48C94D575`
  - `fpga/ec57_hybrid/INTERFACE_ASSUMPTIONS.md`: `965D7993A0B65953B9C5C2CF23826A8BBA835C6833CB3E32AF63E8C724A65641`
  - `fpga/ec57_hybrid/tb/tb_ram_primitives.sv`: `AFE0C7720077F8F7B1BB078690DE1AC9833BEB205CCDF50FB43CD63A3398DC24`
  - `fpga/ec57_hybrid/tb/tb_requant_mac.sv`: `AF596F60E856EAE082DC97DF8ED8A4BE60B4CDE2CDF9C2E36406A669AFD90A18`
- Unverified items: Full CNN integration and Gowin EDA synthesis BSRAM/DSP resource report verification (will be conducted during M4 top-level implementation).

## Decision

- Decision: `continue`
- Reason: All generic RTL infrastructure modules (SP RAM, Simple DP RAM, Requant MAC) and their comprehensive testbenches have been implemented and verified with 100% bit-exact simulation passes.
- What changed in the project baseline: Added `fpga/ec57_hybrid/` infrastructure modules and interface assumptions.
- One primary question for the next run: When M3 integer export produces the quantized weight/bias bundle, are multiplier and shift values directly compliant with the 32-bit/5-bit interface defined in `ecg_requant_mac.sv`?
- **审核状态声明**：等待中央审核登记 INDEX，因此 RTL 基础节点尚未正式关闭。
