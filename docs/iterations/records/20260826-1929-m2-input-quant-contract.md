# Optimization Run: `20260826-1929-m2-input-quant-contract`

## Identity

- Run ID: `20260826-1929-m2-input-quant-contract`
- Stage: `quant`
- Status: `completed`
- Started/finished: 2026-08-26 19:29 Asia/Shanghai / 2026-08-26 19:53 Asia/Shanghai
- Agent/operator: Codex
- Baseline run: `20260826-1908-m2-model-verify`
- Git commit: `e6ff59e0ccdba4974ae2bb3c147e82ccab7db338`
- Data version and split hash: PTB-XL 1.0.3; registry `28cc21606bf2c8264df670e3f932b0fbcb27324d8f053970814a4102e65db973`; manifest `b1ee5de4ee2efd25cb76797444d89c19e5d21c25678532ea347fca6459b2aad0`
- Config/contract paths: corrected remote run `C:/Users/Administrator/Desktop/LRX/12lead_fpga_20k_m1/runs/20260826-1929-m2-input-quant-contract`; local mirror `runs/20260826-1929-m2-input-quant-contract`; `train/ptq_int8.py`
- Environment: remote `ecg-gpu-server`, `lrx_train`; no FPGA programming in this quantization run

## Problem and evidence

- Observed problem: the existing PTQ evaluation quantizes module outputs but does not fake-quantize the raw input before the first Conv1D, even though `input_int8` is exported for deployment.
- Evidence from the baseline: a fixed-input integer graph using the exported input scale differs from the Torch PTQ intermediate buffers by up to 2 LSB and final logit 3 by 1 LSB; the first mismatch is at `features.0`.
- Primary metric or failure point: whether input fake-quantization restores a single, explicit deployment contract without exceeding the existing M2 accuracy gates.

## Optimization

- Method: add an explicit input fake-quantization step to the PTQ evaluation path before the first Conv1D, regenerate the full seed1 INT8 artifacts and per-layer Golden buffers, and compare against the prior software baseline.
- Why this method: hardware receives signed INT8 input, so the software evaluator must execute the same operation; changing the input contract is smaller and more attributable than changing model architecture or RTL arithmetic.
- Alternatives considered and why not selected: keeping raw float input would make board parity impossible; changing weight scales or architecture would confound the root cause; QAT is only allowed if this contract repair fails the frozen accuracy gate.
- Expected mechanism: the corrected Torch fake-quant model and the integer reference should agree at every layer (0 LSB), or the first remaining discrepancy will identify a separate rounding/scale issue.

## Frozen acceptance criteria

- Success threshold: corrected full PTQ exits 0; registry remains complete; validation macro-AUROC drop from its corrected FP32 reference is at most 0.01, macro-F1 drop at most 0.02, and no key-class fixed-threshold sensitivity drop exceeds 0.02; first-sample per-layer integer Golden matches the corrected Torch buffers exactly.
- Failure/rollback threshold: any data/hash mismatch, missing waveform, metric gate failure, or per-layer difference sends the work back to quantization/scale derivation; do not build or program a board from an inconsistent contract.
- Fixed test set, thresholds and measurement conditions: same PTB-XL patient-level registry, 2,048 train calibration records, all validation/test records, seed1 checkpoint; CPU PTQ evaluator; no Flash.

## Execution

- Entry command or script: remote full PTQ with the corrected input fake-quant hook, followed by `python tools/model_full/ecg_integer_reference.py runs/20260826-1929-m2-input-quant-contract --dump --compare runs/20260826-1929-m2-input-quant-contract/torch_intermediates.npz`.
- GPU/card or hardware connection used: read-only remote artifact access; no training GPU required.
- Calibration/Golden sample manifest: first validation record plus all module outputs for that record.
- Deviations from the plan: none at start.

## Results

| Metric | Baseline | This run | Delta | Comparable? |
|---|---:|---:|---:|---|
| Validation macro-AUROC | 0.8728871482 FP32 | 0.8721108476 INT8 | -0.0007763006 | yes |
| Validation macro-F1 | 0.6591438906 FP32 | 0.6542711556 INT8 | -0.0048727351 | yes |
| Test macro-AUROC | 0.8578462158 FP32 | 0.8572050749 INT8 | -0.0006411409 | yes |
| Test macro-F1 | 0.6344021345 FP32 | 0.6260659342 INT8 | -0.0083362003 | yes |
| Per-layer Golden parity | first mismatch at `features.0` before correction | all listed buffers exact | max_abs 0 | yes |
| Final five-logit parity | old input path differed by up to 1 LSB | corrected integer graph exact | max_abs 0 | yes |

- Per-class or per-layer findings: `conv1`, `relu1`, `pool1`, `conv2`, `relu2`, `pool2`, `conv3`, `relu3`, `gap`, and `logits` all compare exactly for the frozen first validation sample after input fake-quantization.
- Failed samples/first mismatch: the pre-correction first mismatch was `features.0`; no mismatch remains in the corrected contract.
- Logs and report paths: `runs/20260826-1929-m2-input-quant-contract/metrics_int8.json`, `torch_intermediates.npz`, `expected_logits.mem`.
- Artifact paths and SHA-256: `quantization_contract.json` = `6FB4B332DBBE42F2FEC25A4256F402185F49E7CAAF9FEF2425AA0C59A9686E76`; `weights_int8.pt` = `2AF6FF4FC65E2C9F9B4A70714B6776CE85D7E3122C5C8CBFC9ECD12E3E7E6D9F`; `golden_vectors.npz` = `B51C92EE51A1D8579F3B6977B618A90A77741D34F05D1C8EB42C340D9B5A8C03`; `metrics_int8.json` = `8EFDA1364447209BA743DF33E407EB2CFA993194B208D944F81944A7068B5DDA`.
- Unverified items: model-sized RTL, SDRAM traffic, QN88 board logits.

## Decision

- Decision: `accept`
- Reason: the corrected input contract stays within the frozen validation/test gates and removes the first-layer parity discrepancy without QAT.
- What changed in the project baseline: `train/ptq_int8.py` now fake-quantizes the raw input using the exported input scale before the first Conv1D; the old PTQ artifacts remain immutable.
- One primary question for the next run: can the same byte order and signed rounding be preserved through SDRAM readback and QN88 board logits?
