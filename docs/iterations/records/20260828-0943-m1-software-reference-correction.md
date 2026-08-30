# Optimization Run: `20260828-0943-m1-software-reference-correction`

## Identity

- Run ID: `20260828-0943-m1-software-reference-correction`
- Stage: `data`
- Status: `completed`
- Started/finished: `2026-08-28T09:43:00+08:00 / 2026-08-28T14:34:00+08:00`
- Agent/operator: Codex M1 corrective worker
- Baseline run: `20260828-0940-m1-central-review`
- Git commit: `6e618a2cb509fb8eb252d2ac346bdf3c3694e776` (shared dirty worktree; no reset, checkout, or commit)
- Data version and split hash: synthetic-only; no ECG database root will be opened
- Config/contract paths: `contracts/ec57_hybrid_io_contract.json`, `contracts/ec57_hybrid_metrics_contract.json`, `contracts/ec57_label_mapping_v1.json`, `docs/datasets/data_role_registry.csv`
- Environment: Windows PowerShell; Python 3.14.4 standard library; SciPy is not installed; no GPU, network, database, FPGA, board, Flash, or SDRAM access

## Problem and evidence

- Observed problem: the first M1 implementation passed its narrow unit tests but did not fail closed for all dataset-use and path variants, attenuated the 257 Hz QRS passband, did not implement the frozen adaptive energy QRS and three-lead voting semantics, and generated evidence from hard-coded results.
- Evidence from the baseline: central review `20260828-0940-m1-central-review` reproduced 42/42 tests while also reproducing an unknown-context bypass, a `..` locked-root bypass, locked explicit-record leakage, about 0.192 amplitude at 25 Hz after 257->250 resampling, missing adaptive/voting semantics, and hard-coded evidence.
- Primary metric or failure point: test success was not specification compliance; the synthetic software seam cannot be accepted while any governance bypass, QRS-band distortion, frozen-QRS omission, or non-executable evidence remains.

## Optimization

- Method: add adversarial tests first; make registry use and Windows-path handling fail closed; validate explicit records and supplied splits as one patient-ownership set; replace the incorrect fractional filter with a fixed rational-phase Kaiser-windowed sinc; implement adaptive integrated-energy QRS with bounded fixed arithmetic and three-lead voting; generate evidence by running registry, detector, and evaluator into a tracked report directory.
- Why this method: each central-review blocker receives a negative or numerical regression test tied directly to the M1 contract, while the evidence generator becomes a consumer of the same public implementations later agents will use.
- Alternatives considered and why not selected: SciPy `resample_poly` is allowed by the plan but is unavailable in the local Python environment; installing packages or accessing the network is unnecessary. A fixed standard-library polyphase implementation will instead be checked against analytic target-time sinusoids. Raw-amplitude QRS thresholds and hard-coded evidence are rejected because they do not exercise the frozen algorithm.
- Expected mechanism: canonical absolute lexical Windows paths eliminate separator/case aliases and reject parent traversal; role/use checks occur before split emission; a cutoff expressed on the source grid preserves 5-40 Hz for near-unity resampling; adaptive signal/noise levels operate on integrated energy; voting clusters per-lead peaks within the frozen 80 ms window; evidence values are derived from actual temporary synthetic inputs and outputs.

## Frozen acceptance criteria

- Success threshold: all unknown usages and contexts reject; case/separator aliases and all paths containing `..` reject; locked explicit records never enter development outputs; any patient appearing in more than one split across supplied and explicit metadata rejects; every referenced raw-file digest matches the actual inventory; all attack tests pass.
- Success threshold: 257->250 resampling of deterministic 5, 10, 25, and 40 Hz unit sinusoids has steady-state fitted amplitude in `[0.98, 1.02]`, fitted phase error `<=0.02 rad`, RMS error against analytic target-time truth `<=0.02`, and event mapping error `<=2 ms`.
- Success threshold: QRS detection decisions use 5-25 Hz filtered derivative-square-30-point integrated energy with adaptive signal/noise thresholds; fixed filter accumulation saturates to signed 40-bit and derivative has explicit `/8` semantics; synthetic noise, baseline wander, amplitude variation, refractory/searchback, dropout, boundary, and float/fixed timestamp tests all pass.
- Success threshold: three-lead fusion requires at least two peaks within an inclusive 80 ms span and emits their median; exactly one valid lead emits its peaks with `DEGRADED_ONE_LEAD`; zero valid leads emits `SIGNAL_LOSS` and no peaks.
- Success threshold: `generate_reference_evidence` invokes the registry, detectors, and evaluator; a test perturbs its synthetic input and observes derived output change; tracked `docs/reports/20260828-0943-m1-software-reference-correction/` contains configuration, execution summary, float/fixed differences, failed samples, test log, and SHA-256 manifest.
- Failure/rollback threshold: any governance bypass; passband or timestamp threshold failure; missing adaptive/voting behavior; fixed arithmetic boundary failure; evidence value remaining hard-coded; any real ECG database/GPU/network/hardware access; any modification outside assigned files; or any full-suite regression.
- Fixed test set, thresholds and measurement conditions: deterministic synthetic metadata/signals only; 250 Hz QRS path; 257 Hz source with edge trimming for resampling; `python -m unittest discover -s tests/ec57 -p "test_*.py" -v`; LUDB and all locked databases remain `not_evaluated`.

## Execution

- Entry command or script:
  - RED: `python -m unittest tests.ec57.test_registry_no_leakage -v` (10 expected failures), `python -m unittest tests.ec57.test_resample_timestamps -v` (4 expected failures), `python -m unittest tests.ec57.test_qrs_reference -v` (missing APIs/behavior).
  - GREEN: targeted suites above, then `python -m unittest discover -s tests/ec57 -p "test_*.py" -v`.
  - Syntax: `python -m py_compile train/ec57/build_registry.py train/ec57/resample.py train/ec57/sqi.py train/ec57/qrs_detector.py train/ec57/heart_rate.py train/ec57/evaluate_qrs.py`.
  - Evidence: `python train/ec57/evaluate_qrs.py --output-dir docs/reports/20260828-0943-m1-software-reference-correction --run-id 20260828-0943-m1-software-reference-correction`.
- GPU/card or hardware connection used: none; prohibited
- Calibration/Golden sample manifest: deterministic synthetic metadata and waveforms only
- Deviations from the plan: no isolated worktree because the coordinating agent explicitly assigned file ownership in the shared dirty workspace; `docs/iterations/INDEX.md` is reserved for central review and will not be modified; real LUDB evaluation remains outside this corrective run.

## Results

| Metric | Baseline | This run | Delta | Comparable? |
|---|---:|---:|---:|---|
| Governance adversarial cases | bypasses present | 13/13 registry tests pass | bypasses rejected | yes |
| 257->250 25 Hz amplitude | about 0.192 | 1.000217 | +0.8116 | yes |
| Adaptive QRS / lead voting | incomplete | 14/14 QRS/SQI tests pass | frozen synthetic behaviors present | yes |
| Executable evidence | hard-coded | registry/detector/evaluator executed | derived evidence | yes |
| LUDB QRS Se / +P | not evaluated | not evaluated | N/A | yes |

- Per-class or per-layer findings:
  - Unknown usage/context, relative/traversal locked paths, locked explicit records, cross-source patient leakage and raw-file hash mismatch now reject before output creation.
  - The source-grid rational polyphase FIR preserves deterministic 5/10/25/40 Hz inputs with amplitudes 0.999995/1.000005/1.000217/0.999687; all phase errors are below 0.000002 rad and all RMS errors below 0.00025.
  - Fixed QRS arithmetic now exposes signed 40-bit saturation and `/8` derivative semantics. Integrated-energy adaptive thresholds, 200 ms refractory/searchback and inclusive 2-of-3/80 ms lead fusion are covered by synthetic tests.
  - Evidence generation creates a temporary synthetic registry and runs both detectors and the evaluator; the default case produces QTP=3, QFN=0, QFP=0 and zero float/fixed timestamp mismatch. These synthetic percentages are not database performance claims.
- Failed samples/first mismatch: none after correction; the RED phase reproduced all central-review failures before implementation.
- Logs and report paths: `docs/reports/20260828-0943-m1-software-reference-correction/`; full suite result is 54/54 `OK` and `py_compile` exits 0.
- Artifact paths and SHA-256: complete file-level hashes are in `docs/reports/20260828-0943-m1-software-reference-correction/sha256_manifest.txt` (SHA-256 `7f890247545af22390d55cbe4e65e6bce5960e1cfdf4a853cec755a5fa3fbb6f`). Key code hashes: `build_registry.py` `a473284d357c12f6f6347a77cca5b0f91afd9f86e8be76cbb4a98d51fdb37825`; `resample.py` `e4ce7c8638343f9218738487dc0a97b4999f1e1504855d9b1f5d69c0d0ae14f1`; `qrs_detector.py` `3645824996ada29756650857b4ffc89d0a374b1d348286a06c02dd3162224508`; `evaluate_qrs.py` `5137ff7a36cb37dc4de5cc6e04eb928a30c8fd2387055d5e5e7a41e77da02316`.
- Unverified items: real LUDB performance, WFDB `bxb`, all locked-database metrics, long-duration signals, training, quantization, RTL, synthesis, HIL, and board behavior

## Decision

- Decision: `接受`
- Reason: all frozen synthetic correction gates and the full EC57 local regression pass, with executable tracked evidence and no database/GPU/hardware access. Acceptance is strictly limited to the corrected synthetic software seam; LUDB remains untested, so the project milestone `M1-reference-accepted` remains open and M2 training remains gated.
- What changed in the project baseline: the corrected fail-closed registry, source-grid resampler, SQI window guard, adaptive float/fixed QRS plus lead fusion, and executable synthetic evidence replace the rejected M1 synthetic implementation as the software reference candidate.
- One primary question for the next run: after the synthetic software seam is corrected, can lawful LUDB evaluation meet QRS Se/+P >=99.5% without consulting any locked database?
