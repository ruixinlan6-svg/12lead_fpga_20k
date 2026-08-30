# Optimization Run: `20260829-1000-m1c-causal-pure-integer-qrs-reference`

## Identity

- Run ID: `20260829-1000-m1c-causal-pure-integer-qrs-reference`
- Stage: `algorithm/software`
- Status: `completed`
- Started/finished: `2026-08-29T10:00:00+08:00 / 2026-08-29T10:06:30+08:00`
- Agent/operator: Codex M1c Causal Pure Integer Reference Worker
- Baseline run: `20260829-0940-m1a-fixed-reference-repair`
- Git commit: dirty worktree (no commit/push)
- Data version and split hash: Official LUDB `1.0.1` (all 200 development records, 2,805 files verified against `SHA256SUMS.txt`)
- Config/contract paths: `contracts/ec57_hybrid_io_contract.json`, `contracts/ec57_hybrid_metrics_contract.json`, `docs/datasets/data_role_registry.csv`
- Environment: local Windows PowerShell, python torch_evn, CPU-only evaluation

## Problem and evidence

- Observed problem:
  1. In baseline `20260829-0940-m1a-fixed-reference-repair`, the "fixed" detector `detect_qrs_fixed()` delegated to `_adaptive_candidates()`, which converted integer energy to `float` and used floating-point scalar multiplications (`0.875`, `0.125`, `0.08`, `0.5`).
  2. `_adaptive_candidates()` inspected all local maxima across the entire 10-second recording upfront to compute global maximum and median values for initializing `signal_level` and `noise_level`. This creates an acausal future lookahead that cannot be implemented in a streaming FPGA accelerator.
  3. Appending future samples to a stream retroactively modified initial threshold state and altered previously emitted QRS decisions, violating prefix invariance.
- Evidence from baseline: Code inspection of `train/ec57/qrs_detector.py:316-329` confirms `float(energy[index])`, `signal_level = max(strengths)`, and `0.875 * signal_level`.

## Optimization

- Method:
  1. **Pure Integer State & Arithmetic**: Replace all floating-point math in the fixed path with bit-exact signed integer arithmetic (int32/int40 saturation, bit-shifts for decay `(sig * 7 + str) >> 3`, integer multiplier/shift for adaptive thresholds).
  2. **Strictly Causal Streaming State Machine**: Implement `CausalIntegerQRSDetector` operating sample-by-sample without full-record lookahead. Adaptive signal/noise levels initialize from causal bootstrap rules (e.g. startup window or fixed initial prior) and update monotonically in causal time.
  3. **Prefix Invariance & Streaming Equivalence**: Guarantee that appending future samples to a stream never modifies past emitted QRS timestamps. Prove that streaming chunk sizes of 1, 10, 50, and 500 samples produce 100% bit-exact outputs as batch execution.
  4. **Export Shared Q2.14 Filter Parameters & Accounting**: Explicitly record overflow/saturation counters and layer-by-layer intermediate integer state representations compatible with Gowin RTL modules.
  5. **Independent LUDB 200-Record Evaluation**: Re-run all 200 LUDB records with independent reporting of float and causal pure integer fixed metrics into an isolated directory `docs/reports/20260829-1000-m1c-causal-pure-integer-qrs-reference/`.
- Why this method: Establishes a true, mathematically verifiable 1:1 software reference for FPGA RTL implementation without acausal shortcuts or float dependencies.
- Alternatives considered and why not selected: Retaining floating-point threshold tracking in software was rejected because it violates FPGA deployment equivalence.

## Frozen acceptance criteria

- Success threshold:
  1. 100% pure integer arithmetic in fixed-point detector (0 floating-point operations or float type conversions).
  2. Strictly causal: processing sample $N$ depends exclusively on samples $0 \dots N$.
  3. Prefix invariance & streaming equivalence: for any input ECG signal, streaming sample-by-sample, in 10-sample chunks, in 500-sample chunks, or full-batch yields 100% bit-exact identical QRS peak timestamps.
  4. Unit tests pass (100% PASS with dedicated causal and pure integer regression tests).
  5. Full 200 LUDB records evaluated with complete artifacts and SHA-256 manifest in `docs/reports/20260829-1000-m1c-causal-pure-integer-qrs-reference/`.
- Failure/rollback threshold: Any use of float in fixed path; any acausal future lookahead; any failure in streaming chunk equivalence or prefix invariance; unhandled record errors. Failure conclusion is `回到训练`.

## Execution

- Entry command or script: `python train/ec57/evaluate_ludb.py --data-root data/ludb/1.0.1 --output-dir docs/reports/20260829-1000-m1c-causal-pure-integer-qrs-reference --run-id 20260829-1000-m1c-causal-pure-integer-qrs-reference`
- Calibration/Golden sample manifest: 200 LUDB 1.0.1 records, verified against `SHA256SUMS.txt`
- Status: `completed`

## Results

| Metric | Baseline (`20260829-0940-m1a`) | This run (`20260829-1000-m1c`) Float | This run (`20260829-1000-m1c`) Causal Pure Int | Delta (Causal Int vs Baseline) |
|---|---:|---:|---:|---|
| Gross QTP | 1832 (fixed) / 1831 (float) | 1,831 | **1,747** | -85 (causal startup / unadapted weak beats) |
| Gross QFN | 0 (fixed) / 1 (float) | 1 | **85** | +85 |
| Gross QFP | 578 (fixed) / 679 (float) | 679 | **392** | **-186 (-32.18% FP reduction)** |
| Gross QRS Se | 100.0% (fixed) / 99.945% (float) | 99.945% | **95.360%** | -4.640% |
| Gross QRS +P | 76.017% (fixed) / 72.948% (float) | 72.948% | **81.674%** | **+5.657%** |
| Average QRS Se | 100.0% (fixed) / 99.938% (float) | 99.938% | **95.004%** | -4.996% |
| Average QRS +P | 77.366% (fixed) / 74.908% (float) | 74.908% | **81.165%** | **+3.799%** |
| Float / Fixed Mismatches | 802 | - | **1,302** | +500 (due to strictly causal vs lookahead float) |
| Causal & Pure Integer? | NO (non-causal, float) | N/A (float) | **YES (100% causal pure int)** | **Closed** |
| Prefix Invariant? | NO | N/A | **YES (108/108 PASS)** | **Closed** |
| Streaming Equivalence (1/10/50/500)? | NO | N/A | **YES (Bit-exact match)** | **Closed** |

- Per-class or per-layer findings:
  1. `CausalPureIntegerQRSDetector` eliminates 100% of floating-point operations in fixed path (0 float ops).
  2. Eliminates full-record global lookahead; state machine operates strictly on sample $n$ using past samples $0 \dots n$.
  3. QFP dropped from 578 to 392 without any algorithmic threshold tuning (solely due to causal 30-sample MWI grouping and integer threshold updates).
- Logs and report paths: `docs/reports/20260829-1000-m1c-causal-pure-integer-qrs-reference/`
- Artifact paths and SHA-256:
  - `docs/reports/20260829-1000-m1c-causal-pure-integer-qrs-reference/summary.json` (`a15f321b94e4f78a8c46fbcce7fab3400e3bdc921e42beee6beaf98c27bf884e`)
  - `docs/reports/20260829-1000-m1c-causal-pure-integer-qrs-reference/ludb_per_record_metrics.csv` (`3e2a6607bd21604b2c5dc1112265ec9433e2ef92c87d53490d123ffc06b08b45`)
  - `docs/reports/20260829-1000-m1c-causal-pure-integer-qrs-reference/failed_samples.csv` (`70e06aa51ebbfbf2231d772ba9d9cb57ce0c144d51d31bbe08b25f90ca04f98d`)
  - `docs/reports/20260829-1000-m1c-causal-pure-integer-qrs-reference/float_fixed_qrs_diff.json` (`faa8670632cf21b81453fc2294c81ea93e9fc7c1da9549b20081e9015a14e627`)
  - `docs/reports/20260829-1000-m1c-causal-pure-integer-qrs-reference/sha256_manifest.txt`
- Unverified items: None for M1c scope.

## Decision

- Decision: `partial_accept`（局部验收 / 回到训练）
- Reason: M1c 的“因果、纯整数、可流式复现、前缀不变”核心目标已全部达成，通过了 108/108 项单元测试及 200 条 LUDB 全量因果流式闭环评测；建立了与 RTL 1:1 对应的 Q2.14 整数参数标准。但由于 Se (95.36%) 与 +P (81.67%) 尚未达到 99.50% 门槛，M1 总体门禁保持开启，进入基于真实因果定点基线的重新分类学归因与算法增强。
- What changed in the project baseline: `train/ec57/qrs_detector.py` 实现了 `CausalPureIntegerQRSDetector` 与 `get_fixed_qrs_rtl_parameters()`，彻底移除了定点路径中的浮点运算与全局前视。
- One primary question for the next run: 基于 M1c 产出的 392 个真实定点假阳性与 85 个漏检，如何结合导联波形、能量斜率与 SQI 进行详尽分类归因？
