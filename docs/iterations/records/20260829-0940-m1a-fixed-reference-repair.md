# Optimization Run: `20260829-0940-m1a-fixed-reference-repair`

## Identity

- Run ID: `20260829-0940-m1a-fixed-reference-repair`
- Stage: `data`
- Status: `completed`
- Started/finished: `2026-08-29T09:40:00+08:00 / 2026-08-29T09:45:30+08:00`
- Agent/operator: Codex M1a Fixed Reference Repair Worker
- Baseline run: `20260828-144946-m1-ludb-development-evaluation`
- Git commit: dirty worktree (no commit/push)
- Data version and split hash: Official LUDB `1.0.1` (all 200 development records, 2,805 files verified against official `SHA256SUMS.txt`)
- Config/contract paths: `contracts/ec57_hybrid_io_contract.json`, `contracts/ec57_hybrid_metrics_contract.json`, `docs/datasets/data_role_registry.csv`
- Environment: local Windows PowerShell, python torch_evn, CPU-only evaluation

## Problem and evidence

- Observed problem: In baseline evaluation `20260828-144946`, all 200 records produced `fixed_output_count = 0`. The fixed-point filter output and MWI energy decayed to zero immediately after the first SOS biquad stage.
- Evidence from baseline: Initial `design_butterworth_bandpass_sos` assigned the entire filter normalization gain ($G \approx 0.002235$) to Section 0 ($b_0 = 37$ in Q14), while Sections 1..3 had $b_0 = 16384$. For typical ECG signals of 50..200 LSB, Section 0 attenuated the signal by a factor of 440 down to $0 \sim 1$ LSB, and integer truncation in subsequent sections reduced all internal state and output energy to zero.
- Prior incorrect attribution retracted: The 2,510 differences in the prior report were not "minor 1-2 sample rounding deviations", but a total loss of fixed-point filter signal energy. The prior 72.948% +P reflected only the float path.

## Optimization

- Method:
  1. Distribute total normalization gain equally across all 4 SOS biquad sections ($g_k = \sqrt[4]{G} \approx 0.217427$, $b_0 = 3562$ in Q14).
  2. Keep all QRS decision thresholds, refractory periods, SQI windows, lead selection, and fusion logic strictly frozen.
  3. Add non-zero fixed energy and float/fixed candidate regression unit tests (`test_fixed_qrs_energy_is_nonzero_on_realistic_amplitude_signals`, `test_float_and_fixed_per_lead_candidates_and_fused_peaks_match`).
  4. Update `evaluate_ludb.py` to independently compute, record, and report float and fixed QTP/QFN/QFP/Se/+P.
- Why this method: Decouples the numerical fixed-point signal scaling repair from QRS algorithmic threshold tuning.
- Alternatives considered and why not selected: Tuning QRS detection thresholds simultaneously was rejected to prevent confounding numerical fixes with algorithmic changes.

## Frozen acceptance criteria

- Success threshold: Fixed-point filter and MWI energy are strictly non-zero on realistic ECG signals ($50 \sim 200$ LSB); float and fixed per-lead candidate matching passes unit tests; all 200 LUDB records are evaluated with independent reporting of float and fixed metrics.
- Frozen threshold: Gross QRS Se $\ge 99.50\%$, Gross QRS +P $\ge 99.50\%$, maximum mapping error $\le 2.0$ ms, zero unhandled errors across all 200 records.

## Execution

- Entry command: `python train/ec57/evaluate_ludb.py --data-root data/ludb/1.0.1 --output-dir docs/reports/20260829-0940-m1a-fixed-reference-repair --run-id 20260829-0940-m1a-fixed-reference-repair`
- Calibration/Golden sample manifest: 200 LUDB 1.0.1 records, verified against `SHA256SUMS.txt`
- Unit tests: `python -m unittest discover -s tests/ec57 -p "test_*.py" -v` -> 104 / 104 PASS

## Results

| Metric | Baseline (`20260828-144946`) | This run (`20260829-0940`) Float | This run (`20260829-0940`) Fixed | Delta (Fixed vs Base) |
|---|---:|---:|---:|---|
| Gross QTP | 1831 (float) / 0 (fixed) | 1831 / 1832 | **1832 / 1832** | +1832 (fixed) |
| Gross QFN | 1 (float) / 1832 (fixed) | 1 / 1832 | **0 / 1832** | -1832 (fixed) |
| Gross QFP | 679 (float) / 0 (fixed) | 679 | **578** | +578 (authentic) |
| Gross QRS Se | 99.945% (float) / 0.0% (fixed) | 99.945% | **100.000%** | +100.000% |
| Gross QRS +P | 72.948% (float) / N/A (fixed) | 72.948% | **76.017%** | +76.017% |
| Average QRS Se | 99.938% (float) / 0.0% (fixed) | 99.938% | **100.000%** | +100.000% |
| Average QRS +P | 74.908% (float) / N/A (fixed) | 74.908% | **77.366%** | +77.366% |
| Float/Fixed Diff Count | 2510 (all flatlined) | N/A | **802** | -1708 |
| Max Mapping Error | 2.000 ms | 2.000 ms | 2.000 ms | 0.0 ms |

- Findings:
  - Fixed-point SOS biquad signal truncation is completely repaired; fixed-point path achieved 100% QRS Sensitivity (1832/1832 reference beats detected, 0 misses).
  - Fixed-point Positive Predictivity is 76.017% (578 false positives), independently verified alongside floating-point path (72.948%, 679 false positives).
- Logs and report paths: `docs/reports/20260829-0940-m1a-fixed-reference-repair/`
- Artifact paths and SHA-256:
  - `docs/reports/20260829-0940-m1a-fixed-reference-repair/summary.json` (`6ca2bd57fb6003d62f6f5fdfd67f7565d24459446abbd94dce003dcdafcdf80a`)
  - `docs/reports/20260829-0940-m1a-fixed-reference-repair/ludb_per_record_metrics.csv` (`37396463668db142586232fa0f76251d8eb99a29bf6e6e13c869ef929d092ff2`)
  - `docs/reports/20260829-0940-m1a-fixed-reference-repair/failed_samples.csv` (`a030490a7f74e0aef92ece8bc7d871d8858050585476a182e224f98c2929d83d`)
  - `docs/reports/20260829-0940-m1a-fixed-reference-repair/sha256_manifest.txt`

## Decision

- Decision: `partial_accept`（部分接受 / 回到训练）
- Reason: 定点 SOS 滤波器截断归零缺陷已有效修复，定点能量正常输出且敏感度达到 100.0%（1832/1832）；但经审查，当前 `detect_qrs_fixed` 内部仍通过 `_adaptive_candidates()` 引入了浮点运算（`float` 转换与浮点乘加），并使用全记录全局极值/中位数进行了非因果前视初始化，且定点/浮点仍存在 802 处差异，定点 +P 仅为 76.017%。因此本 run 仅能作为数值平线修复的局部接受成果，定点参考仍未闭合，必须在 M1c 中重构成纯整数因果流式状态机。
- What changed in the project baseline: 修复了 `qrs_detector.py` 中 Q2.14 SOS 增益分配，建立了非零定点能量计算与回归测试集；明确了定点检测器尚存浮点与非因果前视的待整改项。
- One primary question for the next run: 如何在消除全记录前视与浮点运算的前提下，构建纯整数、逐样本因果更新且前缀不变的流式定点 QRS 检测器？
