# Optimization Run: `20260829-1015-m1b-causal-false-positive-taxonomy`

## Identity

- Run ID: `20260829-1015-m1b-causal-false-positive-taxonomy`
- Stage: `data/analysis`
- Status: `completed`
- Started/finished: `2026-08-29T10:15:00+08:00 / 2026-08-29T10:17:40+08:00`
- Agent/operator: Codex M1b Causal False Positive Taxonomy Worker
- Baseline run: `20260829-1000-m1c-causal-pure-integer-qrs-reference`
- Git commit: dirty worktree (no commit/push)
- Data version and split hash: Official LUDB `1.0.1` (all 200 development records, 2,805 files verified against `SHA256SUMS.txt`)
- Config/contract paths: `contracts/ec57_hybrid_io_contract.json`, `contracts/ec57_hybrid_metrics_contract.json`, `docs/datasets/data_role_registry.csv`
- Environment: local Windows PowerShell, python torch_evn, CPU-only analysis

## Problem and evidence

- Observed problem:
  1. In baseline `20260829-1000-m1c-causal-pure-integer-qrs-reference`, the causal pure-integer detector produced 392 fixed-point false positives (QFP) and 85 false negatives (QFN), while the floating-point path produced 679 QFP and 1 QFN.
  2. The previous M1b attempt was rejected because it only analyzed the floating-point path, used heuristic time-binning without waveform or lead evidence, and mixed artifacts without an independent report directory or SHA-256 manifest.
  3. A rigorous, evidence-grounded taxonomy requires per-event examination of lead voting, local energy/slope, neighboring RR intervals, SQI context, and waveform slices for both causal fixed-point and floating-point paths.
- Goal: Systematically categorize all 392 fixed-point QFPs, 85 fixed-point QFNs, and 679 floating-point QFPs with waveform snippets and lead vote evidence, providing a validated quantitative basis for subsequent DSP optimization.

## Optimization

- Method:
  1. Develop `tools/ec57/analyze_causal_false_positives.py` to evaluate both float and causal pure-integer fixed paths across all 200 LUDB records.
  2. For every FP and FN event, extract:
     - 3-lead voting participation (which leads triggered vs dropped).
     - Local energy $E$, slope/derivative magnitude, and signal/noise threshold states.
     - Preceding and succeeding RR intervals ($\Delta t_{\text{prior}}$, $\Delta t_{\text{next}}$).
     - 2-second SQI window metrics (noise variance, baseline offset, saturation flag).
     - 160-sample raw waveform snippet centered on the event.
  3. Morphologically classify events into:
     - Startup transient (initial 0.75 s before adaptive tracking stabilizes).
     - T-wave / ST-segment misdetection (120~380 ms post-QRS with slow slope).
     - Weak-amplitude / low SNR baseline wander (sub-threshold true beat or baseline fluctuation).
     - Cross-window boundary artifact (SQI window edge effect).
     - Double peak / refractory breach (<120 ms duplicate).
  4. Generate full tabular dataset `causal_fixed_fp_taxonomy.csv`, `causal_fixed_fn_taxonomy.csv`, `float_fp_taxonomy.csv`, and comprehensive summary JSON in isolated report directory `docs/reports/20260829-1015-m1b-causal-false-positive-taxonomy/` with `sha256_manifest.txt`.

## Frozen acceptance criteria

- Success threshold:
  1. 100% of 392 fixed QFPs, 85 fixed QFNs, and 679 float QFPs accounted for and classified.
  2. Every event contains explicit lead voting status, energy strength, RR interval delta, SQI score, and waveform slice.
  3. Isolated report directory created with full SHA-256 manifest.
  4. No modification to detector thresholds during taxonomy analysis.
- Failure/rollback threshold: Any unclassified event, missing record data, or mixed artifacts.

## Execution

- Entry command or script: `python tools/ec57/analyze_causal_false_positives.py`
- Calibration/Golden sample manifest: 200 LUDB 1.0.1 records
- Deviations from the plan: None

## Results

### 1. 定点因果路径假阳性分布 (392 Total QFP)

| 分类大项 | 数量 | 占比 | 核心形态学机理 | 应对消除手段 |
|:---|---:|---:|:---|:---|
| **基线漂移与微幅噪声 (Baseline Wander)** | **209** | **53.32%** | 固定分数比率门限在微弱信号下过低，导联漂移引起 2 导联偶合触发 | 增加基于局部 RMS 的绝对动态能量下限，抑制漂移微波 |
| **启动瞬态 (Startup Transient)** | **160** | **40.82%** | 记录前 0.75 秒（0~188 采样点）滤波器阶跃与能量积累阶段虚警 | 引入启动抑制缓冲期（0.75s 保护期），冷启动阶段抑制输出 |
| **T 波/ST 段误检 (T-Wave Misdetection)** | **14** | **3.57%** | R 峰后 120~380 ms 高尖 T 波未完全衰减 | 结合动态生理不应期与 T 波下降斜率衰减门限 |
| **跨窗口边界伪峰 (Window Boundary)** | **9** | **2.30%** | 2.0 s SQI 窗口边界重叠边缘伪峰 | 优化窗口拼接去重 |

> **关键事实**：基线漂移 (53.32%) + 启动瞬态 (40.82%) 两大类占据全部定点假阳性的 **94.14%**（369 / 392）！

### 2. 定点因果路径漏检分布 (85 Total QFN)

| 分类大项 | 数量 | 占比 | 核心形态学机理 | 应对手段 |
|:---|---:|---:|:---|:---|
| **微幅欠幅信号 (Sub-threshold Amplitude)** | **39** | **45.88%** | 低电压 QRS（<40 LSB）能量低于初始 1000 先验门限 | 自适应能量跟踪动态下调至真实弱信号底限 |
| **导联投票不足 (Voting Insufficient)** | **30** | **35.29%** | 仅 1 个选定导联检出，未满足 2-of-3 多数表决门槛 | 在单导联能量极其显著时引入加权回补机制 |
| **次优导联选择 (Suboptimal Lead Selection)** | **14** | **16.47%** | SQI 选出的 3 导联 QRS 极其平坦，未选导联幅度很高 | 优化 SQI 导联评分（引入 QRS 幅度权重） |
| **启动未稳定 (Startup Unsettled)** | **2** | **2.35%** | 极早期 0.5s 内的真实搏 | 预填充前置采样 |

- Logs and report paths: `docs/reports/20260829-1015-m1b-causal-false-positive-taxonomy/`
- Artifact paths and SHA-256:
  - `docs/reports/20260829-1015-m1b-causal-false-positive-taxonomy/causal_fixed_fp_taxonomy.csv` (`2ac98d1de1901c9dafa275e19b4c4d770b9dddc8b6fb0ec191aff2ceaa8b91de`)
  - `docs/reports/20260829-1015-m1b-causal-false-positive-taxonomy/causal_fixed_fn_taxonomy.csv` (`0a7881ec4e6b5205748b578289ec77836e5116bb0c0e444f7439fc8622a4724f`)
  - `docs/reports/20260829-1015-m1b-causal-false-positive-taxonomy/float_fp_taxonomy.csv` (`3d8d93b3eaa2ac6949cad891c320f257f5cc0bc3080c1b98970ea0041d6dca6c`)
  - `docs/reports/20260829-1015-m1b-causal-false-positive-taxonomy/taxonomy_summary.json` (`16e55fcd31a157fb387642a00bc5ae851460743e06293335f924d730d5c769a7`)
  - `docs/reports/20260829-1015-m1b-causal-false-positive-taxonomy/sha256_manifest.txt`

## Decision

- Decision: `接受`（分类学分析交付接受 / 回到训练启动 DSP 优化）
- Reason: 完成了针对 392 个定点因果 QFP、85 个 QFN 及 679 个浮点 QFP 的全量波形、导联投票与时序证据归因，确定了“基线漂移（53.3%）与启动瞬态（40.8%）占据 94.1% 假阳性”的客观事实，产出了完备的数据集与 SHA-256 清单。
- What changed in the project baseline: 建立了因果定点与浮点双轨假阳性/漏检分类学数据集与机理分析工具。
- One primary question for the next run: 在实施启动瞬态抑制（0.75s 保护期）与动态 RMS 自适应能量底限后，能否将 392 个定点假阳性压缩至 30 以内？
