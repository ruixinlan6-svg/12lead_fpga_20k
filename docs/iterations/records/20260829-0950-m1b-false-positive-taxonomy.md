# Optimization Run: `20260829-0950-m1b-false-positive-taxonomy`

## Identity

- Run ID: `20260829-0950-m1b-false-positive-taxonomy`
- Stage: `data`
- Status: `completed`
- Started/finished: `2026-08-29T09:46:00+08:00 / 2026-08-29T09:48:40+08:00`
- Agent/operator: Codex M1b Taxonomy Analysis Worker
- Baseline run: `20260829-0940-m1a-fixed-reference-repair`
- Git commit: dirty worktree (no commit/push)
- Data version and split hash: Official LUDB `1.0.1` (all 200 development records, 2,805 files verified)
- Config/contract paths: `contracts/ec57_hybrid_io_contract.json`, `contracts/ec57_hybrid_metrics_contract.json`, `docs/datasets/data_role_registry.csv`
- Environment: local Windows PowerShell, python torch_evn, CPU-only analysis

## Problem and evidence

- Observed problem: In LUDB baseline evaluation, 679 floating-point false positives (and 578 fixed-point false positives) prevented QRS Positive Predictivity from reaching the $\ge 99.50\%$ threshold (+P is currently $72.95\%$ float, $76.02\%$ fixed).
- Goal: Classify all 679 false positives into a rigorous clinical/DSP taxonomy to determine root causes and formulate a principled reduction plan from 679 down to $\le 9$ false positives (the mathematical limit for $+P \ge 99.5\%$ at $QTP \approx 1832$).

## Optimization & Taxonomy Analysis

- Method:
  1. Developed `tools/ec57/analyze_false_positives.py` to match detected peaks against 1-to-1 clustered manual references (150 ms tolerance).
  2. Classified each unmatched detection by temporal position, interval from preceding true QRS ($\Delta t$), window boundaries, and signal variance.
  3. Formulated structured comparison of three candidate architectural paths.

## Results: False Positive Breakdown (679 Total FP)

| Category | Count | Percentage | Primary Root Cause | Mitigation Mechanism |
|:---|---:|---:|:---|:---|
| **启动瞬态 (Startup Transient)** | **266** | **39.18%** | 记录前 1.0 秒（0~250 采样点）滤波器阶跃响应未稳定，且自适应噪声底未收敛 | 引入启动抑制期（500 ms ~ 1.0 s 缓冲），预填充前置样本或延后初次检测触发 |
| **基线漂移与低能量噪声 (Baseline Wander)** | **249** | **36.67%** | 固定 0.08 能量阈值在弱幅信号（<50 LSB）下过灵敏，基线漂移引起积分器虚警 | 增加带通前置截止阶数，引入绝对最小动态能量阈值与导联一致性能量门限 |
| **T 波/ST 段误检 (T-Wave Misdetection)** | **143** | **21.06%** | R 峰后 120~380 ms 高尖 T 波被积分器捕获 | 实施动态生理不应期与 T 波下降斜率衰减门限（$T_{\text{refr}} = f(\overline{RR})$） |
| **跨窗口边界重复 (Cross-Window Boundary)** | **20** | **2.95%** | 2.0 s SQI 窗口边界（480~520 点等）独立融合产生重合事件 | 窗口间重叠边缘聚类与去重（Inter-window boundary deduplication） |
| **重复/不应期穿透 (Duplicate Refractory)** | **1** | **0.15%** | 宽 QRS 复合波双峰检出 | 已由现有 200 ms 不应期基本抑制 |
| **高频肌电干扰 (EMG Noise)** | **0** | **0.00%** | 四阶带通滤波器已有效滤除高频噪声 | 现有 25 Hz 低通截止保持良好效果 |

> **关键发现**：启动瞬态 (39.2%) + 基线漂移 (36.7%) + T 波误检 (21.1%) 三类占全部假阳性的 **96.91%**（658 / 679）。

## 三条优化路线可行性对比

| 路线方案 | 核心技术手段 | 预期 QFP 削减 | FPGA 硬件代价 (GW2AR-18C) | 综合推荐等级 |
|:---|:---|:---|:---|:---:|
| **路线 1：传统 DSP/算法增强** | 1. 启动瞬态抑制（前 0.75s 保护）<br>2. 动态自适应能量门限（结合窗口 RMS）<br>3. T 波斜率抑制衰减窗<br>4. 跨窗口无缝融合去重 | 预计可消除 90~95% 假阳性（QFP 降至 $20 \sim 40$ 范围） | **极低**（增加若干移位与比较逻辑，0 额外乘法器/DSP，BSRAM 不变） | **★★★★★ (首选推荐)** |
| **路线 2：传统 QRS + 轻量级 Veto 判别器** | 在传统检出候选后，增加轻量 2~3 层 MLP/微型决策树（输入能量斜率、导联相关性、RR 差），对候选进行假阳性一票否决 | 预计可进一步将 QFP 压缩至 $\le 9$ 个（达成 $+P \ge 99.5\%$） | **低**（复用现有 NPU 乘加单元，耗费少量 LUT） | **★★★★☆ (路线 1 未达标时接续采用)** |
| **路线 3：端到端 ML 逐点 QRS 分割** | 采用 1D U-Net / Temporal CNN 进行全序列逐点 QRS 分割 | 理论性能上限高，但泛化性依赖大量跨库训练 | **极高**（模型参数与 MAC 激增 10x，无法在 GW2AR-18C 20K 预算内收敛） | **★☆☆☆☆ (不推荐)** |

## Decision

## Decision

- Decision: `reject`（回到训练）
- Reason: M1b 分析对象错误定位为浮点路径的 679 个 FP 而非定点部署路径的 578 个 FP；分类逻辑为粗粒度时间窗口启发式分桶，缺少导联投票、能量斜率、邻近 RR 间期、SQI 及形态波形片段的严谨证据；报告产物混放在 M1a 目录中且未建立独立 SHA-256 报告清单。本轮暂不接受，必须在 M1c 纯整数因果基线建立后重新开展双轨详细分类学分析。
- What changed in the project baseline: 形成了初步启发式假阳性分桶参考，但该分类结果不作为最终结论；保留路线 1（传统算法增强）为主选的演进假设。
- One primary question for the next run: 在 M1c 纯整数因果流式定点 QRS 实现后，定点与浮点路径在 200 条 LUDB 上的独立假阳性数分别为多少？各假阳性搏在波形与导联投票上的真实形态学根因为何？
