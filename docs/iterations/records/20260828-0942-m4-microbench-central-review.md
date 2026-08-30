# Optimization Run: `20260828-0942-m4-microbench-central-review`

## Identity

- Run ID: `20260828-0942-m4-microbench-central-review`
- Stage: `synth`
- Status: `completed`
- Started/finished: `2026-08-28T09:32:00+08:00 / 2026-08-28T09:42:00+08:00`
- Agent/operator: Codex central reviewer
- Baseline run: `20260828-0920-m4-gowin-primitives-microbench-fix`
- Git commit: `6e618a2cb509fb8eb252d2ac346bdf3c3694e776`
- Data version and split hash: N/A; generic RTL primitive microbenchmark
- Config/contract paths: `contracts/hardware_contract.json`, `docs/superpowers/plans/2026-08-27-qn88-ec57-hybrid-implementation.md`, `fpga/ec57_hybrid/INTERFACE_ASSUMPTIONS.md`
- Environment: Windows, Icarus Verilog 12.0; Gowin reports produced by V1.9.12.03 for `GW2AR-LV18QN88C8/I7`

## Problem and evidence

- Observed problem: verify that the corrective run eliminated the previous X-state false pass, preserved BSRAM/DSP mapping and 27 MHz timing closure, and made its evidence boundary accurate.
- Evidence from the baseline: the corrective record reported a 155-cycle exact scoreboard, 2 BSRAM, 1 `MULT36X36`, and Fmax 51.135 MHz.
- Primary metric or failure point: functional simulation must be independently reproducible and the archived report values/hashes must match the record.

## Optimization

- Method: recompile and run the microbenchmark scoreboard, verify selected SHA-256 values, inspect the archived resource/timing/log reports, and query Git ignore status for each archived artifact.
- Why this method: the preceding run failed because a weak test allowed an X-valued signature to pass and evidence existed only in ignored build output.
- Alternatives considered and why not selected: synthesis/PnR was not rerun because the archived primary reports and hashes were available and internally consistent; no bitstream was downloaded.
- Expected mechanism: an exact cycle scoreboard plus primary report/hash verification supports a narrowly scoped generic-primitive acceptance.

## Frozen acceptance criteria

- Success threshold: 155/155 scoreboard cycles with signature `0x61`, no X/Z or mismatches; 2 BSRAM and 1 `MULT36X36`; 27 MHz setup/hold closure; report hashes match; PR1014 and the non-downloadable bitstream boundary are explicit.
- Failure/rollback threshold: any functional mismatch/X, distributed-RAM substitution, resource/timing contradiction, missing primary report, or physical download.
- Fixed test set, thresholds and measurement conditions: current RTL at the commit above; Icarus `-g2012 -Wall`; archived Gowin report set under `docs/reports/20260828-0920-m4-gowin-primitives-microbench-fix/`.

## Execution

- Entry command or script: Icarus compile/run of RAM, requant, microbenchmark top and scoreboard; SHA-256 verification; text/XML/HTML/log inspection; `git check-ignore` on the evidence directory.
- GPU/card or hardware connection used: none.
- Calibration/Golden sample manifest: deterministic RTL scoreboard model.
- Deviations from the plan: no Gowin rerun and no board action were needed for this central audit.

## Results

| Metric | Baseline claim | Central review | Delta | Comparable? |
|---|---:|---:|---:|---|
| Scoreboard | 155/155, `0x61` | 155/155, `0x61` | 0 | yes |
| BSRAM | 2/46 | 2/46 | 0 | yes |
| DSP | 1 `MULT36X36` | 1 `MULT36X36` | 0 | yes |
| Fmax / WNS / hold | 51.135 MHz / +17.481 ns / +0.319 ns | report-confirmed | 0 | yes |
| Primary checked hashes | match | 6/6 match | 0 | yes |

- Per-class or per-layer findings: the RAM valid pipelines and fatal cycle-accurate scoreboard remove the previous RTL false pass. The synthesis report confirms SP+SDPB mapping and the multiplier macro. PR1014 remains a disclosed full-chip clock-routing item, not a closed board-clock result.
- Failed samples/first mismatch: none in 155 checked cycles.
- Logs and report paths: `docs/reports/20260828-0920-m4-gowin-primitives-microbench-fix/`.
- Artifact paths and SHA-256: selected RTL, resource, timing and log hashes match the corrective record.
- Unverified items: vendor netlist simulation, physical RAM power-up contents, dedicated global-clock routing in the full top, full CNN/QRS integration, SRAM download, COM10, SDRAM, and board behavior.
- Evidence-boundary correction: `.fs` and `.vg` remain ignored by repository-wide rules and therefore are not clone-reproducible tracked evidence. This does not invalidate the tracked text/XML/HTML/log synthesis evidence. The `.fs` is intentionally excluded from the accepted evidence set and remains prohibited from board download.

## Decision

- Decision: `接受`
- Reason: the generic RTL primitive functional, mapping, resource, and 27 MHz timing claims are independently supported after narrowing the evidence boundary. This is not acceptance of the full ECG RTL or any physical-board result.
- What changed in the project baseline: the corrected SP/SDPB/requant primitive microbenchmark becomes the accepted generic M4 infrastructure baseline; `.fs/.vg` are excluded from the formal tracked evidence claim.
- One primary question for the next run: can the next independent RTL block preserve synchronous BSRAM semantics and bit-exact behavior without depending on the not-yet-frozen M3 model bundle?
