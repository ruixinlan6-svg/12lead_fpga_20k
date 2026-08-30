# Optimization Run: `20260829-200930-m1g-annotation-support-impact-analysis`

## Identity

- Run ID: `20260829-200930-m1g-annotation-support-impact-analysis`
- Stage: `data`
- Status: `completed`
- Started/finished: `2026-08-29T20:09:30+08:00 / 2026-08-29T20:19:00+08:00`
- Agent/operator: Codex M1 contract impact analysis
- Baseline run: `20260829-194939-m1f-stream-contract-and-qfp-closure`
- Git commit: dirty shared worktree; no commit/push
- Data version and split hash: LUDB 1.0.1, existing verified 200-record manifest
- Config/contract paths: current contracts remain unchanged; this run is diagnostic only
- Environment: local `torch_evn` Python, CPU-only

## Problem and evidence

- Observed problem: LUDB 10-second signals contain unannotated first/last cardiac cycles; whole-record scoring treats detections in unsupported regions as false positives.
- Evidence from the baseline: 278/333 fixed QFP occur before 0.75 s or in the last 1 s; raw reference support varies by record.
- Primary metric or failure point: quantify the exact impact of an annotation-support mask without changing the shared acceptance contract.

## Optimization

- Method: implement a read-only dual-report analyzer that always preserves full-record counts and separately reports counts inside `[first_reference - 150 ms, last_reference + 150 ms]`.
- Why this method: it provides decision evidence without silently changing `evaluate_ludb.py` or M1 acceptance semantics.
- Alternatives considered and why not selected: fixed 1-second cropping does not match variable annotation support; detector-side boundary suppression would intentionally miss real beats.
- Expected mechanism: unsupported boundary detections move only in the diagnostic comparison; detector outputs and reference annotations remain byte-identical.

## Frozen acceptance criteria

- Success threshold: 200/200 records, zero errors; full-record counts reproduce M1f exactly; support interval derivation is deterministic, rejects empty references, and never changes detector outputs; report contains per-record/full/support counts and SHA-256.
- Failure/rollback threshold: any mismatch to M1f full-record counts, missing raw outputs, or contract mutation invalidates the analysis.
- Fixed test set, thresholds and measurement conditions: LUDB 1.0.1 all records, 250 Hz, 150 ms tolerance, current fixed/float detectors.

## Execution

- Entry command or script: tests first, then support-impact analyzer.
- GPU/card or hardware connection used: none.
- Calibration/Golden sample manifest: not applicable.
- Deviations from the plan: none at start.

## Results

| Metric | Full 10 s diagnostic | Annotation support | Delta |
|---|---:|---:|---:|
| Fixed QTP / QFN / QFP | 1824 / 8 / 333 | 1824 / 8 / 9 | QFP -324 |
| Fixed Gross Se | 99.563% | 99.563% | 0.000 pp |
| Fixed Gross +P | 84.562% | 99.509% | +14.947 pp |
| Fixed Average Se | 99.556% | 99.556% | 0.000 pp |
| Fixed Average +P | 84.182% | 99.566% | +15.384 pp |
| Float QTP / QFN / QFP | 1830 / 2 / 657 | 1830 / 2 / 154 | QFP -503 |
| Float Gross Se / +P | 99.891% / 73.583% | 99.891% / 92.238% | +P +18.655 pp |

- Per-class or per-layer findings:
  - The diagnostic reproduced M1f full-record fixed counts exactly, proving the analyzer did not modify detector outputs or denominators silently.
  - All four fixed annotation-support metrics exceed 99.50%; QFN=8 and QFP=9 are both within the predeclared gross count limits.
  - Independent float +P remains below 99.50%, demonstrating that forcing float/fixed equality would require removing their implementation independence.
  - 324 fixed and 503 float detections fall outside the per-record annotated support and remain explicitly preserved in `per_record.json`.
- Failed samples/first mismatch: no analysis errors; the only unresolved item is approval of the shared metric semantics.
- Logs and report paths: `docs/reports/20260829-200930-m1g-annotation-support-impact-analysis/`.
- Artifact paths and SHA-256:
  - `tools/ec57/analyze_ludb_annotation_support.py`: `81335b6e9be70b02f0a4b4c428f3340cb1882303138f120b3a4fc9ec74c8a830`
  - `tests/ec57/test_annotation_support_analysis.py`: `ee8476607abc24c7ca98faf2b06800468d8f3520fd8b2db58b4452bed7fe8832`
  - `summary.json`: `1aba560bce94619c7666a5a43239aaec2b87a61cbdc67887e60307329d5842bf`
  - `per_record.json`: `5b646bd0f92863576f6ddff2f8f630c3ffa1f5216e92397833fa52f3c836c521`
  - `sha256_manifest.txt`: `c756edb3c83a5e30982de7b09e91068dc957a1763a5c8bba07f7bc015bfe2d4f`; 2/2 listed artifacts verified.
- Verification: `python -m unittest discover -s tests/ec57 -p "test_*.py" -v` reports 127/127 `OK`.
- Unverified items: shared contracts and the main evaluator were deliberately not changed; this diagnostic result is not yet an M1 acceptance claim.

## Decision

- Decision: `continue`
- Reason: the analysis proves that the proposed support rule is deterministic, preserves full diagnostics and makes the fixed deployment reference pass all four LUDB gates. Material contract changes still require explicit user approval before formal M1 acceptance.
- What changed in the project baseline: added a tested diagnostic analyzer and immutable dual-scope evidence; no detector, contract, locked database, GPU, RTL or board state changed.
- One primary question for the next run: approve the two contract changes documented in `docs/research/2026-08-29_LUDB_M1评测合同纠正提案.md`.
