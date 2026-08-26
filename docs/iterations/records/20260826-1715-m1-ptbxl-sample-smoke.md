# Optimization Run: `20260826-1715-m1-ptbxl-sample-smoke`

## Identity

- Stage: M1 PTB-XL software smoke test
- Date: 2026-08-26
- Owner: Codex implementation agent
- Status: passed_smoke_only
- Baseline: `20260826-1535-m1-ptbxl-parallel64` (aborted by upstream timeouts)

## Problem and evidence

- The metadata registry is complete, but PhysioNet per-file transfer is too slow and returns intermittent `WinError 10060` timeouts at high concurrency.
- A small, explicitly non-claiming sample is sufficient to validate WFDB decoding, tensor shape, label plumbing, and the training loop before solving bulk acquisition.

## Optimization

- Method: reuse verified partial files and acquire only the first bounded `records100` sample needed for a smoke run.
- Why this method: it preserves the PTB-XL source and preprocessing contract while preventing a network bottleneck from blocking software/quantization integration.
- This run must not be reported as a PTB-XL benchmark; full M1 metrics remain pending complete data.

## Frozen acceptance criteria

- No raw waveform or checkpoint enters Git.
- Registry label order, folds, lead order, 100 Hz rate, 10 s length, and mV normalization remain unchanged.
- The script must either complete the requested bounded sample or record the transfer failure; no silent substitution of another dataset is allowed.
- Training output includes config, metrics, checkpoint hash, and the exact sample/registry path.

## Execution

- Remote root: private `LRX/12lead_fpga_20k_m1/data/ptb-xl/1.0.3`.
- Candidate GPU: freshly checked GPU 0 only; GPU 2 remains excluded because it has an active process.
- Planned sample: first 128 records from the deterministic source list; 48 labeled records had both waveform files available after reuse, yielding 16 train, 16 validation, and 16 test examples.

## Results

- Bounded acquisition completed with 8 workers and zero failures for the requested 128 records.
- WFDB decoding and shape checks passed for all records reached by the loader: 12 leads × 1000 samples at 100 Hz.
- Single-seed CUDA smoke run completed on GPU 0 for 3 epochs. Best epoch: 1. Validation macro-AUROC `0.3053571428571429`, macro-AUPRC `0.18198662448662448`, macro-F1 `0.04444444444444444`; test macro-AUROC `0.6076923076923078`, macro-AUPRC `0.30234948011390317`, macro-F1 `0.023529411764705882`.
- These metrics are diagnostic smoke evidence only: the subset is tiny and imbalanced, and does not satisfy the full PTB-XL benchmark gate.
- Registry source hashes remain `RECORDS=56d37274b0b02339e9c30bff8c9a9f2a6fb3cb2bb7bcd5d7c55355451d53896a`, `ptbxl_database.csv=7600de9c1b27d181d850b3c6038a35d7c3ddb6bb33b702e3a20252a6859d216b`, `scp_statements.csv=ad05b0b1fcae83bb1230755ad9cfc7c96f303feddc08a4a9ad5bdc9ca63bac8f`.
- Remote artifact SHA-256: `data_registry.yaml=200b3389f024f88ff1345d74d18016f2ff4b8b6695e6561656baead9151436b6`, `split_manifest.jsonl=45d974a0e92a6f5604c8e4aaaa4aa057f1edf05ad9ad96367eaa7c9250243540`, `seed0/config.json=7793c062a4695a10431ac448e65faa1a56e5e7e435342b7ecec177b452054baf`, `seed0/metrics.json=e6f1825b253cde29368574e1d38497f95d2442a7c70a7e724985a056c24f5939`, `seed0/checkpoint_best.pt=fbc95cfdf020dcb68d43ccbaf3adbdcd6d9273994b70ac483bb2d379f6c0fe63`.

## Decision

- Accept the smoke path for integration work and proceed to model-derived INT8 vectors. Keep the full M1 benchmark gate open until a bulk mirror/archive or complete source acquisition is available; do not tune or publish claims from this subset.
