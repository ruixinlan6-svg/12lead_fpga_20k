# Optimization Run: `20260828-0920-m4-gowin-primitives-microbench-fix`

## Identity

- Run ID: `20260828-0920-m4-gowin-primitives-microbench-fix`
- Stage: `synth`
- Status: `completed`
- Started/finished: `2026-08-28T09:16:40+08:00 / 2026-08-28T09:19:00+08:00`
- Agent/operator: Antigravity (FPGA Generic RTL Infrastructure Agent)
- Baseline run: `20260828-0905-m4-gowin-primitives-microbench`
- Git commit: `6e618a2cb509fb8eb252d2ac346bdf3c3694e776`
- Data version and split hash: N/A; generic RTL primitive microbenchmark
- Contract paths: `contracts/hardware_contract.json`, `docs/superpowers/plans/2026-08-27-qn88-ec57-hybrid-implementation.md`, `fpga/ec57_hybrid/INTERFACE_ASSUMPTIONS.md`
- Environment: Windows, Gowin EDA V1.9.12.03 (`gw_sh.exe`), Target Device `GW2AR-LV18QN88C8/I7`, Icarus Verilog 12.0

## Problem and evidence

- Observed problem:
  1. Baseline run `20260828-0905-m4-gowin-primitives-microbench` testbench had a weak assertion (`pass_count > 0`) that allowed X-state contaminated signatures (`0xxx`) to pass without a fatal assertion.
  2. The SP/DP RAM synchronous read outputs lacked valid pipeline registers in the top wrapper, prematurely accumulating uninitialized RAM data into `dout_data`.
  3. Evidence files were stored only under the gitignored `build/` tree, making them non-reproducible in fresh checkouts.
  4. The timing report hash in the previous run pointed to the HTML frame wrapper instead of `gowin_primitives_microbench_tr_content.html`.
  5. The PnR warning `PR1014` regarding generic clock routing was unrecorded.
  6. Resource units were mixed between macro primitives, PnR units, and 18x18 multiplier equivalent counts.
- Evidence from baseline: Review decision for `20260828-0905-m4-gowin-primitives-microbench` was `回到 RTL/存储架构`, requesting clean valid pipelines, a cycle-accurate scoreboard, complete report packaging under `docs/reports/`, distinct resource reporting, and proper INDEX registration.
- Primary repair:
  1. Updated `ecg_gowin_primitives_microbench_top.sv` with explicit 1-cycle `sp_dout_valid` and `dp_dout_valid` registers and strict zero-gating before signature reduction.
  2. Implemented `tb_gowin_primitives_microbench_top.sv` with a cycle-accurate scoreboard, strict `$isunknown` checks, and `$fatal(1)` on any mismatch.
  3. Re-ran Gowin EDA V1.9.12.03 synthesis and PnR.
  4. Archived the complete minimal evidence package under `docs/reports/20260828-0920-m4-gowin-primitives-microbench-fix/`.

## Optimization

- Method:
  1. **Valid Pipeline Fix**:
     - SP RAM: `sp_dout_valid <= sp_en_reg;`
     - DP RAM: `dp_dout_valid <= dp_rd_en_reg;`
     - Gated terms: `sp_term = sp_dout_valid ? sp_dout : 8'd0;` etc.
     - Result: `dout_data` is guaranteed deterministic on every clock cycle with zero X/Z propagation.
  2. **Cycle-Accurate Scoreboard Testbench**:
     - Modeled exact SP RAM (2048x8), DP RAM (2048x8), and Requant MAC (64-bit rounded arithmetic right shift + saturation clamping) behavioral pipelines.
     - Checked every cycle for `!$isunknown(dout_data)`, `dout_valid === exp_dout_valid`, `dout_data === exp_dout_data`, and `status_flags === exp_status_flags`.
  3. **Gowin Synthesis and PnR**:
     - Target: `GW2AR-LV18QN88C8/I7`, Speed grade `C8/I7`.
     - Standard: SystemVerilog 2017 (`set_option -verilog_std sysv2017`).
     - Clock constraint: 27.000 MHz (Period: 37.037 ns).
  4. **Evidence Archival & Prohibition Labeling**:
     - Copied all reports (`.rpt.txt`, `_syn_rsc.xml`, `_tr_content.html`, `.power.html`, `.pin.html`, `.log`, `.vg`, `.fs`) to tracked path `docs/reports/20260828-0920-m4-gowin-primitives-microbench-fix/`.
     - Explicitly labeled `.fs` as non-downloadable microbenchmark bitstream.

## Frozen acceptance criteria

- Preflight regressions:
  - `tb_ram_primitives.sv`: 625/625 PASS.
  - `tb_requant_mac.sv`: 132/132 PASS.
  - `tb_gowin_primitives_microbench_top.sv`: 155/155 cycles checked, 0 mismatches, 0 X/Z errors, final signature `0x61` exact.
- BSRAM mapping: Exactly 2 BSRAM blocks (1 SP + 1 SDPB).
- DSP mapping: 1 `MULT36X36` macro (occupying 2 PnR DSP slots, equivalent to 4 18x18 multipliers).
- Logic utilization: Total Logic `<= 2,000` (actual 838 Logic: 740 LUT4 + 98 ALU).
- Timing: 27.000 MHz clock constraint, WNS `>= 0.000 ns` (Fmax `>= 27.000 MHz`).
- Bitstream status: Marked strictly prohibited from physical board download.
- Evidence: Full reports copied to `docs/reports/` and SHA-256 verified.

## Execution

- Commands executed:
  ```powershell
  # 1. Preflight regressions
  iverilog -g2012 -Wall -o .tb_top.vvp fpga/ec57_hybrid/ecg_sync_sp_ram.sv fpga/ec57_hybrid/ecg_sync_dp_ram.sv fpga/ec57_hybrid/ecg_requant_mac.sv fpga/ec57_hybrid/microbench/gowin_primitives/ecg_gowin_primitives_microbench_top.sv fpga/ec57_hybrid/microbench/gowin_primitives/tb_gowin_primitives_microbench_top.sv
  vvp -n .tb_top.vvp

  # 2. Gowin Synthesis and PnR
  D:\software\Gowin\Gowin_V1.9.12.03_x64\IDE\bin\gw_sh.exe fpga/ec57_hybrid/microbench/gowin_primitives/build_gowin_primitives_microbench.tcl

  # 3. Copy evidence to tracked directory
  Copy-Item ... docs/reports/20260828-0920-m4-gowin-primitives-microbench-fix/
  ```

## Results

### 1. Functional Simulation Summary (Icarus Verilog 12.0)

| Testbench | Scope | Total Tests / Cycles | Pass Count | Fail / X Count | Final Signature | Status |
|---|---|---|---|---|---|---|
| `tb_ram_primitives.sv` | SP/DP RAM synchronous semantics & collisions | 625 | 625 | 0 | - | **PASS** |
| `tb_requant_mac.sv` | 32x32 MAC rounding, shift sweep, clamping, ReLU | 132 | 132 | 0 | - | **PASS** |
| `tb_gowin_primitives_microbench_top.sv` | Microbench Top cycle-accurate Scoreboard & X-check | 155 | 155 | 0 | `0x61` (Exact) | **PASS** |

### 2. Multi-Standard Resource Utilization Summary (`GW2AR-LV18QN88C8/I7`)

| Resource Dimension | Gowin Native Macro Standard | Gowin PnR Tool Standard | Project Hardware Contract Equivalent | Device Budget | Status |
|---|---|---|---|---|---|
| **BSRAM** | 1 SP + 1 SDPB | **2 / 46** (5%) | **2 BSRAM** (36 Kbit / 828 Kbit) | 46 BSRAM | **PASS** |
| **DSP Multipliers** | 1 MULT36X36 | **2 / 24** (9%) | **4 / 48** (18x18 multiplier eq.) | 48 18x18 DSPs | **PASS** |
| **Logic** | 740 LUT + 98 ALU | **838 / 20736** (5%) | **838 Logic Elements** | <= 2,000 (20,736 cap) | **PASS** |
| **Registers (FF)** | 159 Logic + 3 IO | **162 / 15750** (2%) | **162 Flip-Flops** | 15,750 cap | **PASS** |
| **Distributed RAM (SSRAM)** | 0 | **0** | **0** | - | **PASS** |
| **I/O Ports** | 26 ports | **26 / 66** (40%) | **26 Package Pins** | 66 pins | **PASS** |

### 3. Hierarchical Resource Breakdown (`gowin_primitives_microbench_syn_rsc.xml`)

| Module Instance | Primitive / Function | BSRAM (Native) | DSP (Native) | ALU | LUT4 | Register (FF) |
|---|---|---|---|---|---|---|
| `u_sp_ram` | `ecg_sync_sp_ram #(8, 2048)` | **1 SP** | 0 | 0 | 0 | 0 |
| `u_dp_ram` | `ecg_sync_dp_ram #(8, 2048)` | **1 SDPB** | 0 | 0 | 0 | 0 |
| `u_requant_mac` | `ecg_requant_mac #(32,32,8,5)` | 0 | **1 MULT36X36** | 64 | 569 | 16 |
| `top_wrapper` | Valid pipelines, LFSR, Signature | 0 | 0 | 32 | 171 | 146 |
| **Total Top** | `ecg_gowin_primitives_microbench_top` | **2 BSRAM** | **1 MULT36X36** | **96** | **740** | **162** |

### 4. Static Timing Analysis (STA 27.000 MHz / Period 37.037 ns)

| Timing Parameter | Constraint Target | Actual Gowin STA Result | Timing Slack / Margin | Status |
|---|---|---|---|---|
| **Max Clock Frequency (Fmax)** | 27.000 MHz | **51.135 MHz** | +24.135 MHz | **PASS** |
| **Worst Setup Slack (WNS)** | >= 0.000 ns | **+17.481 ns** | +17.481 ns | **PASS** |
| **Setup Total Negative Slack (TNS)** | 0.000 ns | **0.000 ns** (0 violated endpoints / 614) | 0.000 ns | **PASS** |
| **Worst Hold Slack** | >= 0.000 ns | **+0.319 ns** | +0.319 ns | **PASS** |
| **Hold Total Negative Slack (TNS)** | 0.000 ns | **0.000 ns** (0 violated endpoints / 614) | 0.000 ns | **PASS** |
| **Worst Setup Path** | - | `u_requant_mac/stage1_shift_0_s0/Q` -> `u_requant_mac/out_data_3_s0/D` (Data Delay: 19.521 ns, Logic Level: 18) | - | **PASS** |

### 5. PnR Log Warnings & Hardware Safety Notices
- **PnR Warning `PR1014`**:
  `WARN (PR1014) : Generic routing resource will be used to clock signal 'clk_d' by the specified constraint. And then it may lead to the excessive delay or skew`
  - *Analysis*: In this microbenchmark, only Pin 4 (`clk`) is physically constrained without dedicated PLL / HCLK primitives. The Gowin router utilized generic clock routing. Internal static timing analysis closed cleanly at 51.135 MHz with zero setup/hold violations. In future full-chip integration, dedicated global clock buffers (`BUFG` / `GCLK`) will be assigned.
- **Bitstream Safety Notice**:
  The generated bitstream `gowin_primitives_microbench.fs` is a synthesis/PnR microbenchmark verification artifact only. **IT IS STRICTLY PROHIBITED FROM PHYSICAL BOARD DOWNLOAD** because only 1 of 26 pins is constrained in the CST, and remaining I/Os were auto-assigned to LVCMOS18 without PCB pad mapping.
- **Netlist Simulation & Collision Semantic Boundary**:
  Netlist simulation in Icarus Verilog is blocked by the vendor proprietary hierarchical `GSR.GSRO` construct in `prim_sim.v`. In accordance with design standards, the project strictly maintains that **higher-level architectures must not rely on cross-port same-address collision results in physical hardware**.

### 6. Tracked Evidence Package Paths & SHA-256 Hashes

```text
40E4C943487744D83077CD6E14A3A985D9564724618CE350477D4A6EF6575D3E  fpga/ec57_hybrid/microbench/gowin_primitives/ecg_gowin_primitives_microbench_top.sv
3E7035B4208E008C6E892777C1A123CA68FF494D1EEB50E4BC912C79B0342696  fpga/ec57_hybrid/microbench/gowin_primitives/gowin_primitives_microbench.gprj
6E81B9A0F537AB6F770EA5B4BF229F6DB4559D81EB508EEEC1E961BC02E2F267  fpga/ec57_hybrid/microbench/gowin_primitives/gowin_primitives_microbench.cst
5DF56ACB52C762871BAE7CBCA62101CBF86D96E20A15B90462DE60E168F349B7  fpga/ec57_hybrid/microbench/gowin_primitives/timing.sdc
8A01B555A408E412B92B13D05F0D3666ABEBC5131F34771B1CB68E4EEE2CC865  fpga/ec57_hybrid/microbench/gowin_primitives/build_gowin_primitives_microbench.tcl
9C14F35BD3DE38E98AA7FBD243375194A3418F72E34D75667CC9739985050486  fpga/ec57_hybrid/microbench/gowin_primitives/tb_gowin_primitives_microbench_top.sv
8141D96E5FAB52F404B433A1E51743178671BF504F2D727D962A9FEF2A147063  docs/reports/20260828-0920-m4-gowin-primitives-microbench-fix/gowin_primitives_microbench.rpt.txt
95D2E36C1973620201817E3851499ABA2CF93B8FE3A0D440A0956198D0F13C87  docs/reports/20260828-0920-m4-gowin-primitives-microbench-fix/gowin_primitives_microbench_syn_rsc.xml
779CF59C3B1BD32F1E40AECAA6F8399D3CA5DC1E2D2ACAC3327EFA1F54B057CF  docs/reports/20260828-0920-m4-gowin-primitives-microbench-fix/gowin_primitives_microbench_syn.rpt.html
6AD20BBCD15489C4D69F3091FE895357CECB4E56BF41CA36C3CFF9610C774C46  docs/reports/20260828-0920-m4-gowin-primitives-microbench-fix/gowin_primitives_microbench.vg
E0A88C0DEADFB9C42998E3AB49B61FE86B591470A772D34823D15DD0D4AB6867  docs/reports/20260828-0920-m4-gowin-primitives-microbench-fix/gowin_primitives_microbench_tr_content.html
13A732BA21A002D645173D2A41941751929A7171465020DAFC7E8F30537FFF4B  docs/reports/20260828-0920-m4-gowin-primitives-microbench-fix/gowin_primitives_microbench.power.html
1269A3EB3F7E263468F50803C6DF55B65CF19A34C9FD44844ED4CA364064BAEF  docs/reports/20260828-0920-m4-gowin-primitives-microbench-fix/gowin_primitives_microbench.pin.html
2EAF7F65E00D16F5AD1E69C535344D06B480BDAD05C3FE857DE9C9EECE41515D  docs/reports/20260828-0920-m4-gowin-primitives-microbench-fix/gowin_primitives_microbench.log
2D6C710DAF84ADC90822301F349583BE1A0B2B0A814DEB176A78617F0FB9C233  docs/reports/20260828-0920-m4-gowin-primitives-microbench-fix/gowin_primitives_microbench.fs
```

## Decision

- Decision: `接受`
- Scope: Accepted the Gowin EDA synthesis and PnR evidence for generic RTL infrastructure primitives on `GW2AR-LV18QN88C8/I7`.
- Rationale:
  1. All preflight regressions passed 100% (RAM 625/625, Requant 132/132, Scoreboard 155/155 with exact `0x61` signature and zero X-state errors).
  2. SP RAM and DP RAM inferred strictly as 2 hardware BSRAMs with 0 distributed RAM.
  3. Requant MAC mapped into 1 MULT36X36 DSP macro (2 PnR DSP units, equivalent to 4 18x18 multipliers).
  4. Logic utilization is 838 Logic Elements (740 LUT4 + 98 ALU), well within the `<= 2,000` limit.
  5. 27.000 MHz timing closed with Fmax = 51.135 MHz, WNS = +17.481 ns, and 0 timing violations.
  6. Minimal evidence package is archived in the tracked repository path `docs/reports/20260828-0920-m4-gowin-primitives-microbench-fix/`.
  7. Bitstream is explicitly marked non-downloadable; zero unauthorized hardware operations performed.
