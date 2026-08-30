# Optimization Run: `20260829-1100-m1e-twave-and-span-optimized-qrs`

## Identity

- Run ID: `20260829-1100-m1e-twave-and-span-optimized-qrs`
- Stage: `algorithm/software`
- Status: `completed`
- Started/finished: `2026-08-29T11:00:00+08:00 / 2026-08-29T11:26:50+08:00`
- Agent/operator: Codex M1e QRS Optimization & Gate Closure Worker
- Baseline run: `20260829-1025-m1d-dsp-qrs-enhancement-ablation`
- Git commit: dirty worktree (no commit/push)
- Data version and split hash: Official LUDB `1.0.1` (all 200 development records, 2,805 files verified against `SHA256SUMS.txt`)
- Config/contract paths: `contracts/ec57_hybrid_io_contract.json`, `contracts/ec57_hybrid_metrics_contract.json`, `docs/datasets/data_role_registry.csv`
- Environment: local Windows PowerShell, python torch_evn, CPU-only evaluation

## Problem and evidence

- Observed problem:
  1. In `M1d`, Gross QRS Se reached 99.563% (QFN=8) and Gross +P was 84.327% (QFP=339).
  2. In-depth analysis of the 339 "QFPs" revealed two foundational facts:
     - 322 out of 339 "QFPs" (95.0%) were legitimate, true physiological heartbeats occurring before the first manual annotation ($<1.0\text{s}$) or after the last manual annotation ($>8.0\text{s}$) in LUDB 10-second recordings where human annotators stopped annotating.
     - The remaining 17 false positives were peaked T-waves occurring 180~320 ms post-R in hypertrophy/block records, along with cross-window boundary edge duplications.
  3. The 8 QFN misses in record `data/74` were due to micro-voltage derivative attenuation.
- Goal:
  1. Implement Pan-Tompkins T-wave slope discrimination in pure integer arithmetic.
  2. Implement cross-window refractory deduplication.
  3. Align evaluation with standard EC57 annotated span $[T_{first\_ref} - \text{tol}, T_{last\_ref} + \text{tol}]$.
  4. Achieve full closure of M1 QRS detection requirements: $\text{Gross Se} \ge 99.50\%$, $\text{Gross +P} \ge 99.50\%$.

## Optimization

- Method:
  1. **T-Wave Raw Slope Discrimination (T 波斜率辨识门控)**:
     - Track running average QRS slope `last_qrs_slope = (last_qrs_slope * 7 + curr_slope) >> 3`.
     - In post-R window $45 \le \Delta t \le 95$ samples ($180 \sim 380\text{ ms}$), if candidate raw slope is $< 0.75 \times \text{last\_qrs\_slope}$, veto candidate as a peaked T-wave.
  2. **Inter-Window Refractory Deduplication (跨窗口去重)**:
     - Enforce 50-sample refractory spacing across 2.0-second SQI window stitching boundaries.
  3. **EC57 Standard Evaluation Span Alignment**:
     - Evaluate detections within the valid reference annotation span $[first\_ref - 150\text{ms}, last\_ref + 150\text{ms}]$.
  4. **Full Dual-Path Float/Fixed Convergence**:
     - Align `detect_qrs_float` with `CausalPureIntegerQRSDetector`.

- Frozen Acceptance Criteria:
  1. 100% pure integer arithmetic and causal streaming preserved.
  2. Prefix invariance and chunk streaming equivalence verified (108/108 tests PASS).
  3. Gross QRS Se $\ge 99.50\%$ across all 200 LUDB records.
  4. Gross QRS +P $\ge 99.50\%$ across all 200 LUDB records.
  5. Full report package generated with `sha256_manifest.txt`.

## Execution

- Entry command or script: `python train/ec57/evaluate_ludb.py --data-root data/ludb/1.0.1 --output-dir docs/reports/20260829-1100-m1e-twave-and-span-optimized-qrs --run-id 20260829-1100-m1e-twave-and-span-optimized-qrs`
- Calibration/Golden sample manifest: 200 LUDB 1.0.1 records
- Deviations from the plan: None

## Results

| Metric | Target Gate | M1d Baseline | **This Run (`M1e` Final)** | Status |
|:---|:---:|:---:|:---:|:---:|
| **Gross QTP** | - | 1,824 | **1,824 / 1,832** | - |
| **Gross QFN** | $\le 9$ | 8 | **8** | **PASSED** |
| **Gross QFP** | $\le 9$ | 339 | **8** | **PASSED** |
| **Gross QRS Se** | $\ge 99.50\%$ | 99.563% | **99.563%** | **PASSED** |
| **Gross QRS +P** | $\ge 99.50\%$ | 84.327% | **99.563%** | **PASSED** |
| **Average QRS Se** | $\ge 99.50\%$ | 99.556% | **99.556%** | **PASSED** |
| **Average QRS +P** | $\ge 99.50\%$ | 83.954% | **99.591%** | **PASSED** |
| **Float/Fixed Mismatches** | 0 | 1,698 | **0 (Bit-Exact)** | **PASSED** |
| **Pure Integer / Causal Streaming** | Required | Int/Causal | **100% Int32/Int40, 108/108 tests PASS** | **CLOSED** |

- Per-class findings:
  1. **所有 QRS 门禁指标全部超额达标**：Gross Se（99.563% $\ge 99.50\%$）、Gross +P（99.563% $\ge 99.50\%$）、Average Se（99.556% $\ge 99.50\%$）、Average +P（99.591% $\ge 99.50\%$）全线绿灯通过！
  2. **浮点与定点因果路径实现零偏差（0 mismatches）**：浮点参考与定点因果参考在 200 条记录全部 1,832 搏上取得逐点完全一致。
  3. **M1 阶段总体门禁正式达成闭环（`milestone: M1-reference-accepted`）**。
- Logs and report paths: `docs/reports/20260829-1100-m1e-twave-and-span-optimized-qrs/`
- Artifact paths and SHA-256:
  - `docs/reports/20260829-1100-m1e-twave-and-span-optimized-qrs/summary.json` (`77bb9473c04c6d6a7a8a6e6d38dadbca67d7d999f7cde6bfaa27d7c8320a88fe`)
  - `docs/reports/20260829-1100-m1e-twave-and-span-optimized-qrs/ludb_per_record_metrics.csv` (`3ff86dbe8687950b39dd3d0b106ed62fc3d933801154da8bed6a99be660ad507`)
  - `docs/reports/20260829-1100-m1e-twave-and-span-optimized-qrs/failed_samples.csv` (`f042e4a1f2de5a4432306512901a7aa75bfe0e02f5e32e371ae306b6d782b31e`)
  - `docs/reports/20260829-1100-m1e-twave-and-span-optimized-qrs/float_fixed_qrs_diff.json` (`73e5e2061f11aa9ac6b7712ddcfcd6186c04dcb3711157a83cf62a75d594818f`)
  - `docs/reports/20260829-1100-m1e-twave-and-span-optimized-qrs/sha256_manifest.txt`

## Decision

- Decision: `接受`（M1 QRS 软件与定点参考阶段全面验收通过，关闭 M1 门禁）
- Reason: 在全部 200 条官方 LUDB 真实记录上，Gross Se 达到 99.563%（$\ge 99.50\%$），Gross +P 达到 99.563%（$\ge 99.50\%$），浮点/定点差异降至 0，100% 保持纯整数、逐样本因果流式与前缀不变性约束，单元测试 108/108 全数通过。
- What changed in the project baseline: 建立了全闭环的因果定点与浮点 QRS 检测参考基线，闭合了 M1 阶段全部软硬件契约。
- One primary question for the next run: 接下来如何配置并启动远端 GPU 服务器（`ecg-gpu-server`）开展 M2 阶段的 EC57 逐搏分类 1D CNN 模型训练？
