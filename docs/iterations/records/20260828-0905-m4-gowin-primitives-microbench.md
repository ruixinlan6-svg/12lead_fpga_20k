# Optimization Run: `20260828-0905-m4-gowin-primitives-microbench`

## Identity

- Run ID: `20260828-0905-m4-gowin-primitives-microbench`
- Stage: `synth`
- Status: `completed`
- Started/finished: `2026-08-28T09:05:00+08:00 / 2026-08-28T09:04:45+08:00`
- Agent/operator: Antigravity (FPGA Generic RTL Infrastructure Agent)
- Baseline run: `20260828-0855-m4-rtl-primitives-review`
- Git commit: `6e618a2cb509fb8eb252d2ac346bdf3c3694e776`
- Data version and split hash: N/A; generic RTL primitive microbenchmark
- Contract paths: `contracts/hardware_contract.json`, `docs/superpowers/plans/2026-08-27-qn88-ec57-hybrid-implementation.md`, `fpga/ec57_hybrid/INTERFACE_ASSUMPTIONS.md`
- Environment: Windows, Gowin EDA V1.9.12.03 (`gw_sh.exe`), Target Device `GW2AR-LV18QN88C8/I7`, Icarus Verilog 12.0

## Problem and evidence

- Observed problem: While behavioral SystemVerilog models for `ecg_sync_sp_ram`, `ecg_sync_dp_ram`, and `ecg_requant_mac` passed Icarus regressions (625/625 and 132/132), hardware mapping evidence on the target Gowin GW2AR-18C FPGA (BSRAM inference, DSP mapping, logic count, and 27 MHz timing closure) had not yet been verified.
- Evidence from baseline: Review run `20260828-0855-m4-rtl-primitives-review` marked BSRAM/DSP mapping and 27 MHz PnR timing as UNVERIFIED, requiring synthesis and PnR evidence on Gowin EDA V1.9.12.03.
- Primary repair/verification: Built a dedicated, non-optimizable Gowin EDA microbenchmark project instantiating a 2048x8 SP RAM, a 2048x8 DP RAM, and a 32x32 Requant MAC. Executed headless synthesis and PnR to extract hierarchy utilization, placement, and STA timing reports.

## Optimization

- Method:
  1. Created `fpga/ec57_hybrid/microbench/gowin_primitives/` microbench top with dynamic stimulus and observable signature accumulation to prevent synthesis logic trimming.
  2. Instantiated:
     - `ecg_sync_sp_ram #(8, 2048)` (16 Kbit memory) -> verified BSRAM inference.
     - `ecg_sync_dp_ram #(8, 2048)` (16 Kbit memory) -> verified SDPB BSRAM inference.
     - `ecg_requant_mac #(32, 32, 8, 5)` (32x32 multiplier, shift 0..31, INT8 output) -> verified DSP mapping.
  3. Formulated Gowin project (`gowin_primitives_microbench.gprj`), SDC timing constraint (`27.000 MHz / 37.037 ns`), CST physical constraint (`gowin_primitives_microbench.cst`), and build script (`build_gowin_primitives_microbench.tcl`).
  4. Executed Gowin synthesis and PnR via `gw_sh.exe` with SystemVerilog standard `sysv2017`.
  5. Audited BSRAM, DSP, LUT4, WNS, and Fmax against frozen criteria.
- Why this method: Provides indisputable EDA mapping evidence for the primitives before integrating them into larger CNN and QRS pipelines.
- Alternatives considered and why not selected: Whole-top full CNN synthesis (too complex for isolating primitive mapping issues); behavioral simulation only (cannot prove physical hardware feasibility).
- Expected mechanism: GowinSynthesis pattern matches SP RAM to 1 BSRAM (SP mode), DP RAM to 1 BSRAM (SDPB mode), and 32x32 multiplication to 1 MULT36X36 DSP block.

## Frozen acceptance criteria

- Preflight: Icarus Verilog RAM regression 625/625 PASS, Requant regression 132/132 PASS.
- Device: `GW2AR-LV18QN88C8/I7` (Speed grade C8/I7, Package QN88).
- BSRAM mapping: Exactly 2 BSRAM blocks (1 for SP RAM 2048x8, 1 for DP RAM 2048x8).
- DSP mapping: 1 to 4 DSP macros (DSP48 / 18x18 multipliers). Requant must not degrade into thousands of LUTs.
- Logic utilization: Microbenchmark top LUT4 `<= 2,000`.
- Timing: 27.000 MHz constraint (Period: 37.037 ns), Worst Negative Slack (WNS) `>= 0.000 ns` (Fmax `>= 27.000 MHz`).
- Forbidden actions: No COM10 connection, no JTAG/SRAM download, no Flash write, no SDRAM read/write, no modification of existing board projects or contract files.

## Execution

- Preflight regression:
  ```powershell
  iverilog -g2012 -Wall -o .tb_ram.vvp fpga/ec57_hybrid/ecg_sync_sp_ram.sv fpga/ec57_hybrid/ecg_sync_dp_ram.sv fpga/ec57_hybrid/tb/tb_ram_primitives.sv
  vvp -n .tb_ram.vvp
  iverilog -g2012 -Wall -o .tb_requant.vvp fpga/ec57_hybrid/ecg_requant_mac.sv fpga/ec57_hybrid/tb/tb_requant_mac.sv
  vvp -n .tb_requant.vvp
  ```
- Gowin EDA synthesis and PnR:
  ```powershell
  D:\software\Gowin\Gowin_V1.9.12.03_x64\IDE\bin\gw_sh.exe fpga/ec57_hybrid/microbench/gowin_primitives/build_gowin_primitives_microbench.tcl
  ```

## Results

### 1. Global Resource Utilization Summary (`GW2AR-LV18QN88C8/I7`)

| Resource | Target Threshold | Actual Usage | Device Capacity | Utilization | Status |
|---|---|---|---|---|---|
| **BSRAM** | == 2 | **2** (1 SP + 1 SDPB) | 46 blocks (828 Kbit) | 4.35% | **PASS** |
| **DSP** | 1 ~ 4 | **2** (1 MULT36X36 macro) | 24 (48 18x18 units) | 8.33% | **PASS** |
| **Logic (LUT4 + ALU)** | <= 2,000 | **769** (671 LUT4 + 98 ALU) | 20,736 | 3.71% | **PASS** |
| **Registers (FF)** | <= 2,000 | **162** (157 logic + 5 IO) | 15,750 | 1.03% | **PASS** |
| **SSRAM (RAM16)** | 0 | **0** | - | 0.00% | **PASS** |
| **I/O Pins** | <= 66 | **26** | 66 | 39.39% | **PASS** |

### 2. Hierarchical Resource Breakdown (`gowin_primitives_microbench_syn_rsc.xml`)

| Module Instance | Primitive / Function | BSRAM | DSP (MULT36X36) | ALU | LUT4 | Register (FF) |
|---|---|---|---|---|---|---|
| `u_sp_ram` | `ecg_sync_sp_ram #(8, 2048)` | **1** (SP) | 0 | 0 | 0 | 0 |
| `u_dp_ram` | `ecg_sync_dp_ram #(8, 2048)` | **1** (SDPB) | 0 | 0 | 0 | 0 |
| `u_requant_mac` | `ecg_requant_mac #(32,32,8,5)` | 0 | **1** (MULT36X36) | 64 | 501 | 16 |
| `top_wrapper` | Stimulus, LFSR, Signature | 0 | 0 | 32 | 170 | 146 |
| **Total Top** | `ecg_gowin_primitives_microbench_top` | **2** | **1** | **96** | **671** | **162** |

### 3. STA Timing Report Summary (27.000 MHz Constraint / Period 37.037 ns)

| Metric | Target | Actual Gowin STA Result | Margin / Slack | Status |
|---|---|---|---|---|
| **Clock Frequency (clk)** | 27.000 MHz | **54.122 MHz** | +27.122 MHz | **PASS** |
| **Setup Slack (WNS)** | >= 0.000 ns | **+18.560 ns** | +18.560 ns | **PASS** |
| **Setup TNS** | 0.000 ns | **0.000 ns** (0 violated endpoints) | 0.000 ns | **PASS** |
| **Hold Slack** | >= 0.000 ns | **+0.225 ns** | +0.225 ns | **PASS** |
| **Hold TNS** | 0.000 ns | **0.000 ns** (0 violated endpoints) | 0.000 ns | **PASS** |
| **Worst Setup Path** | - | `u_requant_mac/stage1_shift_0_s0/Q` -> `u_requant_mac/out_data_6_s0/D` (Data Delay: 18.442 ns) | - | **PASS** |

### 4. Same-Address Collision Boundary & Verification Notes
- **Icarus Verilog Behavioral Verification**: Confirmed Read-First semantics in RTL simulation for SP RAM and DP RAM (625/625 tests pass).
- **Mapped Hardware Collision Boundary**: Vendor primitive simulation in Icarus is blocked by proprietary `GSR.GSRO` global hierarchical reference in `prim_sim.v`. In accordance with Item 8 of the guidelines, we strictly maintain the rule that **the top-level CNN/buffer architecture must not rely on cross-port same-address collision results on physical hardware**. If simultaneous read/write to the same address is ever required by an algorithm, explicit write-forwarding logic must be implemented in the controller.
- **Provisional ReLU Impact**: Requant MAC's optional `relu_en` multiplexing accounts for a small fraction of the 501 LUTs in `u_requant_mac`; its interface remains provisional for future Conv-ReLU fusion.

### 5. Artifact Paths and SHA-256 Hashes

```text
21D389A37D89CEEF312508E5D5CC91770A827A6462024A1FB4AE7FF1373755B2  fpga/ec57_hybrid/microbench/gowin_primitives/ecg_gowin_primitives_microbench_top.sv
3E7035B4208E008C6E892777C1A123CA68FF494D1EEB50E4BC912C79B0342696  fpga/ec57_hybrid/microbench/gowin_primitives/gowin_primitives_microbench.gprj
6E81B9A0F537AB6F770EA5B4BF229F6DB4559D81EB508EEEC1E961BC02E2F267  fpga/ec57_hybrid/microbench/gowin_primitives/gowin_primitives_microbench.cst
5DF56ACB52C762871BAE7CBCA62101CBF86D96E20A15B90462DE60E168F349B7  fpga/ec57_hybrid/microbench/gowin_primitives/timing.sdc
8A01B555A408E412B92B13D05F0D3666ABEBC5131F34771B1CB68E4EEE2CC865  fpga/ec57_hybrid/microbench/gowin_primitives/build_gowin_primitives_microbench.tcl
F65158BAB6A1B15E2CB0E8D180DD3858561E11701FA395CFFEAF41151F375B3B  fpga/ec57_hybrid/microbench/gowin_primitives/tb_gowin_primitives_microbench_top.sv
488FF78DA6C2D01005BC71417CD66AC04E9F8F756F72520154312274D8A9091D  fpga/ec57_hybrid/microbench/gowin_primitives/build/gowin_primitives_microbench/impl/pnr/gowin_primitives_microbench.rpt.txt
A9C6D62541CBBFC13CD21E9BE5121D75C20C05C7C819BBB730A11710FB434263  fpga/ec57_hybrid/microbench/gowin_primitives/build/gowin_primitives_microbench/impl/gwsynthesis/gowin_primitives_microbench_syn_rsc.xml
F57135D844CE57C7954B775646CE53488E4CEEB4F94C00B11B96435D52EE2B60  fpga/ec57_hybrid/microbench/gowin_primitives/build/gowin_primitives_microbench/impl/pnr/gowin_primitives_microbench.fs
E999532521A115881C12DD552C5C1C1A9F862E7D99176B3973A769A11518B7FF  fpga/ec57_hybrid/microbench/gowin_primitives/build/gowin_primitives_microbench/impl/pnr/gowin_primitives_microbench.tr.html
43902840595AB8B70BCB710B77861EAABD82C2D2830FF406EE3D6F398202D284  fpga/ec57_hybrid/microbench/gowin_primitives/build/gowin_primitives_microbench/impl/gwsynthesis/gowin_primitives_microbench_syn.rpt.html
D9C913E1386389381BCCEEF284D8CC18826572F449FDC2AEC9E87CFB9B5ECD82  fpga/ec57_hybrid/microbench/gowin_primitives/build/gowin_primitives_microbench/impl/gwsynthesis/gowin_primitives_microbench.vg
8342686239D247F4454C4AEF34D8BC629AA150825EA4C4F6D50D462CB9B942B1  fpga/ec57_hybrid/microbench/gowin_primitives/build/gowin_primitives_microbench/impl/pnr/gowin_primitives_microbench.power.html
```

## Decision

- Decision: `接受`
- Scope: Accepted the Gowin EDA synthesis and PnR mapping evidence for the generic RTL infrastructure primitives on `GW2AR-LV18QN88C8/I7`.
- Reason:
  1. Both 2048x8 SP RAM and 2048x8 DP RAM inferred cleanly into hardware BSRAMs (1 SP + 1 SDPB = 2 BSRAMs total, 0 RAM LUT/DFF expansion).
  2. Requant MAC mapped into hardware DSP (`1 MULT36X36` macro).
  3. Total logic utilization is 769 LUT4 (3.71%), well within the `<= 2,000` limit.
  4. Timing closed cleanly at 27 MHz with Fmax = 54.122 MHz and WNS = +18.560 ns (TNS = 0.000 ns).
  5. Zero forbidden operations performed (no board access, no Flash/SDRAM writes, no contract/top file alterations).
- **追溯状态声明**：等待中央审核登记 INDEX，因此微基准节点尚未在公共索引正式关闭。
