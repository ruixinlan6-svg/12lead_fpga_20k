# Optimization Run: `20260826-1613-m1-ptbxl-full-fp32-retry`

## Identity

- Stage: M1 full PTB-XL FP32 baseline retry
- Date: 2026-08-26
- Owner: Codex implementation agent
- Status: passed_full_fp32
- Baseline: `20260826-1611-m1-ptbxl-record-parser-fix`

## Problem and evidence

- The previous three-seed baseline was invalidated by a missing `21837_lr.hea` caused by a malformed line boundary in the source `RECORDS` index, not by model or GPU behavior.
- The repaired downloader now selects 21,799 paths, downloads/reuses both waveform files per path, and reports zero failures with zero `.part` files.

## Optimization

- Method: rerun the frozen TinyECGCNN FP32 reference on the regenerated complete registry, with seeds 0/1/2 assigned one per idle GPU.
- Why this method: isolate the data-integrity repair from architecture and quantization changes while preserving patient-level folds and the exact model used by the RTL plan.

## Frozen acceptance criteria

- Registry: 21,388 labeled records, 18,617 patients, official folds 1–8 train, 9 validation, 10 test; no patient overlap.
- Three seeds complete without data-loader errors and emit config, metrics, checkpoint, environment, and GPU assignment.
- Metrics include macro/per-class AUROC, AUPRC and F1; no test-fold tuning.
- No FPGA programming or Flash write is part of this run.

## Execution

- Remote root: private `C:/Users/Administrator/Desktop/LRX/12lead_fpga_20k_m1`.
- Registry: `runs/20260826-1611-m1-ptbxl-record-parser-fix/data_registry`.
- Candidate GPUs: 0, 1, 2 were checked idle before launch; one seed per GPU.
- Planned command: 8 epochs, batch size 64, `num_workers=0`, CUDA devices 0/1/2.

## Results

- Three seeds completed 8 epochs without data-loader errors on the complete registry. Test metrics:
  - seed0: macro AUROC `0.8593784697`, macro AUPRC `0.6839639850`, macro F1 `0.6419707450`.
  - seed1: macro AUROC `0.8578455398`, macro AUPRC `0.6833000120`, macro F1 `0.6345291989`.
  - seed2: macro AUROC `0.8624476890`, macro AUPRC `0.6807188844`, macro F1 `0.6444485069`.
- Artifact SHA-256:
  - seed0 config `4FEDC7F290D73F3AA32500764EEC05B8AC5BD38987B44319576632961F02B324`; metrics `421822BCFF486A7529744B733A6EC0DD41BBAE95535CCDD0619FF4402E4C446D`; checkpoint `ADBE2804AB45A64B0692E208E7A09B7D7F107247E9AC3773B64A01021E8663BE`.
  - seed1 config `9D8E7B60585FFFB0ACB5B4D195FA86EC2DDE946B7340A94A959B1E760CEDF9F9`; metrics `3A54ED9CFA38BD3AD22ECBA1912FD04EEDA6467140DC62549959BBB8A869EA2D`; checkpoint `351691E19F5B0C0C3437DEE984B7FCB0472B4F769FB2C9145D619DC04A9B6075`.
  - seed2 config `E7C764024970495CC272163EFEAACA89F781433C3BD03B67F31B00EF7F324A9A`; metrics `62518614A2AC7085FDCF485FDF844E814A9D7DDE44507B1AA5B005FE6E4D7884`; checkpoint `42D91F5438F033FFFF66849D3D019BC6236B36828FB9576F6287308B508428EA`.

## Decision

- M1 full FP32 baseline accepted as the reproducible reference. Keep the three checkpoints private under the remote LRX folder; do not add them to Git. Proceed to full-data INT8 PTQ only after recording a new optimization run.
