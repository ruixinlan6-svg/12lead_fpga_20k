# Optimization Run: `20260901-130728-m2ae-m4-evidence-and-isolation-audit`

## Identity

- Run ID: `20260901-130728-m2ae-m4-evidence-and-isolation-audit`
- Stage: `train`
- Status: `completed`
- Started/finished: `2026-09-01 13:07 CST / 2026-09-01 13:13 CST`
- Agent/operator: Codex central review
- Baseline run: `20260901-103000-m4d-compensatory-consistency-loss`
- Git commit: pre-run `b1d5b91`
- Data version and split hash: M4 artifacts claim the M2ab lookahead-v2 cache but do not record a verifiable split hash; this is an audit finding, not a substituted hash
- Config/contract paths: `train/ec57/model_nv.py`, `train/ec57/train_nv.py`, `train/ec57/train_nv_remote.py`, `contracts/ec57_hybrid_metrics_contract.json`
- Environment: local Windows PowerShell; read-only evidence audit plus local unit tests; no GPU, internal_test, locked database or board access

## Problem and evidence

- Observed problem: M4a-M4d repeatedly use validation false-positive patients to design the next run, the MAC estimator omits dual-branch projections and bilinear gating, and the training API can open internal_test by default.
- Evidence from the baseline: all 12 M4 artifacts are correctly rejected, but their validation results are repeatedly mined; M4 records lack immutable input/code identity; reported DualBranch MAC and package bytes are stale lower bounds.
- Primary metric or failure point: evidence isolation and fail-closed eligibility, before any further claim that M2 passed.

## Optimization

- Method: disable internal_test access from the training path; make validation-only the default loader/CLI behavior; correct MAC accounting; relabel M4 results as contaminated diagnostic evidence; preserve the original rejected artifacts and hashes.
- Why this method: it closes data leakage and resource-accounting defects without erasing useful diagnostic results.
- Alternatives considered and why not selected: accepting the M4c improvement as an M2 candidate is rejected because +P is only 82.51% and the same validation patients shaped later runs; retroactively inventing split/code hashes is rejected.
- Expected mechanism: future architecture selection must use train-only/group-CV development evidence and reserve a newly frozen, untouched confirmation cohort before internal_test.

## Frozen acceptance criteria

- Success threshold: training cannot receive or evaluate internal_test; default cache loading excludes it; exact MAC tests cover bilinear and every DualBranch embedding size used in M4; M4a-M4d are explicitly diagnostic/not admissible as an unbiased validation gate; full EC57 tests pass.
- Failure/rollback threshold: any default path opens internal_test, any corrected candidate exceeds the unchanged 100,000 MAC / 2,048 B activation / 51,200 B package limits without rejection, or INDEX still presents M4 as an admissible gate result.
- Fixed test set, thresholds and measurement conditions: local `tests/ec57/test_*.py`; no model retraining and no internal_test access.

## Execution

- Entry command or script: `D:/software/anaconda/envs/torch_evn/python.exe -m unittest discover -s tests/ec57 -p "test_*.py" -v`
- GPU/card or hardware connection used: none
- Calibration/Golden sample manifest: not applicable
- Deviations from the plan: none at run creation

## Results

| Metric | Baseline | This run | Delta | Comparable? |
|---|---:|---:|---:|---|
| Internal-test access from training | default/open | prohibited; validation-only default | fail-open closed | yes |
| DualBranch 32/32 MAC | 94,016 reported | 96,832 exact | +2,816 corrected | yes |
| M4 best validation point | Se 90.10%, +P 82.51%, FPR 0.0931% | diagnostic only | eligibility revoked | yes |
| Unit tests | 204/204 PASS before isolation repair | 206/206 PASS | +2 isolation/resource tests | yes |
| Quantization/parity error | not evaluated | not evaluated | N/A | no |
| LUT / FF / BSRAM / DSP | not evaluated | not evaluated | N/A | no |
| Fmax | not evaluated | not evaluated | N/A | no |
| Core / end-to-end latency | not evaluated | not evaluated | N/A | no |

- Per-class or per-layer findings: the 12 M4 artifacts remain correctly `rejected` and `checkpoint_freezable=false`; corrected resources remain below the unchanged hardware gates. DualBranch 24/24, 32/32 and 40/40 are respectively 95,360, 96,832 and 98,304 MAC/beat. Bilinear MLP-96 is 99,522 MAC/beat.
- Failed samples/first mismatch: M4 validation false positives concentrated in patients reused to design later iterations; no internal-test samples opened by this audit.
- Logs and report paths: `docs/reports/20260901-085000-m4a-twostage-high-sensitivity-primary-model/` through `docs/reports/20260901-103000-m4d-compensatory-consistency-loss/`.
- Artifact paths and SHA-256:
  - `00fa7f016f922cb3fee8fa75ac5b37dc13221c92fdc22b322d1f107e02c35a85  train/ec57/model_nv.py`
  - `2270f26414a27c2e0c74ffec024269b55a198949625703f4e1f27cb5f6add846  train/ec57/train_nv.py`
  - `5c0ee878268559b6c5da7c23b95411e3f94c2e6f70669be5be3cff24206ddcfc  train/ec57/train_nv_remote.py`
  - `a6219076fa0125f7908602d5a83c6581a67d42c5b33952a0e4509acd4a76e5af  tests/ec57/test_model_budget.py`
  - `233b773e37f8e6f91aa2d76292cfc4d36d7edaee981053abc108d754f7aaa160  tests/ec57/test_train_pipeline.py`
  - `9fa6db566603ee65e43a8efdcf455c12f9003c88142e36d3e1161ab93567a92d  tests/ec57/test_m2_data_provenance.py`
- Unverified items: fresh unmined validation/confirmation performance, three-seed stability, internal_test, PTQ/QAT, integer Golden, RTL, synthesis and board execution.

## Decision

- Decision: `accept`
- Reason: the training path and default loader now fail closed against internal_test, exact resource regression tests cover the omitted operations, 206/206 tests pass, and contaminated M4 evidence is explicitly quarantined without altering its original rejected artifacts.
- What changed in the project baseline: M2 remains `回到训练`; M4a-M4d cannot be used for acceptance, internal_test remains unopened/unavailable from training, and the next iteration must use train-only group cross-validation plus a newly frozen untouched confirmation cohort.
- One primary question for the next run: can train-only patient-group cross-validation identify a model that reaches +P 95% at Se 90% without further tuning on the exhausted validation cohort?
