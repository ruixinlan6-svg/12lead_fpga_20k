# 十二导联 ECG FPGA 本地部署 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `executing-plans` or `subagent-driven-development` to implement this plan milestone-by-milestone. Do not start execution from merely reading this document.

**Goal:** 在 Tang Nano 20K 上建立可复现的十二导联 ECG“训练—量化—FPGA 推理—板级测试—结果反馈”研究闭环。

**Architecture:** 远端 GPU 负责浮点基线、轻量学生模型和 INT8 量化；本地以共享的模型/量化/I/O 契约生成整数 Golden。先验证 GoAI/NPU 能否把 Conv1D 等价降为 `1×K Conv2D`；不支持时再采用面向固定算子集的自研 INT8 流水核。片上 BSRAM 做活动值与权重分块缓存，板载动态存储保存主要权重；首轮由 PC 通过 UART 送入样本并接收 logits，阈值化与报告在主机完成。

**Tech Stack:** PyTorch、ONNX、INT8 PTQ/QAT、WFDB/PhysioNet、Python、Verilog、Icarus Verilog、Gowin EDA V1.9.12.03、Tang Nano 20K（GW2AR-18C）。

---

## 1. 规划边界与当前事实

本文件只规划，不执行 SSH/JTAG 连接，不下载数据，不训练，不综合，不烧录。项目现已在 `ruixinlan6-svg/12lead_fpga_20k` 的 `main` 分支建立版本记录；数据、模型、日志、EDA 生成物、比特流、厂商 PDF 和本地连接配置不进入公共仓库。

公开文献、数据版本和许可的逐条证据见 `datasheet/2026-08-26_十二导联ECG文献与数据集证据.md`。

本地已有事实：

- `project/` 是可综合的 LED 板级基线，不是 NPU；报告证明 Gowin 工具曾在 `GW2AR-LV18QN88PC8/I7` 上完成 PnR，并生成 `.fs`，但不代表当前 JTAG 或板卡实时可用。
- `train/` 已有 PTB-XL 下载/登记、TinyECGCNN FP32 smoke 和静态 INT8 PTQ 参考脚本；完整基准仍待完整数据。
- `datasheet/REMOTE_LRX_AGENT_CONNECTION.md` 已给出安全的 GPU SSH 别名、远端 Python 和 GPU 使用边界，本计划不重复保存凭据。
- Tang Nano 20K 文档列出 20,736 LUT4、46 个 BSRAM（828 Kbit，约 103.5 KiB）、48 个 18x18 乘法器、64 Mbit 动态存储和 64 Mbit QSPI Flash。
- 用户已确认实物封装为 QN88；因此 QN88/SDR SDRAM 是主部署路线。仓库中的 QN88P/PSRAM 工程和 GoAI 资料只作历史/隔离实验参考，不能证明本板兼容；SDRAM 读写测试仍需独立通过。

难度判断为 **高但适合分阶段完成的研究原型**。真正的难点不是单次模型训练，而是患者级无泄漏划分、跨数据集标签映射、量化舍入一致性、长序列活动值/权重搬运、Gowin BSRAM/DSP 正确推断，以及软件—RTL—实板三端结果可追溯。现有调研中 `<20 ms`、微瓦级功耗等跨平台数字不作为本板目标；首轮先测量，再依据计算量、内存带宽和实际时钟设定优化目标。

## 2. 首轮需求定义与方案选择

### 推荐首轮任务

- 数据：PTB-XL 100 Hz 文件，固定 10 秒、12 导联。
- 任务：5 个诊断超类的多标签分类；使用官方建议的患者隔离 folds，训练/验证/测试划分写入清单并哈希。
- 模型：硬件友好的紧凑 1D-CNN/残差网络，只使用 Conv1D、加法、ReLU/clip、池化、全局平均池化、全连接和重定标。
- 数值：先复现 FP32，再做 INT8 PTQ；若量化门禁失败再做 QAT，不在首轮引入二值网络、Transformer 或知识蒸馏。
- 板端输出：FPGA 输出定点 logits；PC 完成 sigmoid/阈值和报告。独立运行与 BL616 后处理留在闭环稳定后。

首轮采用 100 Hz 的原因是 INT8 原始输入约 12 KiB；500 Hz 输入约 60 KiB，会在约 103.5 KiB 总 BSRAM 上显著挤压活动值缓存。500 Hz 和细粒度 SCP 标签是第二阶段扩展，不与首轮闭环并行推进。

### 方案比较

| 方案 | 优点 | 代价 | 结论 |
|---|---|---|---|
| GoAI/NPU：Conv1D 降为 `1×K Conv2D` | 复用厂商转换与 IP，工作量最小 | 公开页面未承诺 Conv1D，也需确认板卡/版本兼容 | **先做小型兼容性门禁** |
| 固定算子集的流式 1D-CNN NPU | 最容易做到比特精确，能按 48 个乘法器和有限 BSRAM 定制 | 换模型需要重新导出配置，通用性有限 | GoAI 门禁失败后的主路线 |
| 通用可编程 NPU/指令集 | 可承载更多网络 | 控制、编译器、验证和存储系统工作量显著增加 | 闭环稳定后再评估 |
| 激进二值/无乘法网络 | 可能节省 DSP/功耗 | 精度、论文可比性和训练稳定性风险较高 | 仅作后续研究分支 |

## 3. 核心公开基准与数据集下载计划（本轮不下载）

| 优先级 | 数据集 | 用途 | 计划中的使用方式 |
|---|---|---|---|
| P0 | PTB-XL | 主训练与内部基准 | 先取官方 100 Hz 版本，按患者隔离 folds 做 5 诊断超类多标签基线；保存版本、许可、文件哈希和划分清单 |
| P1 | Chapman-Shaoxing 12-lead ECG | 跨机构/设备外部验证 | 只在首轮闭环通过后下载；先建立标签本体映射，只报告可对齐标签，不把外部测试样本混入训练 |
| P1 | PhysioNet/CinC Challenge 2020 的公开 12 导联训练数据（含 CPSC 来源） | 跨域鲁棒性与更广标签验证 | 分来源保留，不先合并；记录各来源许可和标签体系，形成公共标签交集后再评估 |
| P2 | CODE-15% 或其他大规模公开/可申请 12 导联数据 | 规模化预训练与泛化研究 | 仅在 P0/P1 证明收益需求后评估访问条件、磁盘与训练成本 |

MIT-BIH Arrhythmia 是双导联、心搏级任务，不作为十二导联记录级首轮核心基准。MIMIC-IV-ECG 需要凭证/数据使用流程，也不作为自动下载项。

执行下载前必须先产出 `data_registry.yaml`，记录官方来源、版本、许可、预计容量、用途、患者级划分规则和校验和；数据本体不进入代码仓库。

## 4. 目标文件边界（执行阶段创建）

```text
contracts/                 模型 I/O、导联顺序、单位、预处理、量化与硬件契约
train/                     数据清单、训练/量化代码、配置和测试
fpga/rtl/                  INT8 算子、DMA/缓存、调度和顶层协议
fpga/tb/                   算子、逐层、顶层协议与整数 Golden 测试
tools/hil/                 UART 板测、日志解析和报告生成
runs/<run_id>/             每次闭环的不可变配置、指标、模型、报告和哈希
docs/research/             文献、数据集与硬件决策依据
```

保留现有 `project/` 作为板级工具链基线；ECG 工程验证通过前不在其上原地改造。

## 5. 闭环与交付节点

从 M1 开始，每一次训练、量化、GoAI、RTL、综合和板测尝试都先创建 `docs/iterations/records/<run_id>.md`，执行后记录优化结果、优化手法、选择原因、相对基线差值、失败样本和决策，并追加到 `docs/iterations/INDEX.md`。失败或没有收益的尝试同样保留，禁止用新结果覆盖旧记录。

```text
数据清单/患者划分
  → FP32 可复现基线
  → 部署约束模型
  → PTQ（失败才 QAT）
  → ONNX/整数 Golden
  → RTL 逐层比特精确
  → Gowin 综合/PnR
  → SRAM 实板批测
  → 浮点/量化/RTL/实板对比报告
  → 接受或回退到明确阶段
```

### M0：目标与工具预检

**交付物：** `contracts/hardware_contract.json`、`contracts/ecg_io_contract.json`、`docs/preflight-report.md`。

**内容：** 锁定导联顺序、输入单位、100 Hz 重采样、10 秒裁剪/补齐、标签集合、输出 logits；记录用户确认的 QN88 器件事实；把 SDRAM 读写测试作为后续独立硬件门禁；验证 GPU 身份和空闲卡；确认本地 `gw_sh.exe`、Programmer、Icarus 与串口。

**出口门禁：** 两份契约不再含歧义；QN88 事实有来源记录；活体连接证据带时间戳；不修改或占用他人 GPU 进程；SDRAM 未通过前不得宣称板级闭环完成。

### M1：可复现 FP32 基线

**交付物：** `data_registry.yaml`、患者级 split manifest、训练配置、FP32 checkpoint、ONNX、`metrics_fp32.json` 和复现报告。

**内容：** 复现 PTB-XL 5 超类任务；报告 macro/per-class AUROC、AUPRC、F1、敏感度/特异度和固定阈值；至少两个随机种子，空闲 GPU 以“一卡一候选”并行。

当前已先完成一个不用于论文/基准声明的有界样本 smoke run，用于验证 WFDB、标签、训练和后续整数向量链路；完整 M1 仍需完整数据或可信 bulk 镜像后再执行。

**出口门禁：** 无患者泄漏；相同配置可复跑；指标定义和阈值冻结；测试集未参与调参。

### M2：部署模型与 INT8 冻结

**交付物：** 模型复杂度/峰值活动值报告、`quantization_contract.json`、PTQ/QAT 模型、逐层整数 Golden、`metrics_int8.json`。

**内容：** 先依据板卡资源削减通道与层数，再 PTQ；只有 PTQ 相对 FP32 的 macro-AUROC 绝对下降超过 0.01、macro-F1 绝对下降超过 0.02，或任一关键类别的固定阈值敏感度下降超过 0.02，才进入 QAT。

**出口门禁：** 算子集可由计划中的 RTL 核覆盖；权重/活动值分块能落入确认后的存储层级；量化误差在门禁内；量化公式、舍入、饱和和字节序完全冻结。

### M3：NPU 基础内核与比特精确验证

**交付物：** GoAI 目标器件/算子支持报告；若厂商路径不通过，再交付 Conv1D MAC、requantize/clip、pool、residual add、global average pool、dense、动态存储 DMA/缓存 RTL，以及对应自检 testbench 和逐层对比报告。

**内容：** 先用最小模型验证 `1×K Conv2D` 转换、量化语义和目标器件支持；失败证据写入报告后才进入自研 RTL。自研路线先单算子，再多层核心，再顶层 UART/存储协议；适配 BlueStar 五级验证，但按 GW2AR-18 的 46 BSRAM、48 个 18x18 乘法器和实际存储类型重算 SIMD、Bank 和突发长度。

**出口门禁：** Level 1/2/3 全通过；所有部署测试向量与整数 Golden 逐元素一致；无 X/Z；首个失配点可自动定位。

### M4：综合、SRAM 上板与批量测试

**交付物：** Gowin 综合/PnR 报告、资源/时序/功耗估算、`.fs` 哈希、板端批测日志、`board_report.json`。

**内容：** 先综合核对 BSRAM/DSP 推断和时序，再仅下载 SRAM；用公开测试样本走 UART；分别测“纯推理延迟”和“含通信端到端延迟”。

**出口门禁：** 资源不超限、无时序违例；板端 logits/标签与整数参考一致；对完整保留测试集重新统计的指标满足 M2 量化门禁。Flash 持久化不属于此节点的自动动作。

### M5：结果反馈与下一轮决策

**交付物：** `runs/<run_id>/manifest.json`、`docs/iterations/records/<run_id>.md`、迭代索引更新、四端指标对比、失败样本索引、资源/延迟变化和最终决策。

**决策规则：** 浮点不足回 M1；量化掉点回 M2；仿真失配回 M3；时序/带宽/实板失配回 M3/M4。只有数值、指标、资源和时序同时通过，才接受本轮并讨论 500 Hz、更多标签、外部数据或独立运行。

## 6. 后续 Agent 的连接验证计划

以下命令只在获得执行任务后运行，并把输出脱敏保存到 preflight 报告。

### GPU

```powershell
ssh -G ecg-gpu-server
ssh ecg-gpu-server "cmd /c whoami"
ssh ecg-gpu-server "nvidia-smi --query-gpu=index,name,memory.used,memory.total,utilization.gpu --format=csv"
ssh ecg-gpu-server "nvidia-smi --query-compute-apps=gpu_uuid,pid,process_name,used_memory --format=csv"
```

预期身份为远端 `Administrator`；只允许使用当次检查确认空闲且项目允许的 GPU 0/1/2。独立候选分别绑定单卡，日志写入远端项目 `runs`；不停止、不暂停其他进程。

### FPGA

```powershell
python "$env:USERPROFILE\.cc-switch\skills\bluestar-fpga-skill\scripts\gowin_toolchain_runner.py" --scan
& 'D:\software\Gowin\Gowin_V1.9.12.03_x64\IDE\bin\gw_sh.exe' '.\build.tcl'
python .\download.py
```

第一条用于活体 JTAG/器件确认；后两条只能在对应工程目录、契约匹配且测试通过后运行。`download.py` 默认 SRAM 模式；不要向其传入 `flash/spi/rom`，直到用户明确批准持久化烧录。

## 7. 计划验收摘要

本计划覆盖了公开文献与数据集选择、GPU 多卡安全使用、FPGA/NPU 基础内核、训练—量化—部署—测试—反馈闭环以及交付物。仍需执行阶段在 M0 确认的关键事实只有：最终临床标签目标、实物 QN88/QN88P 与动态存储类型、实时 JTAG/SSH 状态，以及板端性能目标；这些事实不会被代理自行猜测。
