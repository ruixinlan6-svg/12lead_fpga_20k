# 12-Lead ECG on Tang Nano 20K

在 Sipeed Tang Nano 20K（Gowin GW2AR-18C）上研究十二导联 ECG 多标签模型的训练、INT8 量化、FPGA/NPU 部署和板级验证。

> 当前状态：QN88/SDRAM 路线已确认；EC57 混合架构的 M1 因果纯整数 QRS 开发基线已在 LUDB 1.0.1 的 200/200 条记录上正式验收，下一阶段是重新训练 M2 VEB 候选，旧 M2 候选保持撤销。板卡有可用串口：COM9/COM10 均枚举为 FT2232，其中 COM10 已实测接收 FPGA PIN69 的 UART；QN88 SDRAM 非破坏性 volatile smoke 和既有 TinyECGCNN 五 logits SRAM 实板闭环已有独立记录。项目不是医疗器械，LUDB 开发结果不代表通过 EC57、FDA 或临床验证。

## 首轮目标

- 数据：PTB-XL v1.0.3，100 Hz、10 秒、12 导联。
- 任务：NORM、MI、STTC、CD、HYP 五个诊断超类，多标签输出。
- 模型：只使用便于硬件映射的轻量 CNN 算子。
- 数值：FP32 基线 → 静态 INT8 PTQ → 精度门禁失败才进入 QAT。
- 部署：先验证 Gowin GoAI/NPU；不满足算子或数值要求时再进入自研 RTL。
- 验证：软件浮点、整数参考、RTL/厂商仿真和 SRAM 实板使用同一批 Golden 输入逐级对拍。

完整计划见 [十二导联 ECG FPGA 本地部署计划](docs/superpowers/plans/2026-08-26-ecg-fpga-closed-loop.md)。本轮实际结果按 [迭代索引](docs/iterations/INDEX.md) 追溯。

本次 QN88 SDRAM 首读为零的现象、复位排除、魔法端口根因和后续 RTL 修复见
[问题说明](docs/research/qn88-sdram-first-read-zero.md)。

## 已验证入口（2026-08-26）

- 全量 PTB-XL 异步下载器：[train/download_ptbxl_async.py](train/download_ptbxl_async.py)。数据保存在不进入 Git 的远端私有缓存；最终验收为 21,799 对 `records100/*_lr` 文件、0 个 `.part` 文件，manifest SHA-256 记录在 `20260826-1611-m1-ptbxl-record-parser-fix`。
- 完整 FP32 基线：远端 `runs/20260826-1613-m1-ptbxl-full-fp32-retry`，三 seed 测试 macro AUROC 为 0.8578–0.8624；checkpoint 仅保留在远端，不进 Git。
- 完整 checkpoint INT8 PTQ：远端 `runs/20260826-1634-m2-ptq-full-checkpoint/seed1`，验证集 AUROC 下降 0.00039；量化 contract 和 golden vectors 的哈希见对应迭代记录。
- 模型复现验证：`20260826-1908-m2-model-verify` 在同一完整 registry、seed1 checkpoint 和 2,048 条校准样本上重新生成 PTQ；metrics、量化 contract、INT8 权重和 4 个 Golden 数组与既有结果逐项/逐元素一致。该结果确认软件模型与量化产物可复现，但尚未验证模型级 QN88 FPGA 推理。
- 模型级 RTL 闭环：`20260826-2056-m3b-sync-bram` 完成同步 BRAM 重构，`20260827-0824-m3b-sram-download-retry` 恢复 QN88 SRAM 下载链路；随后 `20260827-1055-m4-model-full-hardware-closure` 在实板得到三次一致、与整数 Golden bit-exact 的五 logits `[32,-22,-21,-19,-21]`，并完成 27 MHz 时序闭合。该闭环属于既有 TinyECGCNN 演示模型，不等同于当前 EC57 混合架构的 M2 VEB 模型或最终监管验证。
- QN88 SDRAM 非破坏性探针：[fpga/sdram_probe/README.md](fpga/sdram_probe/README.md)。构建入口为 `fpga/sdram_probe/build_qn88.tcl`，只允许 SRAM 下载；当前接受构建在 COM10 稳定报告 `SD I1 P1 E0 C=19 D=0000 X=0000`。首读零、低位偏移、尾脉冲和突发状态泄漏均已按迭代记录闭合；`read_write_test_passed` 已更新为 true，但这仍不是长时保持或完整 ECG 模型流量证明。
- QN88 INT8 算术实板 smoke：[fpga/inference_smoke/README.md](fpga/inference_smoke/README.md)。它验证 8 项 INT8 点积 240、重定标结果 120，并已在 COM10 读取 `INFER D=00F0 Q=78 P=1`；这不等同于完整 ECG 模型准确率。

模型级 RTL 的可复用入口在 [fpga/model_full](fpga/model_full/) 和 [tools/model_full](tools/model_full/)：`ecg_integer_reference.py` 做 NumPy 整数参考，`tb_tiny_ecgcnn_full.sv` 做逐层对拍，`qn88_model_full_top.sv` 定义 `ECG0` + 输入/权重字节流、SDRAM 回读校验和五 logits UART 帧。硬件构建采用两步：先运行 `tools/model_full/build_core_synth.tcl` 生成 RAM/DSP 已映射的 `build_core/model_core_only/impl/gwsynthesis/model_core_only.vg`，再运行 `fpga/model_full/build_qn88_model_full.tcl` 完成顶层综合、布局布线和 bitstream。权重协议按 100 字节 SDRAM burst 分块；诊断镜像可用 HIL 的 `--wait-ack`，正式镜像应依照板端握手或足够长的块间暂停。完整结果见 [M3b 记录](docs/iterations/records/20260826-2056-m3b-sync-bram.md) 和 [下载重试记录](docs/iterations/records/20260827-0824-m3b-sram-download-retry.md)。

所有 `.fs` 仍只允许通过 SRAM 直接运行方式下载；使用 Gowin Programmer 时应选择 `GW2AR-18C`、`--run 2` 和 `--fsFile`，不要使用 Flash/`--run 44`。既有 TinyECGCNN 模型闭环已完成，但 EC57 混合架构必须重新从 M2 训练、量化和整数 Golden 开始，不能把旧模型的实板结果当成新模型验收。

后续 Agent 在任何训练、量化、RTL、综合或板测前，必须先为本轮创建新的 `docs/iterations/records/<run_id>.md` 并更新 `INDEX.md`；重试也必须使用新 ID。当前可用的机器可读状态通道为 COM10；JTAG “SRAM Program” 成功仍不能替代状态帧或 LED 观察。

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
