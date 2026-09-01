# Optimization Run: `20260901-075504-m2ad-central-gate-and-50k-contract`

## Identity

- Run ID: `20260901-075504-m2ad-central-gate-and-50k-contract`
- Stage: `train`
- Status: `completed`
- Started/finished: `2026-09-01 07:55 CST / 2026-09-01 08:42 CST`
- Agent/operator: Codex central review
- Baseline run: `20260831-221500-m3i-accepted-model-multiseed-confirmation`
- Git commit: pre-run `b1d5b91`
- Data version and split hash: unchanged M2ab lookahead-v2 cache; no data are opened by this governance repair
- Config/contract paths: `contracts/ec57_hybrid_metrics_contract.json`, `train/ec57/train_nv.py`, `tests/ec57/test_train_pipeline.py`, `tests/ec57/test_model_budget.py`
- Environment: local Windows PowerShell; `D:/software/anaconda/envs/torch_evn/python.exe`; no GPU or board access for this repair

## Problem and evidence

- Observed problem: the validation threshold gate checks VEB +P and VEB FPR but omits the frozen VEB Se threshold. It therefore marked a threshold with VEB Se 6.86% as accepted. The 50 KB exploration also equates parameter count with deployment bytes and assumes an unauthorized `50KB or more` budget.
- Evidence from the baseline: M3h seed 17 reports TP=97, FP=4, Se=6.86%, +P=96.04%; M3i seeds 29 and 43 are rejected and the three-seed Se span is 5.16 percentage points. M3g Candidate 1 contains 50,880 INT8 weight bytes plus 1,096 INT32 bias bytes before requant metadata.
- Primary metric or failure point: complete validation eligibility is the conjunction `VEB Se >= 90%`, `VEB +P >= 95%`, `VEB FPR <= 0.25%`.

## Optimization

- Method: make minimum VEB Se an explicit fail-closed threshold-search input; add regression tests that reject high-precision/low-sensitivity tails; define the user-authorized 50 KiB limit as the complete deployable parameter package rather than parameter count; correct the affected iteration decisions without deleting historical evidence.
- Why this method: it restores the already frozen metric contract and prevents threshold gaming before any further GPU training.
- Alternatives considered and why not selected: keeping Se as a ranking-only metric is rejected because it permits arbitrarily low recall; interpreting 50 KB as weights-only or `50KB+` is rejected because the user authorized expansion *to* 50 KB.
- Expected mechanism: no threshold can be frozen unless all three VEB metrics pass, and no model can be described as within 50 KiB until INT8 weights, INT32 biases and requant metadata are counted.

## Frozen acceptance criteria

- Success threshold: threshold scanner exposes `min_veb_se=0.90`; every accepted threshold simultaneously satisfies Se >=90%, +P >=95%, FPR <=0.25%; low-Se regression fails closed; complete model parameter package <=51,200 bytes.
- Failure/rollback threshold: any accepted low-Se point, any 50 KiB test using raw parameter count as byte size, or any INDEX entry retaining M3h/M3i as accepted.
- Fixed test set, thresholds and measurement conditions: synthetic unit vectors for scanner semantics; local full `tests/ec57/test_*.py`; no Icentia internal_test, locked database, GPU training, PTQ, RTL or board action.

## Execution

- Entry command or script: `D:/software/anaconda/envs/torch_evn/python.exe -m unittest discover -s tests/ec57 -p "test_*.py" -v`
- GPU/card or hardware connection used: none
- Calibration/Golden sample manifest: not applicable
- Deviations from the plan: user explicitly replaced the old 2 KiB model-size ceiling with a 50 KiB complete package ceiling; MAC, activation, DSP, timing and complete-system limits remain frozen until separately revised.

## Results

| Metric | Baseline | This run | Delta | Comparable? |
|---|---:|---:|---:|---|
| Accepted validation gate dimensions | 2 | 3 (Se>=90%, +P>=95%, FPR<=0.25%) | +1 (Se restored) | yes |
| Complete deployment package limit | not enforced | payload <=50,176 B plus 1,024 B reserve; serialized export <=51,200 B | enforced | yes |
| Unit tests | 198/198 | 204/204 PASS | +6 regression/contract tests | yes |
| Primary model metric | false accept at Se 6.86% | fail-closed rejection | corrected | yes |
| Quantization/parity error | not valid | exploratory deleted | corrected | no |
| LUT / FF / BSRAM / DSP | not evaluated | not evaluated | N/A | no |
| Fmax | not evaluated | not evaluated | N/A | no |
| Core / end-to-end latency | not evaluated | not evaluated | N/A | no |

- Per-class or per-layer findings: threshold scanner fail-closed verified; low-sensitivity points correctly rejected. Candidate 1 from M3g is 54,168 B payload / 55,192 B conservative package and is therefore outside the 50 KiB contract.
- Artifact cleanup: invalid `int8_deployment` exploratory directory removed; all iteration records (M3f, M3h, M3i) updated to `回到训练`.
- Logs and report paths: `contracts/ec57_hybrid_metrics_contract.json`, `train/ec57/resource_budget.py`, `train/ec57/model_nv.py`, `train/ec57/train_nv.py`, `tests/ec57/test_contracts.py`, `tests/ec57/test_train_pipeline.py`, `tests/ec57/test_model_budget.py`.
- Artifact SHA-256:
  - `33a95cc15afb59616fdfe77472bc79640b291ba4cdf06c69383ba88930254167  train/ec57/resource_budget.py`
  - `42609b79bc89d332d8ef3d85f2ecda6f24b43e0994b0be87d2563b2af0ec5cd3  train/ec57/model_nv.py`
  - `b1fb9f54560497bae4e7b52193d016350e661b6c8d2418a6566fbbbdde52ee5f  train/ec57/train_nv.py`
  - `dd06cc250f1aa421a7afcede73666033e5275b554a2b72284643febc98823c7b  contracts/ec57_hybrid_metrics_contract.json`
  - `e6a7e3d93cddfc323b57b230aed353ac64ebbe90e05be63a13fc1dca8bd8632c  tests/ec57/test_contracts.py`
  - `8f6d6bae9d0484ed79f1a3a1664970f9d97f9bef592b5e13454a7370bb451eaa  tests/ec57/test_model_budget.py`
  - `b0ddfab5e6f933e4bcebcbdc2fcce418924bd9425cf99bc389f4fb9dbe2a984f  tests/ec57/test_train_pipeline.py`
- Unverified items: new model training, three-seed stability, internal_test, PTQ/QAT, integer Golden, RTL, synthesis, HIL and locked external databases.

## Decision

- Decision: `接受` (ACCEPTED - Governance & Metric Contract Repair Completed)
- Reason: The three-metric validation gate (`VEB Se >= 90%`, `VEB +P >= 95%`, `VEB FPR <= 0.25%`) is strictly restored across all scanner and training code. The 50 KiB complete deployment package budget is formally codified and tested. All invalid freeze and acceptance conclusions have been revoked.
- What changed in the project baseline: M2 status is officially restored to `回到训练` with no frozen model.
- One primary question for the next run: Can a <=50 KiB complete two-stage model reach all three VEB validation gates without validation-set tail mining?
