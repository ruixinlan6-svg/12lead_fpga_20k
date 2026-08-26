# Gowin GoAI/NPU 用于十二导联 ECG 的可用性与使用路线

> 状态：基于高云官方公开页面、本机 Gowin V1.9.12.03 NPU IP 和官方示例的规划结论。完整证据见 `datasheet/2026-08-26_Gowin-GoAI_十二导联ECG可用性.md`。尚未运行模型转换、综合、Flash 写入或板级推理。

## 结论

**可以保留为短门禁分支，但当前不能判定 Tang Nano 20K 实物可以使用。**

本机 `NPU 1.0` 的器件清单包含 `GW2AR-18C-QFN88P*`，官方 `mjb_npu` 示例和当前 EDA 工程选择的器件号也是 `GW2AR-LV18QN88PC8/I7`。但 Tang Nano 20K 原理图标注 `GW2AR-LV18-QN88C8/I7`：QN88P 集成 PSRAM，QN88 集成 SDR SDRAM。工程配置与官方示例只能证明 QN88P 路线存在，不能证明当前实物是 QN88P。

真正的门禁是：

1. 必须先用丝印、JTAG、EDA 和内存读写四项证据确认实物是 QN88 还是 QN88P；实物为 QN88 且厂商未提供 SDRAM 版本时，直接转自研 RTL；
2. 本机尚未发现 GoAI 模型转换 SDK/工具，只发现 EDA 内的 NPU IP 和参考工程；
3. 公开确认的计算算子只有 Conv2D、DepthwiseConv2D、MaxPool2D、AveragePool2D；
4. Conv1D、残差 Add、激活、全连接、GlobalAveragePool、Sigmoid 和具体量化语义仍需用转换器报告确认；
5. 官方示例是 MJB STD Board，虽然 EDA 器件号相同，但引脚、输入时钟、摄像头和显示接口不能复制到 Tang Nano 20K；
6. NPU 从 SPI Flash 读取权重/bias，而 Tang Nano 20K 的 QSPI Flash 也承担配置用途的可能性很高，必须先获得地址分区和镜像格式，防止覆盖 FPGA 配置。

推荐采用“GoAI 最小兼容性验证优先，自研 RTL 作为明确 fallback”，而不是立即把整个模型交给厂商工具或立即重写所有算子。

## 已确认的本机能力

| 能力 | 证据 | 结论 |
|---|---|---|
| EDA 目标器件 | `IDE/ipcore/NPU/npu.ipspec` 列出 `GW2AR-18C-QFN88P*` | QN88P 工程进入 NPU IP 支持范围；实物 QN88 不在该白名单 |
| 精确器件参考工程 | `IDE/data/examples/mjb_npu/mjb_npu.gprj` 为 `GW2AR-LV18QN88PC8/I7` | 可以作为 IP 例化、时钟和 AHB 结构参考 |
| NPU 计算单元 | 本机 `npu.html` 与[高云 NPU 官方页](https://www.gowinsemi.com/en/support/ip_detail/119/) | 确认 Conv2D、DepthwiseConv2D、MaxPool2D、AveragePool2D |
| 活动值存储 | NPU 官方说明和 `NPU_Top` 接口 | 前层/当前层临时数据位于 PSRAM |
| 权重存储 | NPU 官方说明和 `NPU_Top` 接口 | 权重和 bias 从 QSPI Flash 读取 |
| 控制面 | NPU 官方说明、示例顶层 | NPU 是 AHB slave，由 MCU 配置；示例使用 GOWIN_EMPU_M1 |
| 下载桥 | Programmer 内含 `DK-GoAI-GW2AR18_QN88P v1.1.fs` | 工具链包含面向该器件的 GoAI bridge，但用法和 Flash 布局仍需官方指南 |

本机证据根目录为：

```text
D:\software\Gowin\Gowin_V1.9.12.03_x64
```

## 算子支持边界

### 公开确认

- `Conv2D`
- `DepthwiseConv2D`
- `MaxPool2D`
- `AveragePool2D`

### 必须由 GoAI 3.0 转换报告确认

- Conv2D 的 kernel、stride、padding、dilation、channel 和 batch 限制；
- ReLU/ReLU6/clip 是否独立支持或只能与卷积融合；
- BatchNorm 是否由转换器折叠进 Conv2D；
- Add/残差、Concat、Reshape、Transpose；
- GlobalAveragePool、Dense、Sigmoid/Softmax；
- INT8 激活/权重是否支持 per-tensor 或 per-channel scale，zero-point、bias 位宽、舍入和饱和规则；
- 输入模型格式、受支持的 TensorFlow/TFLite/ONNX 版本；
- 生成的固件、权重镜像、Flash 地址表和 AHB 驱动接口。

任何没有出现在目标工具版本算子报告中的算子都按“不支持”处理，不能依据其他 NPU 或较新网页推断。

## Conv1D 到 Conv2D 的推荐映射

首轮 ECG 输入在训练框架中通常是 `[N, 12, 1000]`。为避免在 NPU 图内引入未确认的 Transpose，导出阶段直接生成 NHWC：

```text
Input:  [N, H=1, W=1000, C=12]
Kernel: [KH=1, KW=K, Cin, Cout]
Output: [N, H=1, Wout, Cout]
```

PyTorch `Conv1d(Cin, Cout, K)` 的权重 `[Cout, Cin, K]` 在导出时转换为 `[1, K, Cin, Cout]`。后续一维时序层都保持 `H=1`，沿 `W` 轴卷积或池化。

首个 GoAI 候选网络应遵守：

- 只使用 `1×K Conv2D`、`1×K DepthwiseConv2D`、`1×K Pool` 和 `1×1 Conv2D`；
- BatchNorm 在导出前折叠进卷积；
- 第一版不使用 residual Add、Attention、LSTM、LayerNorm、Concat 或动态 shape；
- 若全局池化不受支持，由 MCU 对最终短序列做平均；
- 分类头优先用 `1×1 Conv2D` 代替 Dense；
- Sigmoid 和五类阈值化先放在 MCU/PC，NPU 输出定点 logits；
- 所有 padding、layout、scale、zero-point、舍入和饱和规则写入量化契约。

这种结构牺牲了一部分模型自由度，但能把首轮兼容性问题限制在已经公开确认的四类算子附近。

## 建议其他 Agent 按此顺序挖掘

每一步都必须从 [迭代模板](../iterations/TEMPLATE.md) 创建新的 `run_id`，记录方法、原因、结果和决策。

### G0：补齐 GoAI 3.0 工具与官方合同

1. 先完成实物料号与内存类型四证据确认；若为 QN88，要求高云书面确认 QN88/SDRAM NPU 支持，否则本阶段直接结束并转自研 RTL。
2. 从[高云 GoAI 3.0 文档入口](https://gowinsemi.com/en/document/main/database/3343/?order=ASC&page=1&support_search=&type=version)取得与本机工具版本匹配的 SDK、用户指南、支持器件表和算子表。
3. 记录安装包版本、下载来源和 SHA-256，不把厂商受限安装包提交到公共仓库。
4. 确认模型输入格式、量化合同、生成文件、授权条件和命令行入口。

**通过条件：** 实物内存类型与 NPU IP 数据路径匹配，转换工具可调用，官方文档明确包含该精确器件/封装，且能导出可审计的算子支持报告。

### G1：只做四算子的最小模型

构建一个输入 `[1,1,1000,12]` 的 INT8 smoke model，仅含 `Conv2D(1×K)`、DepthwiseConv2D、MaxPool2D 和 AveragePool2D。固定少量人工 Golden 输入，比较训练框架、导出模型和 GoAI 仿真输出。

**交付物：** 模型图、转换日志、算子报告、量化参数、各节点输出、首个失配点和迭代记录。

**通过条件：** 不出现 CPU fallback/未知算子；定点输出满足提前冻结的逐元素规则。

### G2：移植 NPU 参考工程骨架

复制官方 `mjb_npu` 到新的 ECG 工程作为结构参考，只保留：

- NPU IP；
- GOWIN_EMPU_M1/AHB 控制路径；
- PSRAM、QSPI Flash、时钟复位和 UART 调试。

删除摄像头、DVI 和 MJB 板级约束。Tang Nano 20K 的 27 MHz 时钟、UART、QSPI 和其他引脚必须重新依据本板原理图定义；不得直接使用 `mjb_npu.cst`。

**通过条件：** 新工程器件号匹配、无 MJB 遗留引脚、综合无错误，且 NPU/PSRAM/Flash 初始化状态可由 UART 读取。

### G3：先审计 Flash，再写入权重

在任何 GoAI bridge 或权重下载前，取得以下事实：

- Tang Nano 20K QSPI Flash 的现有配置镜像范围；
- GoAI 权重/bias 镜像的起始地址、长度、对齐和校验；
- FPGA 配置、模型权重和其他数据的分区是否重叠；
- 备份与恢复方法。

**通过条件：** 形成书面 Flash 分区表，证明写入范围不覆盖配置和用户数据，并得到持久化写入授权。未通过时不得调用 bridge 或 Flash 编程。

### G4：替换为最小 ECG 候选

只有 G1-G3 通过后，才把 smoke model 替换为 PTB-XL 五超类的最小硬件候选。使用与软件整数参考相同的 Golden manifest，分别记录：

- macro-AUROC/F1 和逐类指标变化；
- GoAI 转换后的算子、权重和活动值容量；
- LUT/FF/BSRAM/DSP、Fmax；
- NPU 核心延迟与 UART 端到端延迟；
- 首个不一致层或板端失败样本。

## GoAI 与自研 RTL 的决策门禁

继续 GoAI 路线必须同时满足：

- 目标器件和当前 EDA/SDK 版本受支持；
- ECG 模型可以完全降低为受支持算子，或只有明确放在 MCU/PC 的轻量后处理；
- INT8 量化语义可冻结并与软件整数参考对齐；
- PSRAM 活动值、QSPI 权重和 AHB 控制路径可在 Tang Nano 20K 上安全使用；
- 转换、综合和板端结果可由公开仓库中的配置与记录复现。

出现以下任一情况时转向自研固定算子 RTL：

- Conv1D 等价图仍包含不支持算子或隐式 fallback；
- 量化/舍入规则无法导出或无法与训练侧一致；
- GoAI SDK/授权无法稳定获得；
- Flash 分区与 FPGA 配置冲突且没有安全方案；
- NPU 资源、带宽、延迟或精度不满足冻结门禁；
- 加密 IP 无法提供本研究所需的逐层可观测性。

转向 RTL 不是“GoAI 尝试失败后重新开始”，而是复用相同的输入、量化、Golden、Flash/PSRAM 和迭代记录合同。

## 官方来源

- [Gowin NPU IP 官方页](https://www.gowinsemi.com/en/support/ip_detail/119/)
- [IPUG800 NPU 用户指南](https://www.gowinsemi.com/upload/database_doc/2356/document/63085c571dde8.pdf)
- [RN800 NPU 发布说明](https://www.gowinsemi.com/upload/database_doc/2357/document/63085cb26caa3.pdf)
- [IPUG952 GoAI Acceleration IP 用户指南](https://www.gowinsemi.com/upload/database_doc/746/document/5d7ef57bcbebc.pdf)
- [Gowin GoAI 3.0 SDK/用户指南入口](https://gowinsemi.com/en/document/main/database/3343/?order=ASC&page=1&support_search=&type=version)
- 本机 Gowin V1.9.12.03 的 `IDE/ipcore/NPU/npu.ipspec`、`IDE/ipcore/NPU/doc/npu.html` 与 `IDE/data/examples/mjb_npu/`
