# 12-Lead ECG on Tang Nano 20K

在 Sipeed Tang Nano 20K（Gowin GW2AR-18C）上研究十二导联 ECG 多标签模型的训练、INT8 量化、FPGA/NPU 部署和板级验证。

> 当前状态：QN88 硬件路线已确认，正在建立 PTB-XL 训练与 INT8 RTL 闭环。项目不是医疗器械，公开数据集结果不能作为临床诊断声明。

## 首轮目标

- 数据：PTB-XL v1.0.3，100 Hz、10 秒、12 导联。
- 任务：NORM、MI、STTC、CD、HYP 五个诊断超类，多标签输出。
- 模型：只使用便于硬件映射的轻量 CNN 算子。
- 数值：FP32 基线 → 静态 INT8 PTQ → 精度门禁失败才进入 QAT。
- 部署：先验证 Gowin GoAI/NPU；不满足算子或数值要求时再进入自研 RTL。
- 验证：软件浮点、整数参考、RTL/厂商仿真和 SRAM 实板使用同一批 Golden 输入逐级对拍。

完整计划见 [十二导联 ECG FPGA 本地部署计划](docs/superpowers/plans/2026-08-26-ecg-fpga-closed-loop.md)。

## 强制迭代追溯

从现在开始，每一轮训练、量化、GoAI 转换、自研 RTL、综合和板测都必须分配唯一 `run_id`，并记录：

1. 上一轮基线和本轮要解决的问题；
2. 采用的优化手法；
3. 选择该手法的证据和原因；
4. 数据、代码、配置、环境和硬件版本；
5. 优化前后指标、资源、时序、延迟和失败样本；
6. 接受、拒绝、回退或继续实验的决定。

失败、中止和没有收益的实验也必须记录。旧记录不得覆盖，重试必须创建新 `run_id`。

- 规则：[迭代记录规范](docs/iterations/README.md)
- 索引：[迭代索引](docs/iterations/INDEX.md)
- 模板：[单轮记录模板](docs/iterations/TEMPLATE.md)

## Gowin GoAI/NPU 当前判断

本机 Gowin V1.9.12.03 已包含：

- NPU IP 1.0，目标器件列表明确含 `GW2AR-18C-QFN88P*`；
- 与当前工程器件号相同的 `GW2AR-LV18QN88PC8/I7` 官方 `mjb_npu` 示例；
- `DK-GoAI-GW2AR18_QN88P` Programmer bridge；
- Conv2D、DepthwiseConv2D、MaxPool2D、AveragePool2D 加速单元，以及 AHB、PSRAM 和 QSPI Flash 数据路径。

本轮已由用户确认实物封装为 **QN88**，板上外部存储按 **SDR SDRAM** 主路线处理；QN88P/PSRAM 资料仅保留为 GoAI 可行性对照，不能当作本板部署依据。因现有 GoAI/NPU 证据针对 QN88P/PSRAM，当前主路线是自研、可综合的 INT8 RTL；只有在额外证明 QN88/SDRAM 兼容后，才把 Conv1D 表示成高度为 1、卷积核为 `1×K` 的 Conv2D 做隔离实验。SDRAM 读写测试仍是独立门禁。

- 操作用法：[Gowin GoAI ECG 使用说明](docs/goai/GOWIN_GOAI_ECG_GUIDE.md)
- 一手证据：[GoAI/NPU 可用性与验证门禁](datasheet/2026-08-26_Gowin-GoAI_十二导联ECG可用性.md)

## 目录

```text
AGENTS.md                  后续 Agent 必须遵守的项目规则
docs/iterations/           每轮优化的索引、规范和模板
docs/goai/                 GoAI 可用性与使用路线
docs/superpowers/plans/    总体实施计划
datasheet/                 本地硬件资料与公开文献证据
project/                   已完成 PnR 的 Tang Nano 20K LED 工具链基线
train/                     后续训练、量化与模型导出实现
```

大体积数据、模型、运行结果、EDA 生成目录、比特流和厂商 PDF 不进入 Git。迭代记录只保存摘要、哈希和可定位路径。

## 后续 Agent 的开始顺序

1. 阅读 [AGENTS.md](AGENTS.md)。
2. 阅读总体计划、GoAI 说明和最新迭代记录。
3. 执行前从模板创建新的 `run_id` 记录，先写清优化原因和验收指标。
4. 只执行当前任务授权的阶段，不自动下载数据、占用 GPU、连接 JTAG 或烧录 Flash。
5. 执行后补齐结果与决策，并更新迭代索引后再提交代码。

远端仓库：[ruixinlan6-svg/12lead_fpga_20k](https://github.com/ruixinlan6-svg/12lead_fpga_20k)
