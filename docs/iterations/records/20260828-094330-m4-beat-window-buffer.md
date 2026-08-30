# Optimization Run: `20260828-094330-m4-beat-window-buffer`

## Identity

- Run ID: `20260828-094330-m4-beat-window-buffer`
- Stage: `rtl`
- Status: `completed`
- Started/finished: `2026-08-28T09:43:30+08:00 / 2026-08-28T14:44:00+08:00`
- Agent/operator: Codex M4 beat-window worker
- Baseline run: `20260828-0942-m4-microbench-central-review`
- Git commit: `6e618a2cb509fb8eb252d2ac346bdf3c3694e776` (dirty shared worktree; only this run's owned paths are in scope)
- Data version and split hash: N/A; deterministic synthetic sample streams only
- Config/contract paths: `docs/superpowers/plans/2026-08-27-qn88-ec57-hybrid-implementation.md`, `fpga/ec57_hybrid/ecg_sync_dp_ram.sv`
- Environment: Windows PowerShell, Icarus Verilog 12.0; optional Gowin V1.9.12.03 target `GW2AR-LV18QN88C8/I7`

## Problem and evidence

- Observed problem: M4 has accepted generic synchronous RAM primitives but no independent beat-window cache that retains selected-lead samples and emits the frozen 160-point `[R-64,R+95]` window.
- Evidence from the baseline: `20260828-0942-m4-microbench-central-review` accepts the generic SP/SDPB/requant infrastructure only and explicitly leaves full ECG RTL unverified.
- Primary metric or failure point: exact sample/index alignment through the one-cycle synchronous RAM read, including overlap, ring wrap, reset and malformed sample sequences.

## Optimization

- Method: test-first implementation of a power-of-two circular buffer built from `ecg_sync_dp_ram`, a four-entry pending-R queue, explicit sequence/error accounting and a cycle-exact serial window interface.
- Why this method: a dual-port synchronous BSRAM allows continuous sample writes while serial windows are read; explicit pending/error state prevents silent loss or unflagged output.
- Alternatives considered and why not selected: copying each accepted beat into a private 160-word register array was rejected because it duplicates storage and risks LUT/FF mapping; asynchronous array reads were rejected because they violate the Gowin BSRAM inference rule; implementing CNN consumers now was rejected because the M3 bundle is not frozen.
- Expected mechanism: write each valid sample at `sample_index mod RAM_DEPTH`, queue accepted R indices, wait until `R+95` is present, then pipeline 160 synchronous reads while preserving the R/index metadata.

## Frozen acceptance criteria

- Success threshold: self-checking TB passes every named scenario with exact 160/160 data and metadata, R at output point index 64, no X/Z, no weak `pass_count>0` assertions, and zero unexpected errors; default pending queue depth is at least four.
- Failure/rollback threshold: any data/index off-by-one, silent queue loss, output after a discontinuity without an error/flush, RAM data reset/clear loop, asynchronous RAM read, X/Z accepted as pass, or any TB scenario not reaching its exact expected count.
- Fixed test set, thresholds and measurement conditions: Icarus `-g2012 -Wall`; single exact window; two overlapping QRS events; 512-word ring wrap; absolute/segment warm-up; five-event queue overflow against depth four; missing, duplicate and out-of-order sample indices; reset while pending/streaming and clean post-reset operation; continuous one-sample-per-clock writes during one-cycle synchronous reads. Optional Gowin target is `GW2AR-LV18QN88C8/I7`, 27 MHz, with inferred BSRAM, no asynchronous RAM, non-negative setup/hold slack. No SRAM/COM10/SDRAM/Flash action is authorized.

## Execution

- Entry command or script:
  - RED 1: Icarus compile failed because `beat_window_buffer.sv` did not exist.
  - GREEN 1: `iverilog -g2012 -Wall` plus `vvp -n` on `ecg_sync_dp_ram.sv`, `beat_window_buffer.sv` and `tb_beat_window_buffer.sv`.
  - RED/GREEN 2: added the segment-first QRS warm-up regression, reproduced an unexpected output, then corrected the segment-local prehistory test.
  - Gowin: `D:\software\Gowin\Gowin_V1.9.12.03_x64\IDE\bin\gw_sh.exe fpga\ec57_hybrid\microbench\beat_window_buffer\build_beat_window_buffer.tcl`.
- GPU/card or hardware connection used: none.
- Calibration/Golden sample manifest: deterministic function of `sample_index`, generated in the TB.
- Deviations from the plan: none at start.

## Results

| Metric | Baseline | This run | Delta | Comparable? |
|---|---:|---:|---:|---|
| Exact TB checks | N/A | 9 scenarios; 10 complete windows; 1,621 checked points | N/A | no |
| X/Z failures | N/A | 0 | N/A | no |
| LUT / FF / BSRAM / DSP | generic primitives only | 698 Logic / 198 registers / 1 BSRAM / 0 DSP | N/A | no |
| Fmax | generic microbench 51.135 MHz | 65.194 MHz | +14.059 MHz | no; different top |
| Window latency/alignment | absent | 160/160 points, R at index 64 | implemented | no |

- Per-class or per-layer findings:
  - The selected-lead ring maps to exactly 1 BSRAM. The four-entry pending-R control array maps to 8 distributed `RAM16` primitives; this is control-state storage, not sample/activation caching.
  - PnR reports 698/20,736 Logic: 414 LUT, 236 ALU and 8 RAM16; 198 registers; 1/46 BSRAM; no DSP.
  - The 27 MHz constraint closes at Fmax 65.194 MHz, worst setup slack +21.698 ns, worst hold slack +0.327 ns, setup/hold TNS 0 and zero violated endpoints.
  - PR1014 remains: the isolated microbench uses generic clock routing because only the clock pin is constrained. A dedicated full-top global-clock solution remains an M5 gate.
  - Gowin generated a build-directory `.fs`, but it was neither copied into formal evidence nor downloaded. With all non-clock pins unconstrained, it is strictly prohibited from board use.
- Failed samples/first mismatch: no mismatch after correction. RED evidence included missing DUT, the Icarus concatenated `$isunknown` portability issue, a TB reset-edge drive bug, and a segment-first QRS warm-up failure; each was resolved before final verification.
- Logs and report paths: `docs/reports/20260828-094330-m4-beat-window-buffer/` contains behavioral, synthesis resource, PnR resource/timing/power/pin and warning evidence; no `.fs` or `.vg` is included.
- Artifact paths and SHA-256: full list in `docs/reports/20260828-094330-m4-beat-window-buffer/sha256_manifest.txt` (SHA-256 `fc05a0ed299e618971251366042e8917324d00268f38900004b65b1165691035`). Key RTL hashes: `beat_window_buffer.sv` `912188cfd23618d836b286654f71da2c46083c6c3caea0f469ba926fa405b431`; TB `33c9641421e7710320ce93c91b105944ef6afc0cabb8750da5207ca67eab85c7`.
- Unverified items: model/CNN integration, M3 golden, top-level protocol, board SRAM, COM10, SDRAM and Flash are out of scope.

## Decision

- Decision: `接受`
- Reason: the isolated beat-window module satisfies its pre-frozen behavioral, synchronous BSRAM, error-accounting, resource and 27 MHz timing gates. Acceptance is limited to this module and microbenchmark; it is not full M4, full CNN, protocol or board acceptance.
- What changed in the project baseline: `beat_window_buffer.sv`, its strict self-checking TB and an isolated Gowin microbenchmark become the accepted next M4 building block after the generic RAM/requant baseline.
- One primary question for the next run: can the accepted window stream be consumed bit-exactly by the future frozen M3 CNN bundle?
