# Optimization Run: `20260828-1450-m4-delayed-qrs-handshake`

## Identity

- Run ID: `20260828-1450-m4-delayed-qrs-handshake`
- Stage: `rtl`
- Status: `completed`
- Started/finished: `2026-08-28T14:50:07+08:00 / 2026-08-28T14:54:33+08:00`
- Agent/operator: Codex central reviewer
- Baseline run: `20260828-094330-m4-beat-window-buffer`
- Git commit: `6e618a2cb509fb8eb252d2ac346bdf3c3694e776` (shared dirty worktree; no reset, checkout, or commit)
- Data version and split hash: N/A; deterministic synthetic sample stream only
- Config/contract paths: `docs/superpowers/plans/2026-08-27-qn88-ec57-hybrid-implementation.md`, `fpga/ec57_hybrid/beat_window_buffer.sv`
- Environment: Windows PowerShell; Icarus Verilog 12.0; Gowin V1.9.12.03 target `GW2AR-LV18QN88C8/I7`; no board access

## Problem and evidence

- Observed problem: `beat_window_buffer` currently treats every `qrs_valid` cycle without simultaneous `sample_valid` as `qrs_after_current`, so a legal QRS decision arriving after its referenced sample is already stored cannot enter the pending window queue.
- Evidence from the baseline: the nine accepted scenarios only asserted `qrs_valid` on a sample-write cycle; RTL line 128 defines `qrs_after_current` using `!sample_valid`, and line 144 requires `sample_valid` for enqueue.
- Primary metric or failure point: an independently timed QRS event referencing an in-segment, already stored sample must produce the exact 160-point window without incrementing `qrs_reference_error_count`.

## Optimization

- Method: add a failing testbench scenario that streams sufficient pre/post history, deasserts `sample_valid`, then presents a QRS index already present in the ring; replace same-cycle coupling with a comparison against the newest accepted sample index while preserving warm-up, stale, future-reference and discontinuity fail-closed behavior.
- Why this method: sample ingestion and QRS detection are independent pipelines at a 27 MHz fabric clock; the contract identifies samples by `sample_index` and does not require their valid strobes to coincide.
- Alternatives considered and why not selected: forcing the QRS detector or top level to delay/replay `sample_valid` would couple unrelated pipelines and risk duplicate sample writes; adding an asynchronous queue outside this module would hide rather than correct the module interface contract.
- Expected mechanism: when no new sample is present, `last_sample_index` and `segment_start_index` define the valid history boundary; a QRS at or before that boundary can enqueue, while a future, pre-segment, warm-up or stale reference is still rejected explicitly.

## Frozen acceptance criteria

- Success threshold: the new delayed-QRS scenario fails on the baseline and passes after the fix with 160/160 exact samples, R at point 64, no X/Z, zero unexpected error counters; all existing nine scenarios remain bit-exact.
- Success threshold: an idle-cycle future QRS reference increments `qrs_reference_error_count` and emits no window; warm-up and stale logic retain their prior behavior.
- Success threshold: isolated Gowin synthesis/PnR still infers exactly one BSRAM for the sample ring, uses no DSP, closes 27 MHz with non-negative setup and hold slack, and formal evidence contains no `.fs`/`.vg`.
- Failure/rollback threshold: any existing regression, same-cycle-only dependency remains, a future QRS is accepted, any RAM clear/asynchronous read is introduced, BSRAM inference is lost, timing fails, or any board/SRAM/Flash action occurs.
- Fixed test set, thresholds and measurement conditions: Icarus `-g2012`; ten named scenarios including delayed legal and delayed future references; Gowin target `GW2AR-LV18QN88C8/I7`, 27 MHz; deterministic synthetic stream only.

## Execution

- Entry command or script: RED and GREEN `iverilog -g2012 -Wall -s tb_beat_window_buffer` followed by `vvp`; isolated Gowin build with `D:\software\Gowin\Gowin_V1.9.12.03_x64\IDE\bin\gw_sh.exe fpga\ec57_hybrid\microbench\beat_window_buffer\build_beat_window_buffer.tcl`.
- GPU/card or hardware connection used: none; prohibited.
- Calibration/Golden sample manifest: deterministic testbench sample function.
- Deviations from the plan: none at start.

## Results

| Metric | Baseline | This run | Delta | Comparable? |
|---|---:|---:|---:|---|
| Delayed-QRS exact window | rejected as reference error | 160/160 points exact; future reference rejected | fixed | yes |
| Existing exact TB checks | 9 scenarios / 1,621 points | all retained; total 10 scenarios / 1,781 points | +1 scenario / +160 points | yes |
| LUT / FF / BSRAM / DSP | 698 Logic / 198 registers / 1 BSRAM / 0 DSP | 807 Logic / 198 registers / 1 BSRAM / 0 DSP | +109 Logic; storage unchanged | yes |
| Fmax | 65.194 MHz | 58.212 MHz | -6.982 MHz; still >27 MHz | yes |

- Per-class or per-layer findings: QRS acceptance now uses the latest accepted sample and current segment boundary when no sample strobe is present. The same-cycle path, warm-up, stale and discontinuity behavior remains covered. PnR reports setup WNS +19.859 ns, hold WNS +0.323 ns, both TNS 0 and zero violated endpoints. The sample ring remains one SDPB BSRAM; the four-entry queue remains eight RAM16.
- Failed samples/first mismatch: RED reproduced `timeout: expected 1 windows, received 0` in scenario 10. GREEN produces the exact delayed window and increments only `qrs_reference_error_count` for the deliberately future R index.
- Logs and report paths: `docs/reports/20260828-1450-m4-delayed-qrs-handshake/`; the behavioral log ends with `BEAT_WINDOW_BUFFER_ALL_PASS scenarios=10 completed_windows=11 checked_points=1781`. PR1014 generic-clock routing remains recorded for the isolated microbenchmark.
- Artifact paths and SHA-256: full list in `docs/reports/20260828-1450-m4-delayed-qrs-handshake/sha256_manifest.txt` (SHA-256 `52fdd7ab5dcdb2ce436f605445c0981bc1b6093d6d3ccb9ebabd6ca60159efc`). Key RTL hashes: `beat_window_buffer.sv` `ccd061dc3cd2fab5f876eadeee4ab01b1616cbcf1d542cc19b6fafc9ea409497`; TB `fbe0087c5568440d09001c07f95c335d04daa5e1ef8d740e6cea9f025a52fe43`.
- Unverified items: full CNN/top/protocol and all board behavior remain out of scope.

## Decision

- Decision: `接受`
- Reason: the independently timed QRS regression fails on the baseline and passes after the minimal handshake correction; all prior scenarios remain exact, future references fail closed, BSRAM inference is preserved and the isolated top closes 27 MHz. Acceptance remains module-only and is not a full M4 or board claim.
- What changed in the project baseline: the beat-window reference boundary no longer requires QRS and sample strobes to coincide; delayed in-segment QRS decisions are now part of the accepted interface behavior.
- One primary question for the next run: can the accepted independent QRS handshake remain bit-exact when connected to the future QRS pipeline?
