# Optimization Run: `20260829-194939-m1f-stream-contract-and-qfp-closure`

## Identity

- Run ID: `20260829-194939-m1f-stream-contract-and-qfp-closure`
- Stage: `train`
- Status: `completed`
- Started/finished: `2026-08-29T19:49:39+08:00 / 2026-08-29T20:06:46+08:00`
- Agent/operator: Codex M1 completion iteration
- Baseline run: `20260829-1815-m1-m2-central-audit-correction`
- Git commit: dirty shared worktree on `main`; existing untracked M0-M4 work is authoritative and cannot be safely moved to an isolated worktree
- Data version and split hash: LUDB 1.0.1, 200 development records, existing verified raw-file manifest
- Config/contract paths: `contracts/ec57_hybrid_io_contract.json`, `contracts/ec57_hybrid_metrics_contract.json`
- Environment: local Windows PowerShell; `D:\software\anaconda\envs\torch_evn\python.exe`; CPU-only

## Problem and evidence

- Observed problem:
  1. `CausalPureIntegerQRSDetector.feed_chunk()` coerces inputs through `int(s)`, so float/bool samples can bypass the fixed-path fail-closed contract.
  2. One `step()` can commit a searchback event and a current primary event but return only one scalar event, so the streamed event list can diverge from `accepted_peaks`.
  3. The corrected whole-record LUDB baseline has QTP=1824, QFN=8, QFP=333, Gross Se=99.563% and Gross +P=84.562%; M1 remains open.
- Evidence from the baseline: `docs/reports/20260829-1815-m1-m2-central-audit-correction/summary.json`.
- Primary metric or failure point: stream/final event equivalence and Gross QRS +P below 99.50%.

## Optimization

- Method:
  1. Add failing tests for `feed_chunk` float/bool rejection and for simultaneous searchback/current-primary event delivery; then make the smallest API-compatible correction.
  2. Quantify all 333 QFPs by causal observables only: record-relative time, RR distance, raw amplitude/slope/energy, selected-lead agreement and SQI. Do not infer a true beat from missing annotations.
  3. Evaluate predeclared traditional causal candidates independently: stricter multi-lead vote, T-wave slope/energy discrimination, refractory/ripple arbitration, and adaptive noise/energy thresholds. No CNN, locked database, answer-derived evaluation span, future lookahead, or end-of-record suppression.
  4. Select a candidate only on the same full 200-record LUDB development set and re-run the independent float/fixed report.
- Why this method: it first restores the deployment event contract, then addresses the measured false-positive bottleneck using FPGA-representable causal integer features.
- Alternatives considered and why not selected:
  - Reference-span clipping or ignoring boundary detections: rejected because it changes the frozen denominator using annotations.
  - CNN/learned veto before M1 closes: rejected because M1 is the traditional QRS/SQI gate and M2 cannot precede it.
  - Locked MIT/AHA/NST/INCART tuning: prohibited by the data-governance contract.
- Expected mechanism: remove duplicate/T-wave/noise candidates without losing more than one additional true QRS across 1,832 references.

## Frozen acceptance criteria

- Success threshold:
  - Fixed input paths reject float and bool without coercion.
  - Every committed QRS event is returned exactly once and in order by streaming APIs; chunking and prefix invariance remain bit-exact.
  - LUDB full 10-second evaluation, `learning_period_s=0`, `evaluation_span=None`: Gross and Average QRS Se and +P all `>=99.50%`; therefore QFN and QFP must each be `<=9` at the gross count.
  - 200/200 records evaluated, zero evaluation errors, annotation mapping error `<=2 ms`, no locked database access.
  - Independent float/fixed differences are reported, never forced to zero by shared implementation.
  - Full EC57 unit suite passes with no failures/errors.
- Failure/rollback threshold: any causal/integer/stream invariant failure, Se or +P below its frozen gate, or use of answer-derived clipping means `continue`/`reject`; M1 remains open and M2/M3 stay blocked.
- Fixed test set, thresholds and measurement conditions: official local LUDB 1.0.1 all 200 records; 250 Hz target; 150 ms matching; whole 10 seconds; no learning period; unchanged reference clustering.

## Execution

- Entry command or script: tests first, then `train/ec57/evaluate_ludb.py` into a run-specific report directory.
- GPU/card or hardware connection used: none; this iteration is CPU-only traditional QRS work.
- Calibration/Golden sample manifest: not applicable; existing LUDB raw-file manifest is reused and re-hashed in the evidence package.
- Deviations from the plan: none at start.

## Results

| Metric | Baseline | This run | Delta | Comparable? |
|---|---:|---:|---:|---|
| EC57 unit tests | 121/121 | 122/122 | +1 regression | yes |
| Fixed Gross QTP / QFN / QFP | 1824 / 8 / 333 | 1824 / 8 / 333 | 0 / 0 / 0 | yes |
| Fixed Gross Se | 99.563% | 99.563% | 0.000 pp | yes |
| Fixed Gross +P | 84.562% | 84.562% | 0.000 pp | yes |
| Stream/final event loss in constructed collision | 1 event lost | 0 events lost | fixed | yes |
| Invalid float/bool chunk input | silently coerced | rejected | fixed | yes |

- Per-class or per-layer findings:
  - TDD RED reproduced both defects; the two focused tests failed before implementation and passed after the minimal fix.
  - A simultaneous searchback/current-primary collision is now serialized through `pending_primary`, preserving the one-event-per-clock interface and final/event-stream equality.
  - Full taxonomy after the repair still contains 333 QFP and 8 QFN: 212 heuristic baseline/noise, 112 startup, 8 T-wave and 1 window-boundary.
  - Position audit is more informative than the heuristic labels: 112/333 QFP are before 0.75 s, 166/333 are in the last 1 s, and only 55/333 are in the remaining interval.
  - Direct raw-annotation inspection confirms LUDB contains unannotated boundary cycles. For example, `data/1` is 10 s but its clustered QRS references cover samples 331..1984 at 250 Hz. Across all 200 records, first-reference range is 149..694 and last-reference range is 1819..2398 samples.
  - Published LUDB usage literature independently documents that the first and last cardiac cycles are not annotated and crops/removes them for validation. This means counting every detector output over all 10 s as FP is not a valid ground-truth comparison; suppressing those outputs in the detector would optimize against missing labels rather than physiology.
- Failed samples/first mismatch: medical metric remains the baseline failure, QFP=333 and +P=84.562%; stream contract tests have no remaining mismatch.
- Logs and report paths:
  - `docs/reports/20260829-194939-m1f-stream-contract-and-qfp-closure/full-record/`
  - `docs/reports/20260829-194939-m1f-stream-contract-and-qfp-closure/taxonomy/`
- Artifact paths and SHA-256:
  - `train/ec57/qrs_detector.py`: `6212e254743889f7c1cf33e0d8b1b7c68e53406fbb11bf5a934f69f9e084eef5`
  - `tests/ec57/test_qrs_reference.py`: `e52e9cfddcdd63350fdabc391e52079c36fec9106545e842dadb177c7a68735e`
  - `full-record/summary.json`: `67f56ec2b0739e6bbd64ac33c80b6aa0720156a7c12c1ac7576133aa2121f96a`
  - `full-record/sha256_manifest.txt`: `201ea3f669c179475fc1ba2af093ae20dba7734dd4736e0d68b52ceef3579a31`
  - `taxonomy/taxonomy_summary.json`: `ee29c8b65ae9d14a670682ba3bc751c5872f87ae6b8a907d1da2b923b0a52b4c`
  - `taxonomy/sha256_manifest.txt`: `f06f4d3fe68918c925f3db0d54d53e19b704f8a08d3219aa8dcf968a7e53d6c1`
- External evidence consulted:
  - LUDB official database description: `https://physionet.org/content/ludb/1.0.1/`
  - Correia Matias et al., *Time Series Segmentation Using Neural Networks with Cross-Domain Transfer Learning*: `https://www.mdpi.com/2079-9292/10/15/1805`
- Unverified items:
  - A revised LUDB annotated-interval evaluation contract has not been approved or implemented.
  - Locked databases, CNN training, quantization, RTL, HIL and board work were not accessed.

## Decision

- Decision: `continue`
- Reason: the streaming/integer contract repair is accepted, but the pre-frozen full-10-second +P gate still fails. Evidence now shows the failure is dominated by known missing LUDB boundary annotations, so further detector suppression would be scientifically invalid. M1 remains open pending an explicitly approved LUDB valid-annotation-interval contract.
- What changed in the project baseline: fixed inputs fail closed at the chunk API; simultaneous searchback/primary events are serialized without loss; 122 tests pass; whole-record medical metrics are unchanged and honestly retained as failed.
- One primary question for the next run: approve replacing LUDB whole-record scoring with a predeclared valid-annotation interval rule, while retaining full-record event counts as a separate diagnostic, then re-run M1 acceptance.
