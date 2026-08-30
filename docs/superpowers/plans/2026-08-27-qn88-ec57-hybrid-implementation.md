# QN88 Twelve-Lead ECG EC57 Hybrid Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** 在 Sipeed Tang Nano 20K（`GW2AR-LV18QN88C8/I7`）上完成一个可追溯的十二导联 ECG 研究原型闭环：传统算法完成信号质量、导联选择、QRS、RR/心率；轻量 INT8 CNN 完成逐搏 `non-VEB/VEB` 分类；确定性状态机完成研究用途的心动过缓、心动过速、停搏候选、室早二联律/三联律、成对室早及室性连发事件。闭环必须覆盖训练、量化、整数参考、RTL、综合布局布线、SRAM 下载、COM10 实测、数据库评测和结果反馈。

**Architecture:** 采用“12 导联输入适配器 → 每导联定点滤波与 SQI → 最优导联/三导联 QRS 投票 → QRS/RR/HR → 主导联逐搏窗口与 RR 特征 → 约 1.6k 参数 INT8 CNN → 确定性节律状态机”的结构。首版模型权重、量化参数和窗口缓存全部放片上 BSRAM；QN88 的 SDR SDRAM 不作为首版推理正确性的依赖，只用于通过独立门禁后的长时回放/抓取。GoAI 的公开 QN88P/PSRAM 工程不用于本板，计算核采用自研 RTL 和同步 `SP/SDPB/DPB`/推断 BSRAM。

**Tech Stack:** Python 3.10、PyTorch、NumPy/SciPy、WFDB、标准库 `unittest`、Gowin EDA V1.9.12.03、SystemVerilog、Icarus Verilog（单元仿真）、QN88 SRAM 下载、COM10 115200 8-N-1、远端 Windows GPU 主机 SSH 别名 `ecg-gpu-server`。

---

## 0. 计划性质、基线与禁止事项

本文是派工和验收合同，当前步骤只创建计划，不授权下载数据、连接 GPU、启动训练、综合、下载 FPGA、写 SDRAM 或写 Flash。

已确认的硬件基线：

- FPGA：`GW2AR-LV18QN88C8/I7`，20,736 LUT4、46 个 BSRAM（828 Kbit）、48 个 18×18 乘法器。
- 时钟：板载输入 27 MHz；最终设计必须在该时钟下满足时序。
- 串口：COM10，115200，8-N-1，FPGA TX/RX 为 69/70 脚。
- 外存：QN88 的 64 Mbit SDR SDRAM 已通过短时非破坏性读写；长时间、复位首读和大流量仍需单独验证。
- 下载：首版及本计划所有板测只用 SRAM；未经用户再次明确授权不得写持久化 Flash。
- GoAI：公开 NPU 包面向 QN88P/PSRAM，不能作为当前 QN88/SDRAM 的可用部署路径。
- 现有 `contracts/ecg_io_contract.json` 和 `train/` 下 PTB-XL 五超类任务是 10 秒记录级分类，不能静默改写，也不能作为 EC57 QRS/VEB 模型。

首版明确不声明：AF/AFL、SVEB/PAC、VF、ST 事件、临床报警、诊断结论或 FDA 已通过。它只交付 EC57 风格的 QRS/VEB 申报前研究证据。扩展能力列在第 10 阶段，必须另立模型、数据和验收合同。

## 1. 首版冻结的输入、输出与算法边界

### 1.1 输入合同

| 项目 | 冻结值 |
|---|---|
| 采样率 | `250 Hz`；所有数据库在主机侧用有理数 polyphase 重采样到 250 Hz，事件时间戳先以秒表示再映射到目标采样点 |
| 导联数与顺序 | 12 路，严格为 `I, II, III, aVR, aVL, aVF, V1, V2, V3, V4, V5, V6` |
| 传输数值 | signed `int16` little-endian，研究接口规定 `1 LSB = 5 µV`；实际 ADC 必须由独立适配器转换到此接口 |
| 连续流 | 每个采样时刻携带 12 路、单调递增 `sample_index` 和 CRC；丢样、重复、乱序必须显式报错 |
| 支持状态 | 正常 12 导联、至少 1 路有效时的降级输出、0 路有效时 `SIGNAL_LOSS`；降级状态不得伪装成完整 12 导联结果 |

### 1.2 传统前端与 QRS 路径

- 形态/分类路径：0.5–40 Hz、4 阶 Butterworth SOS，系数按 250 Hz 设计后量化为 Q2.14，40-bit 累加、每个 SOS 级间饱和到 signed 24-bit，送模型前再按冻结 scale 转成 int8。
- QRS 路径：5–25 Hz、4 阶 Butterworth SOS，使用同一 Q2.14/40-bit 定点规则；随后使用 `[-1,-2,0,2,1]/8` 导数、平方、30 点（120 ms）移动积分、自适应信号/噪声阈值、50 点（200 ms）不应期和 `1.66 × 最近 8 个有效 RR 中位数` 搜索回补。
- SQI 窗口为 500 点（2 s）。首版无效条件冻结为：峰峰值 `<50 µV` 或标准差 `<10 µV` 的 flatline；连续 3 点到达 int16 轨或窗口内 `>=1%` 点到达轨的 saturation；窗口内 `>1%` 相邻差分绝对值 `>2 mV` 的 impulsive noise。其余有效导联按“有效 QRS 候选数、差分噪声比例、饱和比例”字典序排序；任何阈值修改必须新建 `run_id`。
- 选择 SQI 最高的 3 路有效导联；80 ms 内至少 2/3 路出现候选时，输出候选时间戳的中位数。只有 1 路有效时允许单导联输出，但必须置 `DEGRADED_ONE_LEAD`。
- QRS 输出时间戳是 R 峰位置，不是流水线结果到达时刻；允许且只允许一个在合同中冻结的固定流水线延迟补偿。
- RR 有效范围为 250–2000 ms；HR 使用最近 5 个有效 RR 的中位数计算 `60000/RR_ms`，每个 QRS 更新一次。3 s 没有有效 QRS 时 HR 置无效，禁止继续输出旧值。

### 1.3 逐搏模型合同

模型输入是 SQI 最高的主导联，不是 12 路并行 CNN。这一选择把多导联鲁棒性放在可审计的传统选导联/QRS 融合层，避免用主要为单/双导联的公开训练库伪造“十二导联神经网络已验证”。

| 项目 | 冻结值 |
|---|---|
| 波形窗口 | 160 点，R 峰位于索引 64；覆盖 `[-256 ms, +384 ms)` |
| 波形归一化 | 去除窗口中位数；以 train split 的 `|x-median|` 99.5 分位数（下限 100 µV）映射到 127，round-half-away-from-zero 后饱和到 signed int8 |
| 辅助特征 | 4 个：前一 RR/最近 8 RR 中位数、QRS 宽度、峰值/最近 8 搏峰值中位数、主导联 SQI；每项用 train split 的 median 和 IQR，按 `round(32×(x-median)/(IQR/2))` 量化并饱和到 int8；IQR 为 0 时构建阶段直接失败 |
| 输出 | 两个 logits：`[non_VEB, VEB]`；VEB 对应标准映射中的室性异位，未知/不可判定不强行映射为正常 |
| 延迟 | 从 R 峰到逐搏类别输出不超过 450 ms，其中固定后窗为 384 ms |

冻结的首版网络：

```text
Input 1x160
Conv1d 1->8, kernel=7, pad=3, ReLU, MaxPool2
Conv1d 8->16, kernel=5, pad=2, ReLU, MaxPool2
Conv1d 16->16, kernel=3, pad=1, ReLU, GlobalAveragePool
Concat 4 scalar features -> 20 values
Linear 20->2 logits
```

该网络含约 1,546 个带偏置参数，约 90,920 MAC/beat。禁止执行者在第一次基线训练前增加通道数、Transformer、LSTM、BatchNorm 或动态 shape；任何架构变化必须创建新 `run_id` 并重新过资源和量化门禁。

### 1.4 研究事件定义

这些定义是首版工程合同，不是医疗诊断阈值：

| 输出 | 冻结定义 |
|---|---|
| `BRADY_CANDIDATE` | 有效 HR `<50 bpm` 持续 10 s；HR `>=55 bpm` 持续 5 s 后清除 |
| `TACHY_CANDIDATE` | 有效 HR `>100 bpm` 持续 10 s；HR `<=95 bpm` 持续 5 s 后清除 |
| `ASYSTOLE_CANDIDATE` | 至少 1 路导联有效但 3.0 s 没有有效 QRS；下一有效 QRS 清除；无有效导联只能报 `SIGNAL_LOSS` |
| `PVC_COUPLET` | 连续恰好 2 个 VEB，在第 2 搏产生事件；第 3 个仍为 VEB 时升级为 run |
| `VENTRICULAR_RUN` | 连续 `>=3` 个 VEB；在第 3 搏开始，随后更新结束时间 |
| `VT_CANDIDATE` | 连续 `>=3` 个 VEB，且该 run 内 V-V 中位心率 `>=100 bpm` |
| `BIGEMINY_CANDIDATE` | `nonV,V` 交替且累计 3 个 V（6 搏）；连续 2 次模式违背后清除 |
| `TRIGEMINY_CANDIDATE` | `nonV,nonV,V` 重复且累计 3 个 V（9 搏）；连续 2 次模式违背后清除 |

## 2. 数据库清单、用途和隔离规则

### 2.1 首版必须准备的数据库

| 数据库 | 版本/规模 | 本计划唯一用途 | 进入训练/调参 | 进入锁定验收 | 关键门禁 |
|---|---|---|---:|---:|---|
| **Icentia11k Continuous ECG** | PhysioNet 1.0；11,000 人、250 Hz、单导联，约 27.74 亿已标注心搏 | 大规模 `nonV/V` 研究训练、增强和内部患者级验证 | 是，仅研究候选 | 否 | `CC BY-NC-SA 4.0`；商业/FDA 候选权重使用前必须取得书面许可/法律结论，否则研究模型不得晋级产品模型 |
| **LUDB** | 1.0.1；200 条 10 s、12 导联，500 Hz，心脏科医师标注 P/QRS/T 边界 | QRS 定位、12 导联顺序、重采样和导联选择开发测试 | 只用于传统 QRS 开发 | 否 | 样本太小且无足够逐搏 VEB 标签，不得用于宣称 VEB 性能 |
| **St Petersburg INCART** | 1.0.0；75×30 min、32 人、12 导联、257 Hz、>175k beats | 完整锁定的 12 导联补充外测；如需要整库板端回放，只能作为首次锁定评测的一部分 | 否 | 是，补充集 | 按患者分组；不得把同一患者记录拆到开发侧；时间点偶有偏差必须保留失败清单 |
| **MIT-BIH Arrhythmia DB** | 1.0.0；48×30 min、47 人、双导联、360 Hz | 锁定 QRS/VEB EC57 风格验证 | 否 | 是 | 不参与滤波、阈值、模型、PTQ、后处理选择 |
| **AHA Ventricular Arrhythmia DB** | 合法取得的完整受控版；双通道 250 Hz | 锁定 QRS/VEB/室性事件 EC57 风格验证 | 否 | 是 | PhysioNet 单条排除样例不算完整 AHA；未取得完整合法数据时不得签署“完整 EC57 风格验证通过” |
| **MIT-BIH Noise Stress Test DB** | 1.0.0；12 条 ECG 加 3 类噪声，SNR +24 至 -6 dB | 锁定抗噪 QRS/VEB 验证 | 否 | 是 | 派生自少量患者，只评价噪声鲁棒性，不代表十二导联人群外部验证 |

### 2.2 条件性数据库，不进入首版模型

| 数据库 | 何时加入 | 用途 | 明确禁止 |
|---|---|---|---|
| PTB-XL | 仅并行保留记录级五超类研究或做输入范围检查 | 12 导联幅度/顺序、记录级诊断研究 | 不得用其五超类 logits 证明 QRS、PVC、AF、VT/VF |
| MIT-BIH SVDB | 决定声明 SVEB/PAC 时 | SVEB 逐搏锁定验证 | 不替代 AHA/MIT 的 VEB 验证 |
| MIT-BIH AFDB + LTAFDB | 决定声明 AF/AFL 时 | AF episode/duration 与长时验证 | 未人工确认的 beat 注释不作 QRS/VEB 全库 gold standard |
| CUDB | 决定声明 VT/VF 危重事件时 | VT/VF episode、duration、延迟 | 不替代普通 VEB 逐搏验证 |
| European ST-T + Long-Term ST | 决定声明 ST 时 | ST 偏移与 episode/duration | 不进入首版节律模型 |

### 2.3 精确数据隔离

- Icentia11k 使用 `SHA-256(patient_id) mod 100` 划分：`0–79=train`、`80–89=validation`、`90–99=internal_test`；同一患者的全部片段只属于一个集合。
- 第一轮 smoke 只取各 split 中 SHA-256 最小的 20/5/5 名患者；完整研究候选使用所有合法可用患者。
- Icentia 标签：`V` 为正类；`N`、`S` 作为明确列名的 `non_VEB` 负类，其中 `S` 的支持数和误分类单独报告；`Q` 从损失和性能分母排除但必须统计数量。任何更改标签映射都新建合同版本。
- LUDB 只调传统 QRS/SQI，不进入 CNN 训练。
- INCART、MIT-BIH、AHA、NST 的原始目录权限设为只读；训练程序对这些根目录执行即报错。
- PTQ/QAT 校准集固定为 Icentia `train` 中 8,192 搏：4,096 V、4,096 nonV；按患者轮询取样，清单和 SHA-256 固化，不能从 validation/internal/锁定库取样。
- 一旦首次查看 MIT/AHA/NST/INCART 锁定结果并据此修改算法，这些库对新版本只能作为“已知回归集”；最终产品级外部验证必须增加未被查看过的独立患者级临床集。执行者不得反复试验锁定库直到过线。
- 数据清单必须保存数据库版本、许可证、患者/记录、原始文件 SHA-256、重采样器版本、排除理由、split 和 annotation 映射；任何遗漏样本都计入报告，不能静默删除。

### 2.4 下载与存储规划（本计划不执行）

- 远端训练根目录规划为 `C:\Users\Administrator\Desktop\LRX\12lead_ec57_qn88`，下设 `src`、`data`、`cache`、`runs`；不得覆盖已有 LRX 项目。
- Icentia11k 全量压缩包约 188 GB、解压约 1.1 TB；下载前验收远端目标盘可用空间 `>=1.5 TB`，否则只允许 smoke 子集，不得把子集结果标成“全量训练”。
- PhysioNet 公共数据固定版本下载；AHA 只从合法授权渠道取得。数据库文件、凭据和许可文件不提交公共 Git。
- 本地仓库只保存 `dataset_manifest.json`、split 列表、哈希、许可证摘要和评测输出，不保存受控 ECG 原始数据。

## 3. 全局数值验收标准

所有数值都是本项目预先冻结的内部候选门槛，不是 FDA 公布的统一最低线。正式申报还需 intended use、predicate、授权版 EC57 条款清单和 FDA Pre-Submission 确认。

### 3.1 QRS/VEB/HR 门槛

匹配规则：MIT-BIH、AHA、NST、INCART 的 EC57 风格锁定评测使用 WFDB `bxb` 标准模式、150 ms 匹配窗、每条记录开头 5 min 学习期；LUDB 记录只有 10 s，开发评测不排除学习期，并把各导联人工 QRS peak 的中位时间作为记录级参考。LUDB 医学门禁的有效标注区间为闭区间 `[首个参考 QRS - 150 ms, 末个参考 QRS + 150 ms]`，按精确时间边界换算、不得向外整采样点取整；完整 10 s 指标仍为强制诊断项，必须与门禁指标同时报告，不得隐藏区间外输出。每库分别给原始计数、逐记录、gross 和 average，禁止混库平均掩盖失败。

| 验证集 | QRS Se | QRS +P | VEB Se | VEB +P | VEB FPR |
|---|---:|---:|---:|---:|---:|
| Icentia internal_test（开发门禁） | `>=99.0%` | `>=99.0%` | `>=90.0%` | `>=95.0%` | `<=0.25%` |
| LUDB（仅 QRS） | `>=99.5%` | `>=99.5%` | 不适用 | 不适用 | 不适用 |
| INCART 12 导联补充锁定集 | `>=99.0%` | `>=99.0%` | `>=85.0%` | `>=90.0%` | `<=0.50%` |
| MIT-BIH 与完整 AHA，各库单独 | `>=99.5%` | `>=99.5%` | 每库 `>=85.0%`；另将每库 `>=90.0%` 列为非阻断竞争目标 | 每库 `>=95.0%` | 每库 `<=0.25%` |
| NST 全库 | `>=95.0%` | `>=85.0%` | `>=85.0%` | `>=85.0%` | `<=1.00%` |

附加硬门槛：

- 心率声明范围 30–220 bpm；逐次绝对误差不超过 `5 bpm`，同时报告 MAE、RMSE、最大误差、95% 误差区间和 WFDB normalized RMS error。
- NST 必须按噪声类型和每个 SNR 分层画曲线；全库过线不能替代分层结果。
- VEB FPR 固定按 `VFP/(VTN+VFP)`，另报告 `VFP/有效小时`，二者不得混用。
- 所有分母为 0 的指标报 `N/A`，不能写 0；漏输出、CRC 错误、超时、缓存溢出全部计为失败并列入清单。
- 95% 比例置信区间使用 Wilson 方法；患者级差异用 10,000 次 patient bootstrap，随机种子 `20260827`。

### 3.2 训练稳定性与模型规模

- 选定架构用随机种子 `17、29、43` 各训练一次；三次均须过 Icentia internal_test 数值门槛。
- 三个种子的 VEB Se 和 VEB +P 最大值与最小值差均 `<=2.0` 个百分点。
- 参数数 `<=2,048`，INT8 权重与 bias/scale 打包后 `<=8 KiB`，单搏 MAC `<=100,000`，最大单层激活 `<=2 KiB`。
- 不使用 validation/internal/锁定数据做过采样、归一化统计、早停后的阈值修补或失败样本微调。

### 3.3 量化和三方一致性

- 权重 signed int8、每输出通道对称量化；激活 signed int8、每层对称量化；bias/int accumulator 为 int32。
- requant 使用冻结的整数 multiplier/shift、round-half-away-from-zero、饱和到 `[-128,127]`；所有层均禁止浮点运行时运算。
- PTQ 相对 FP32：Icentia internal_test 的 QRS 指标必须完全不变；VEB Se、+P、FPR 任一绝对退化 `<=0.5` 个百分点；逐搏类别一致率 `>=99.9%`。
- 如果 PTQ 不过门，唯一允许的下一步是创建 QAT 新 run；不能放宽门槛或手改个别输出。
- 4,096 搏 core golden 上，整数 Python、RTL 仿真、QN88 实板的每层 int8 激活、两个 int32 logits 和最终类别必须 bit-exact。
- 流式 golden 上，QRS sample index、HR、SQI、lead_id、逐搏类别、事件起止必须 bit-exact；固定流水线延迟补偿后不允许逐记录移动时间戳。

### 3.4 QN88 资源、时序和板测

| 项目 | 计算核目标 | 完整系统硬门槛 |
|---|---:|---:|
| LUT4 | `<=8,000` | `<=16,000 / 20,736` |
| BSRAM | `<=12` | `<=32 / 46` |
| DSP/18×18 multiplier | `<=8` | `<=24 / 48` |
| 时钟 | 27 MHz | PnR worst slack `>=0.000 ns` |
| 持续输入 | 12×250=`3,000 samples/s` | 连续 2 h，丢样/重复/CRC/overflow 均为 0 |
| QRS 输出延迟 | `<=200 ms` | 逐搏分类 `<=450 ms`；HR 每搏更新 |

完整系统包含 UART、输入缓存、QRS/SQI、CNN、节律引擎和调试计数器。综合报告必须证明 BSRAM/DSP 被真实推断；RTL 仿真通过但资源退化成大量 LUT 不算通过。

## 4. M0：冻结合同、目录和可追溯机制

**交付节点：** `M0-contract-frozen`

**计划文件：**

- Create: `contracts/ec57_hybrid_io_contract.json`
- Create: `contracts/ec57_hybrid_metrics_contract.json`
- Create: `contracts/ec57_label_mapping_v1.json`
- Create: `docs/datasets/ec57_dataset_manifest.schema.json`
- Create: `docs/datasets/data_role_registry.csv`
- Create: `docs/datasets/contamination_log.csv`
- Create: `docs/datasets/locked_run_receipt.schema.json`
- Create: `train/ec57/README.md`
- Create: `tests/ec57/test_contracts.py`

**执行步骤：**

- [ ] 先从 `docs/iterations/TEMPLATE.md` 创建 `docs/iterations/records/<run_id>.md`，将输入/输出、数据隔离、模型规模和本节全部门槛写入“Frozen acceptance criteria”，再开始任何实现。
- [ ] 在新合同中写入 250 Hz、12 导联顺序、5 µV/LSB、160 点窗口、R 索引 64、四个辅助特征、输出枚举、状态机定义和版本号；不得修改旧的 PTB-XL 合同。
- [ ] 在 metrics 合同中逐项写入第 3 节门槛、150 ms 匹配窗、5 min 学习期、公式、置信区间和失败计数规则。
- [ ] 标签合同分别记录 Icentia 的训练映射和 WFDB/EC57 风格评测映射；正式评测映射需由合法标准正文复核并签名。
- [ ] 在 data role registry 中逐库写 `development/internal/locked`、允许/禁止用途、许可证和冻结日期；任何锁定库被误用于 golden、调参或板测调试时，必须登记并把角色降级，不能删除痕迹。
- [ ] 写测试拒绝：导联顺序错误、采样率不是 250 Hz、窗口不是 160、R 索引不是 64、锁定根目录出现在训练配置、指标分母为 0 时输出数值。
- [ ] 运行 `python -m unittest discover -s tests/ec57 -p "test_contracts.py" -v`，预期全部 `OK`。
- [ ] 更新 `docs/iterations/INDEX.md`，记录 M0 的 `run_id`、合同 SHA-256 和 `accept` 决定。

**验收成果：** 上述九个文件齐全；JSON 可解析；合同测试全部通过；旧 `contracts/ecg_io_contract.json` 未改；锁定门槛已经在看到任何新结果前提交。

## 5. M1：数据登记、泄漏防护和传统 QRS/HR 软件参考

**交付节点：** `M1-reference-accepted`

**计划文件：**

- Create: `train/ec57/build_registry.py`
- Create: `train/ec57/resample.py`
- Create: `train/ec57/sqi.py`
- Create: `train/ec57/qrs_detector.py`
- Create: `train/ec57/heart_rate.py`
- Create: `train/ec57/evaluate_qrs.py`
- Create: `tests/ec57/test_registry_no_leakage.py`
- Create: `tests/ec57/test_resample_timestamps.py`
- Create: `tests/ec57/test_qrs_reference.py`
- Create: `tests/ec57/test_heart_rate.py`

**执行步骤：**

- [ ] 先写失败测试：同一 patient 跨 split、锁定库进入 train/calibration、文件哈希缺失、annotation 重采样偏移超过 1 个目标 sample 时必须失败。
- [ ] 实现只读 registry；输入是本地/远端数据根目录，输出 `dataset_manifest.json`、`train_patients.txt`、`validation_patients.txt`、`internal_test_patients.txt` 和 `locked_records.txt`，不负责下载。
- [ ] 实现有理数 polyphase 重采样；事件使用绝对秒映射并保留原始/目标 sample index，往返时间误差 `<=2 ms`。
- [ ] 按第 1.2 节实现浮点参考 SQI/QRS/HR，再实现与硬件相同的定点参考；用合成脉冲、flatline、饱和、漏样、重复样和 lead dropout 建立最小回归。
- [ ] 在 LUDB 上仅调传统前端参数；通过后冻结滤波系数、SQI 阈值和 QRS 阈值，不查看 MIT/AHA/NST/INCART 结果。
- [ ] 运行 `python -m unittest discover -s tests/ec57 -p "test_*.py" -v`，预期泄漏负例被拒绝、时间误差和定点 golden 全部过线。
- [ ] 生成 `runs/<run_id>/reference_qrs/`，至少包含 config、manifest hash、LUDB per-record 双口径指标（有效标注区间门禁 + 完整 10 s 强制诊断）、失败样本和独立浮点/纯整数差异。

**验收成果：** 因果纯整数部署参考在 LUDB 有效标注区间上的 gross 与 average QRS Se/+P 均 `>=99.5%`，gross QFN/QFP 均 `<=9`；完整 10 s 原始计数和指标必须同时保留。独立浮点路径负责差异诊断，不要求与整数路径时间戳相等；bit-exact 责任链为整数 Golden → RTL → QN88 FPGA。重采样时间误差 `<=2 ms`；患者泄漏为 0；所有被排除样本有原因。

**未通过时：** 只回到滤波、SQI、QRS 或重采样；不得用锁定数据库调门槛，也不得进入 CNN 训练。

## 6. M2：远端 GPU 训练轻量 VEB 模型

**交付节点：** `M2-fp32-model-frozen`

**计划文件：**

- Create: `train/ec57/beat_dataset.py`
- Create: `train/ec57/model_nv.py`
- Create: `train/ec57/train_nv.py`
- Create: `train/ec57/evaluate_nv.py`
- Create: `train/ec57/configs/candidate_a_morph.json`
- Create: `train/ec57/configs/candidate_b_morph_rr.json`
- Create: `train/ec57/configs/candidate_c_morph_rr_aug.json`
- Create: `tools/remote/launch_ec57_candidates.ps1`
- Create: `tests/ec57/test_beat_windows.py`
- Create: `tests/ec57/test_model_budget.py`
- Create: `tests/ec57/test_metrics.py`

### 6.1 GPU 使用规则

执行者连接前按顺序运行以下只读检查；本计划不执行：

```powershell
ssh ecg-gpu-server "cmd /c whoami"
ssh ecg-gpu-server "nvidia-smi --query-gpu=index,name,memory.total,memory.used,utilization.gpu --format=csv"
ssh ecg-gpu-server "nvidia-smi pmon -c 1"
```

- 只使用检查时无他人计算进程、显存和利用率均近空闲的卡；允许的项目卡是 0、1、2，但每轮仍要重新检查。
- 小模型采用“一张空闲卡一个独立候选/seed”，不使用 DDP；空闲卡少于任务数时排队，禁止终止他人进程。
- 远端 Python 固定为 `C:\ProgramData\anaconda3\envs\lrx_train\python.exe`。
- 每个进程只写自己的 `runs/<run_id>`；同步回本地时带回配置、环境、stdout/stderr、manifest/split hash、模型/指标 SHA-256。

### 6.2 固定训练方案

| 候选 | 波形 | 四个特征 | 增强 | 损失 |
|---|---|---|---|---|
| A | 是 | 否 | 仅 gain | weighted cross-entropy |
| B | 是 | 是 | 仅 gain | weighted cross-entropy |
| C | 是 | 是 | gain + baseline wander + 12–30 dB Gaussian noise | weighted cross-entropy |

共同超参数：AdamW，lr `1e-3`，weight decay `1e-4`，batch `1024`，最多 50 epoch，validation VEB F1 早停 patience 8；每 epoch 正:负最多 `1:4`，每位患者每 epoch 最多 10,000 搏。增益均匀分布 0.8–1.2；baseline wander 为 0.05–0.5 Hz、峰值不超过 100 µV。除上述 3 个候选外，不允许临时扩大搜索空间。

**执行步骤：**

- [ ] 先写窗口边界、R 索引、患者隔离、类别映射、参数/MAC/激活预算的失败测试。
- [ ] 用 smoke 患者集对 A/B/C 各跑 1 epoch；要求 loss 有限、无 NaN、输出 shape `[batch,2]`、每个 run 产物完整。
- [ ] 在空闲 GPU 上并行运行 A/B/C，初始 seed 固定 17；只看 Icentia validation 选择候选。
- [ ] 候选排序为：先满足 VEB +P `>=95%` 与 FPR `<=0.25%`，再最大化 VEB Se，最后选择参数/MAC 更少者；禁止用 accuracy 或 AUROC 单独选型。
- [ ] 对胜出候选分别用 seed 17、29、43 全量训练；冻结每个 seed 的 checkpoint、阈值、归一化统计和 SHA-256。
- [ ] 每个候选在 validation 上把 VEB 概率阈值从 0.001 到 0.999、步长 0.001 扫描；先保留 `VEB +P>=95%` 且 `FPR<=0.25%` 的阈值，再选择 VEB Se 最高者；Se 相同则选择 +P 更高者，再相同则选择更接近 0.5 者。无满足阈值时该候选失败。
- [ ] 只在冻结后运行一次 Icentia internal_test；生成 per-patient 指标、混淆矩阵、Wilson CI、10,000 次患者 bootstrap 和全部 VFP/VFN 清单。
- [ ] 运行 `python -m unittest discover -s tests/ec57 -p "test_*.py" -v`，预期全部 `OK`。

**验收成果：** 三个 seed 全部满足第 3.1/3.2 节 Icentia 门槛；种子跨度 `<=2.0` 个百分点；参数、MAC、权重和激活均在预算内；无患者泄漏；完整模型包至少含 `model_fp32.pt`、`config.json`、`normalization.json`、`decision_threshold.json`、`metrics.json`、`manifest_sha256.txt`、`model_sha256.txt`。

**许可门禁：** 若 Icentia 的非商业许可未获得产品使用书面批准，则此节点只能标记 `research-only accept`，不能成为 FDA/商业候选。产品候选必须用权利清晰、患者隔离的开发数据重新训练并重新过 M2–M8。

## 7. M3：PTQ/QAT、整数 Golden 与节律状态机

**交付节点：** `M3-int8-bundle-accepted`

**计划文件：**

- Create: `train/ec57/quantize_int8.py`
- Create: `train/ec57/qat_nv.py`
- Create: `train/ec57/integer_reference.py`
- Create: `train/ec57/rhythm_engine.py`
- Create: `train/ec57/export_rtl_bundle.py`
- Create: `tools/ec57/generate_golden.py`
- Create: `tests/ec57/test_requantization.py`
- Create: `tests/ec57/test_integer_layers.py`
- Create: `tests/ec57/test_rhythm_engine.py`
- Create: `tests/ec57/test_export_bundle.py`

**执行步骤：**

- [ ] 先写 requant 边界测试：正/负半值、int32 极值、每层饱和、multiplier/shift 不可表示时必须失败。
- [ ] 用固定 8,192 搏 calibration manifest 做 PTQ；保存每通道 weight scale、每层 activation scale、bias、multiplier、shift 和量化误差。
- [ ] 在同一 Icentia internal_test 上比较 FP32/INT8；任何第 3.3 节门槛失败时创建 QAT 新 run，使用相同 data split、训练门槛和三 seed 规则。
- [ ] 实现与第 1.4 节完全一致的纯整数节律状态机；用边界序列验证 49/50/55 bpm、95/100/101 bpm、2.999/3.000 s、2/3/6 个连续 VEB、模式中断和 SIGNAL_LOSS。
- [ ] 生成 `core_golden_v1.npz`：4,096 搏，包含 int8 输入、四特征、每层输出、int32 logits、类别；生成 `stream_golden_v1/`：完整输入帧、QRS/HR/SQI/lead/event 输出。
- [ ] 导出 `weights_int8.bin`、`bias_int32.bin`、`requant.json`、`model_layout.json`、每文件 SHA-256 和总 `bundle_sha256`。
- [ ] 运行 `python -m unittest discover -s tests/ec57 -p "test_*.py" -v`，预期量化、状态机和 bundle 测试全部 `OK`。

**验收成果：** PTQ 或 QAT 满足全部精度退化门槛；整数参考无浮点运行时算子；状态机边界测试 100% 通过；4,096 搏每层 golden 和完整可哈希部署包齐全。

## 8. M4：RTL 单元、全网络与顶层协议

**交付节点：** `M4-rtl-bitexact`

**计划文件：**

- Create: `fpga/ec57_hybrid/ecg_sync_sp_ram.sv`
- Create: `fpga/ec57_hybrid/ecg_sync_dp_ram.sv`
- Create: `fpga/ec57_hybrid/ecg_biquad_timeshare.sv`
- Create: `fpga/ec57_hybrid/lead_sqi_select.sv`
- Create: `fpga/ec57_hybrid/qrs_detector_fixed.sv`
- Create: `fpga/ec57_hybrid/beat_window_buffer.sv`
- Create: `fpga/ec57_hybrid/nv_cnn_core.sv`
- Create: `fpga/ec57_hybrid/rhythm_engine.sv`
- Create: `fpga/ec57_hybrid/ec57_uart_protocol.sv`
- Create: `fpga/ec57_hybrid/qn88_ec57_hybrid_top.sv`
- Create: `fpga/ec57_hybrid/tb/tb_requant_mac.sv`
- Create: `fpga/ec57_hybrid/tb/tb_nv_cnn_core.sv`
- Create: `fpga/ec57_hybrid/tb/tb_qrs_detector_fixed.sv`
- Create: `fpga/ec57_hybrid/tb/tb_rhythm_engine.sv`
- Create: `fpga/ec57_hybrid/tb/tb_qn88_ec57_hybrid_top.sv`
- Create: `tools/ec57/run_rtl_regression.py`

**架构约束：**

- 12 路滤波器必须在 27 MHz 下时分复用乘法器，不为每路复制 DSP。
- 所有中间缓存和权重存储使用同步读模板或 Gowin `SP/SDPB/DPB`；RAM 数据路径不得在 reset 分支中全阵列清零，控制复位与 RAM 初始化分离。
- CNN 采用最多 8 lane 的定点 MAC，但 lane 数以资源报告为准，只能向下调整；不能复制 BlueStar Primer 25K 的 PSRAM 地址、32 KB cache 或资源参数。
- 顶层帧包含 magic、version、sequence、sample_index、payload length、CRC16；输出至少含 QRS、HR、lead_id、SQI、两个 logits、beat class、rhythm event、overflow/CRC/reset 计数。
- 所有 FIFO 满、窗口覆盖、丢包、非法序号和模型 bundle hash 不匹配都进入错误状态，不得静默丢弃。
- SRAM 调试 bitstream 可通过 UART 输出逐层激活以完成 4,096 搏 bit-exact 验收；发布 bitstream 关闭逐层 trace，仅保留 logits、事件和错误计数。两种 bitstream 均保存 SHA-256，调试版不得写 Flash。

**执行步骤：**

- [ ] 逐模块先写失败 testbench，再实现；顺序为 RAM → requant/MAC → 单层 Conv → pooling/GAP/head → 全 CNN → biquad/QRS → SQI/lead select → rhythm → protocol/top。
- [ ] 每个 CNN 层读取 M3 golden，首个不一致立即停止并输出 layer/channel/index/expected/actual。
- [ ] QRS/HR/SQI/状态机读取 stream golden，要求事件和时间戳 bit-exact。
- [ ] 全网络运行 4,096 搏 core golden，两个 logits、类别和所有中间层逐值一致。
- [ ] 顶层仿真注入 CRC 错、丢序号、重复帧、复位、FIFO 满、全导联 flatline；每个错误必须产生规定状态且不输出无标志诊断结果。
- [ ] 运行 `python tools/ec57/run_rtl_regression.py --golden runs/<run_id>/core_golden_v1.npz`，预期 `4096/4096 PASS, first_mismatch=none`。

**验收成果：** 所有单元 testbench 通过；全网络 4,096/4,096 搏 bit-exact；流式事件 bit-exact；负向协议测试 100% 产生预期错误状态；无异步数组读和 reset 全 RAM 清零模板。

## 9. M5：Gowin 综合/PnR、SRAM 下载与 COM10 实测

**交付节点：** `M5-qn88-sram-hil-accepted`

**计划文件：**

- Create: `fpga/ec57_hybrid/qn88_ec57_hybrid.gprj`
- Create: `fpga/ec57_hybrid/qn88_ec57_hybrid.cst`
- Create: `fpga/ec57_hybrid/qn88_ec57_hybrid.sdc`
- Create: `fpga/ec57_hybrid/build_qn88_ec57_hybrid.tcl`
- Create: `tools/ec57/qn88_hil.py`
- Create: `tools/ec57/compare_three_way.py`
- Create: `tests/ec57/test_hil_protocol.py`

**执行步骤：**

- [ ] 在新的工程目录引用 RTL，不改写 `project/` LED 基线；器件必须锁定 `GW2AR-LV18QN88C8/I7`。
- [ ] 综合后检查 LUT/BSRAM/DSP 层次报告；若同步缓存未进 BSRAM或资源超过第 3.4 节门槛，本 run 判失败并回 M4，不能仅凭 bitstream 生成宣称通过。
- [ ] PnR 后保存 utilization、timing、Fmax、worst path、Gowin 版本和 bitstream SHA-256；WNS 必须 `>=0.000 ns`。
- [ ] 只用 SRAM 下载；下载前确认 COM10 存在和板卡身份，下载后读取顶层版本、合同 hash、bundle hash、bitstream hash 的短标识。
- [ ] Core HIL 回放 4,096 搏，逐层/两个 logits/类别与整数参考 bit-exact。
- [ ] Streaming HIL 只用 development/internal 数据，禁止提前打开 INCART、MIT、AHA、NST。固定集为：LUDB 全部 200 条 10 s 记录；Icentia internal split 中患者哈希最小的 2 名患者、每人 segment 名最小的 1 个约 70 min 连续段，映射到 lead II 并将其余 11 路标为无效；另将 LUDB 全集循环回放至累计 12 导联输入满 2 h。生成的 `hil_stream_v1.json` 固化具体 record、循环次数和 SHA-256。
- [ ] 连续流累计有效输入至少 2 h；统计输入帧、输出事件、CRC、序号、overflow、reset、timeout，错误数必须全部为 0。
- [ ] 分别测量核心计算延迟、R 峰到 beat 输出延迟、主机串口传输延迟；不得用串口往返时间冒充核心推理时间。
- [ ] 运行 `python tools/ec57/compare_three_way.py --reference integer --rtl <rtl-output> --fpga <com10-output>`，预期 `qrs_mismatch=0, logit_mismatch=0, event_mismatch=0, transport_errors=0`。

**验收成果：** 完整系统资源和时序过门；SRAM 下载成功；4,096 搏 logits bit-exact；固定流式集 QRS/HR/SQI/事件 bit-exact；连续 2 h 无传输/缓存错误；所有报告和哈希归档。

### 9.1 SDRAM 独立支线门禁

首版推理不依赖 SDRAM。只有需要长时原始波形抓取/回放时才执行：

- [ ] 创建独立 `run_id`，先备份测试区域原内容，再测试、最后逐字恢复；不得影响推理权重和其他区域。
- [ ] 覆盖连续 1 MiB 区域，使用 address、walking-1/0、固定 0x00/0xFF/0x55/0xAA 和 LFSR 模式各 100 轮。
- [ ] 每轮包含控制器复位后的首次读、突发边界、跨行和 2 h 持续读写；总 mismatch、首读 mismatch、恢复 mismatch 均必须为 0。
- [ ] 未通过时禁用 SDRAM 抓取，但不否定片上 BSRAM 推理闭环；不得写 Flash。

## 10. M6：锁定数据库评测与十二导联系统验证

**交付节点：** `M6-ec57-style-prevalidation`

**计划文件：**

- Create: `tools/ec57/run_wfdb_evaluation.py`
- Create: `tools/ec57/export_test_annotations.py`
- Create: `tools/ec57/check_locked_evaluation.py`
- Create: `docs/reports/<run_id>/gross_average_summary.md`
- Create: `docs/reports/<run_id>/lead_robustness_report.md`
- Create: `docs/reports/<run_id>/board_equivalence_report.md`

**执行步骤：**

- [ ] 在运行前再次签署“模型、传统阈值、量化参数、状态机、匹配规则和全部门槛已冻结”；保存 Git commit 和所有 artifact hash。
- [ ] 对 MIT-BIH、完整 AHA、NST、INCART 各自运行，不将结果合并选模型；导出 WFDB test annotation 后用相同 `bxb` 流程计算。
- [ ] 对每库输出 QTP/QFN/QFP、VTP/VFN/VFP/VTN、有效心搏/小时、五项、逐记录、gross/average、CI、VFP/hour 和全部错误样本。
- [ ] 对 NST 按噪声类型/SNR 分层；对 INCART 以患者为单位报告并保留原始 12 导联配置。
- [ ] 做十二导联负向矩阵：逐导联 flatline、饱和、反相、交换、0.5×/2×增益、随机噪声；做 1/2/3/6/11/12 路失效；每个用例验证质量标志、lead switch、恢复、QRS/VEB 指标和是否拒绝输出。
- [ ] 负向用例硬门槛：正常输入三方 bit-exact；协议中的 lead_id/顺序错误 100% 拒绝；合成导联反相/交换检测敏感度 `>=95%`、正常输入特异度 `>=99%`，未达标则该版本不得声称支持自动导联反接检测；0 路有效时 100% 进入 `SIGNAL_LOSS`；不得保留超过 3 s 的旧 HR；丢包/overflow 未标记数为 0。
- [ ] 锁定数据库只运行冻结的整数软件评测，不用于 RTL/板端调试；板端实现等价性引用 M5 的 development/internal HIL，确认该回归集上 FPGA 与整数软件全部指标差值为 0。若法规策略要求锁定库整库板端回放，该回放必须作为首次 M6 评测的一部分一次性执行，失败也不得回头调试后伪装为未见验证。

**验收成果：** 第 3.1 节每库单独过门；AHA 为完整合法版；所有原始计数、失败样本、CI、分层和板端等价报告完整；十二导联退化行为符合合同。

**阻断结论：** 若没有完整 AHA，只能签署 `MIT/NST/INCART research prevalidation`，明确写“完整 AHA/EC57 风格验证未完成”；不得用 INCART、PTB-XL 或 AHA 样例替代。

## 11. M7：闭环反馈、追溯和版本晋级

**交付节点：** `M7-release-candidate-reviewed`

**计划文件：**

- Create/Update: `docs/iterations/records/<run_id>.md`
- Update: `docs/iterations/INDEX.md`
- Update: `README.md`
- Create: `releases/<version>/artifact_manifest.json`
- Create: `releases/<version>/acceptance_matrix.md`

每轮数据、训练、量化、RTL、综合、板测或外部评测都执行：

- [ ] 执行前写基线问题、证据、优化方法、选择原因、替代方案和冻结门槛；禁止看到结果后补写原因或降低门槛。
- [ ] 执行后写前后差值、所有失败样本、资源/时序/延迟、产物路径与 SHA-256、未验证项和 `accept/reject/rollback/continue`。
- [ ] 更新 INDEX；失败、无收益、中止和回滚也保留，旧记录不得覆盖。
- [ ] 发布包包含合同、数据 manifest、三 seed FP32、INT8 bundle、golden、RTL/Gowin 报告、bitstream、HIL 原始日志、数据库报告和许可证状态。
- [ ] README 明确区分“传统 QRS/HR”“ML VEB”“规则事件”“尚未验证能力”，并给出唯一复现实验入口。

**固定反馈路径：**

| 失败位置 | 唯一允许的回退方向 | 禁止做法 |
|---|---|---|
| M1 QRS/SQI | 重采样、滤波、SQI、QRS | 用 CNN 掩盖 QRS 漏检；偷看锁定集调阈值 |
| M2 FP32 | 数据质量、损失、增强、约 1.6k 参数架构 | 修改 internal_test；只报 accuracy |
| M3 PTQ | QAT 或量化尺度/整数实现 | 放宽 0.5pp 门槛；手改失败 logits |
| M4 RTL | 定点位宽、同步 RAM、控制/流水线 | 修改软件 golden 迎合 RTL |
| M5 资源/时序 | 时分复用、lane 数、BSRAM 映射 | 改目标器件/时钟后仍称同一基线 |
| M5 HIL | 协议、缓存、RTL、固定延迟 | 删除丢包样本；逐记录移动时间戳 |
| M6 锁定指标 | 创建新版本并把已看过库降为已知回归集；最终补新外部集 | 反复调锁定库并继续称其为独立验证 |

**最终验收成果：** `acceptance_matrix.md` 的 M0–M6 每项有证据链接、数值和签署结论；任何一项空白、无哈希、无失败样本或无 iteration record，版本不得标为完成。

## 12. M8：首版通过后才允许的能力扩展

扩展不与首版混做，每项先创建独立合同和 `run_id`：

| 扩展 | 训练/开发数据 | 锁定验证数据 | 研究候选门槛（非 FDA 门槛） |
|---|---|---|---|
| SVEB/PAC | 权利清晰的患者级开发集；Icentia `S` 仅可作研究预训练 | SVDB + MIT-BIH 未参与开发部分 + NST | SVEB Se/+P 各 `>=80%`，FPR `<=1%`，分库报告 |
| AF/AFL | 权利清晰的长时开发集；Icentia rhythm label 仅限许可允许范围 | AFDB + LTAFDB + 独立患者集 | episode Se/+P 各 `>=90%`，duration Se/+P 各 `>=95%`，FA `<=0.1/h`，延迟 `<=30 s` |
| VT/VF | 独立开发集，不使用 CUDB 调阈值 | CUDB + 完整 AHA 适用记录 + 独立危重事件集 | episode/duration Se/+P 各 `>=95%`，FA `<=0.1/h`，VF 延迟 `<=5 s`，全部漏检逐例审查 |
| ST | 独立 ST 开发集 | European ST-T + Long-Term ST | ST 偏移 RMSE `<=100 µV`，episode Se/+P 各 `>=85%`，FA `<=0.1/h` |

任何扩展加入后必须重新过 M0–M7、资源/时序、量化和 SRAM HIL；不得只在 Python 上增加标签后宣称 QN88 已支持。

## 13. 建议派工顺序和交付依赖

```text
M0 合同冻结
  -> M1 数据登记 + 传统 QRS/HR
  -> M2 GPU FP32 VEB
  -> M3 INT8 + 节律状态机 + Golden
  -> M4 RTL bit-exact
  -> M5 Gowin/PnR + SRAM/COM10
  -> M6 锁定数据库 + 十二导联退化
  -> M7 审核发布
  -> M8 单项扩展（可选）
```

可并行的只有：M1 的数据登记与合成 QRS 单测、M2 的独立 GPU 候选、M4 中彼此已有固定接口的 RTL 单元。M2 不能早于 M1 合同/窗口冻结，M4 不能早于 M3 bundle/golden，M6 不能早于模型和所有门槛冻结。

每个交付节点由实现 Agent 提交以下最小审查包：

1. 唯一 `run_id` 和对应 iteration record；
2. 实际执行命令、环境和 Git commit；
3. 固定输入 manifest/split/hash；
4. 原始日志、测试报告和失败样本；
5. 产物 SHA-256；
6. 数值验收矩阵；
7. 仅一个结论：`接受`、`回到训练`、`回到量化`、`回到 RTL/存储架构`。

## 14. 计划自检

- [ ] 需求覆盖：12 导联、传统算法/ML 分工、远端多空闲 GPU、训练→量化→部署→测试→反馈、QN88/SDRAM/BSRAM、SRAM/COM10、数据库与 FDA/EC57 边界均有明确阶段。
- [ ] 占位词扫描：除执行时必须生成的 `<run_id>`、`<version>` 和输出路径示例外，不含未决实现标记；所有首版门槛均有数值。
- [ ] 类型一致：采样率、导联顺序、窗口、单位、时间戳、int8/int32、rounding、label 映射和事件定义在软件、RTL、HIL、评测中一致。
- [ ] 证据边界：研究候选门槛未写成 FDA 统一门槛；AHA 缺失、Icentia 许可、锁定集被查看后的后果均有阻断规则。
- [ ] 硬件边界：器件是 QN88/SDRAM，不使用 QN88P GoAI；首版推理只依赖 BSRAM；Flash 未授权。

## 15. 依据

- `contracts/hardware_contract.json`
- `docs/research/2026-08-27_ANSI_AAMI_EC57_2012_QRS_VEB_指标与项目边界.md`
- `docs/research/2026-08-27_FDA_十二导联心律失常算法_指标与数据库验证矩阵.md`
- `docs/research/2026-08-27_QN88_EC57_训练与验证数据库隔离方案.md`
- `docs/goai/GOWIN_GOAI_ECG_GUIDE.md`
- `datasheet/2026-08-26_Gowin-GoAI_十二导联ECG可用性.md`
- [Icentia11k 官方页](https://physionet.org/content/icentia11k-continuous-ecg/1.0/)
- [LUDB 官方页](https://physionet.org/content/ludb/1.0.1/)
- [INCART 官方页](https://physionet.org/content/incartdb/1.0.0/)
- [MIT-BIH Arrhythmia 官方页](https://physionet.org/content/mitdb/1.0.0/)
- [MIT-BIH NST 官方页](https://physionet.org/content/nstdb/1.0.0/)
- [FDA Arrhythmia Detector and Alarm Class II Special Controls Guidance](https://www.fda.gov/medical-devices/guidance-documents-medical-devices-and-radiation-emitting-products/arrhythmia-detector-and-alarm-class-ii-special-controls-guidance-document-industry-and-fda-staff)
- [WFDB bxb](https://physionet.org/physiotools/wag/bxb-1.htm)
