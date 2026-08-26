# 优化迭代索引

所有训练、量化、GoAI、RTL、综合和板测实验都必须在这里登记。按时间追加，不覆盖旧记录。

| Run ID | Date | Stage | Baseline | Optimization | Reason | Key result | Decision | Record |
|---|---|---|---|---|---|---|---|---|
| `20260826-1425-m0-preflight` | 2026-08-26 | M0 | `06b5d23` | read-only environment/JTAG/GPU preflight | resolve hardware/tool assumptions before model work | QN88 confirmed by user; SDRAM test pending; GPU 0 candidate | continue software preparation; hold memory-backed RTL | [record](records/20260826-1425-m0-preflight.md) |
| `20260826-1455-m1-ptbxl-fp32` | 2026-08-26 | M1 | `5e6777d` | sequential PTB-XL 100 Hz acquisition | establish dataset provenance and registry | metadata/labels pass; waveform attempt aborted for throughput | superseded by parallel method | [record](records/20260826-1455-m1-ptbxl-fp32.md) |
| `20260826-1515-m1-ptbxl-parallel-download` | 2026-08-26 | M1 | `5e6777d` | bounded parallel PTB-XL acquisition | complete 100 Hz source without changing contents | aborted/superseded | superseded by 64-worker attempt | [record](records/20260826-1515-m1-ptbxl-parallel-download.md) |
| `20260826-1535-m1-ptbxl-parallel64` | 2026-08-26 | M1 | `5e6777d` | bounded 64-worker PTB-XL acquisition | test higher safe concurrency after 16-worker throughput was insufficient | aborted: server timeouts | switch to bounded sample run | [record](records/20260826-1535-m1-ptbxl-parallel64.md) |
| `20260826-1615-m3-int8-level1` | 2026-08-26 | M3 | `5e6777d` | signed INT8 MAC and requantize/clip units | freeze arithmetic semantics before model-derived RTL | passed Level 1 | freeze arithmetic for M2 vectors | [record](records/20260826-1615-m3-int8-level1.md) |
| `20260826-1715-m1-ptbxl-sample-smoke` | 2026-08-26 | M1 | `20260826-1535-m1-ptbxl-parallel64` | bounded sample acquisition and single-seed smoke test | validate WFDB/labels/training without waiting for bulk transfer | passed smoke only; full benchmark pending | proceed to INT8 integration; no benchmark claim | [record](records/20260826-1715-m1-ptbxl-sample-smoke.md) |
| `20260826-1745-m2-ptq-smoke` | 2026-08-26 | M2 | `20260826-1715-m1-ptbxl-sample-smoke` | static per-tensor symmetric INT8 PTQ | align model quantization with frozen RTL rounding/clipping | passed semantics smoke; full-data gate pending | proceed to Level-2 vectors; no benchmark claim | [record](records/20260826-1745-m2-ptq-smoke.md) |
