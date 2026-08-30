# Optimization Run: `20260828-0855-m4-rtl-primitives-review`

## Identity

- Run ID: `20260828-0855-m4-rtl-primitives-review`
- Stage: `rtl`
- Status: `completed`
- Started/finished: `2026-08-28T08:54:45+08:00 / 2026-08-28T08:57:25+08:00`
- Agent/operator: Codex central reviewer
- Baseline run: `20260827-2210-m4-ec57-rtl-primitives`
- Git commit: `6e618a2cb509fb8eb252d2ac346bdf3c3694e776` (working-tree review; no commit created)
- Data version and split hash: N/A; generic RTL primitive review
- Contract paths: `contracts/hardware_contract.json`, `docs/superpowers/plans/2026-08-27-qn88-ec57-hybrid-implementation.md`, `fpga/ec57_hybrid/INTERFACE_ASSUMPTIONS.md`
- Environment: Windows; Icarus Verilog 12.0, SystemVerilog 2012; no Gowin synthesis/PnR or board use

## Problem and evidence

- The original record used an incorrect Git baseline (`da66332`) and claimed that an inference attribute and two-stage pipeline guaranteed Gowin BSRAM mapping and 27 MHz timing. Icarus behavioral simulation cannot prove either claim.
- RAM tests did not exercise sustained no-bubble concurrent read/write, output hold on an enable bubble, or the first legal read immediately after reset release.
- Test failures used `$stop`, which may not return a nonzero process status, and the requant latency wording mixed register-stage count with acceptance-edge latency.
- The RAM `rst_n` compatibility ports were unused but the caller's enable-gating responsibility was not explicit enough. Cross-port same-address read-first behavior was only an RTL behavioral result, not a mapped-hardware guarantee.

## Optimization

- Method:
  1. Add 32-cycle no-bubble simple-dual-port concurrent read/write coverage, enable-hold checks and first-legal-read-after-reset coverage.
  2. Add independent signed extreme requant vectors and explicit E0-accept/E1-output valid checks.
  3. Replace failure `$stop` with `$fatal(1, ...)`.
  4. Document unused RAM reset ports, caller gating, provisional ReLU scope and mapped-collision limitations.
  5. Replace ambiguous two-cycle wording with the exact edge relationship.
- Why this method: it strengthens behavioral verification without pretending to have performed Gowin synthesis, primitive simulation, PnR or physical-board verification.
- ReLU decision: retain the port provisionally for Conv-ReLU fusion; M3 must accept identical semantics or M4 must tie it low/split it into a separate module.

## Frozen acceptance criteria

- RAM self-checking regression passes 625/625 with no-bubble, collision, enable-hold, parameterization and reset-release coverage.
- Requant regression passes 132/132 including shifts 0..31, signed extremes, saturation, ReLU, streaming and exact E0/E1 valid timing.
- Any test failure returns a nonzero simulator process result.
- RAM data paths remain synchronous and contain no synthesizable array reset loop or asynchronous read.
- No claim of BSRAM/DSP inference, mapped collision mode or 27 MHz timing is accepted without Gowin reports.
- No synthesis, PnR, SRAM download, serial, SDRAM or Flash action occurs.

## Execution

```powershell
iverilog -g2012 -Wall -o .codex_review_ram.vvp fpga/ec57_hybrid/ecg_sync_sp_ram.sv fpga/ec57_hybrid/ecg_sync_dp_ram.sv fpga/ec57_hybrid/tb/tb_ram_primitives.sv
vvp -n .codex_review_ram.vvp
iverilog -g2012 -Wall -o .codex_review_requant.vvp fpga/ec57_hybrid/ecg_requant_mac.sv fpga/ec57_hybrid/tb/tb_requant_mac.sv
vvp -n .codex_review_requant.vvp
```

- Hardware/GPU used: None
- Deviation: central review edits began before this separate superseding record was created. The original record remains immutable; this record contains the corrected evidence boundary and current hashes.

## Results

| Metric | Reviewed result | Status |
|---|---:|---|
| RAM primitives | 625 PASS / 0 FAIL | PASS |
| Requant MAC | 132 PASS / 0 FAIL | PASS |
| No-bubble DP concurrent R/W | 32 consecutive cycles plus readback | PASS |
| Failure exit behavior | `$fatal(1, ...)` | PASS |
| BSRAM/DSP mapping | not executed | UNVERIFIED |
| 27 MHz PnR timing | not executed | UNVERIFIED |
| Mapped same-address collision | not executed | UNVERIFIED |

- Artifact paths and SHA-256:
  - `fpga/ec57_hybrid/ecg_sync_sp_ram.sv`: `B14B21C124291F10E4CAD885AE7EF56DA6E1A516B8F3C180EA1F8B7E315B4456`
  - `fpga/ec57_hybrid/ecg_sync_dp_ram.sv`: `965EA827ACDAC8C5F7A0130185F73B09D16A799DFFCC5C4A3BD86CA811A7F9D6`
  - `fpga/ec57_hybrid/ecg_requant_mac.sv`: `A84327860AF86850555ECB4E30CF2C71338302404987B9C4994068846EB1B9E2`
  - `fpga/ec57_hybrid/INTERFACE_ASSUMPTIONS.md`: `C3E91D9F05A1582E46AE99A6886363EA8BE6466542F113577882E8F2177B4DEC`
  - `fpga/ec57_hybrid/tb/tb_ram_primitives.sv`: `55D77DA3DCB90D6DD40AD15DB86B9755E07CB408837C1CC9D69BDD7347C6EAB7`
  - `fpga/ec57_hybrid/tb/tb_requant_mac.sv`: `1645D5C6FE0695F711B68F8022788E8CD22192E544C7F4F6197D941D7EE60ED8`
- Unverified items: Python M3 cross-implementation Golden equivalence, explicit Gowin primitive simulation, synthesis hierarchy/resource mapping, PnR timing, SRAM/HIL, COM10, SDRAM and full-CNN integration.

## Decision

- Decision: `接受`
- Scope: accept only the generic behavioral RTL primitive baseline and its Icarus tests. This does not close the full M4 node and does not prove physical QN88 behavior.
- Reason: strengthened regressions pass completely and documentation now draws the correct boundary between behavioral simulation and mapped hardware evidence.
