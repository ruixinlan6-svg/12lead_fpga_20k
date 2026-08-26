# Gowin GoAI/NPU 在十二导联 ECG 上的可用性与验证门禁

- 调研日期：2026-08-26
- 范围：只核对高云官方公开资料、本机已安装的高云官方 EDA 资料，以及 TensorFlow 官方格式规范；本轮不安装/运行 GoAI，不下载 GoAI 3.0 SDK，不连接或下载板卡。
- 标记：**[确认]** 为来源直接支持；**[推断]** 为基于确认事实作出的工程判断；**[未知]** 表示公开资料不足，必须由后续 Agent 获取文档或做最小实验确认。

## 结论先行

1. **Gowin NPU IP 公开明确支持的硬件算子只有 `DepthwiseConv2D`、`Conv2D`、`MaxPool2D`、`AveragePool2D`。** 旧版 GoAI Acceleration IP 文档还明确描述卷积后的可选 ReLU；全连接与 softmax 由处理器计算，不属于该加速器的数据通路。[Gowin NPU 官方页](https://www.gowinsemi.com/en/support/ip_detail/119/)、[IPUG800 NPU 用户指南](https://www.gowinsemi.com/upload/database_doc/2356/document/63085c571dde8.pdf)、[IPUG952 GoAI Acceleration IP 用户指南](https://www.gowinsemi.com/upload/database_doc/746/document/5d7ef57bcbebc.pdf)
2. **公开资料确认 NPU IP 支持 `GW2AR-18C QFN88P`，但没有确认标准 Tang Nano 20K 板卡。** 高云文档中的参考板芯片为 `GW2AR-LV18QN88PC8/I7`，而本地 Sipeed 原理图标注 `GW2AR-LV18-QN88C8/I7`：前者的 `P` 表示 PSRAM，后者集成 SDR SDRAM。因此，本机 EDA 中选择 QN88P 并生成工程不能证明当前实物板兼容。[RN800 NPU 发布说明](https://www.gowinsemi.com/upload/database_doc/2357/document/63085cb26caa3.pdf)
3. **将 ECG `Conv1D` 改写为高度为 1、卷积核为 `1×K` 的 `Conv2D` 在数学上等价，但尚不能据此宣布 GoAI 可用。** 官方资料没有公开矩形核、高度 1、量化细节及张量布局限制；旧版 IP 文档用单个 `CONV_KERNEL` 描述方形核，更需要以转换器实测为准。
4. **GoAI 3.0 已于 2026-01 发布 SDK 1.0E、用户指南 MUG1526 1.0E 和发布说明 MRN1526 1.0E，但正文下载需要高云账号。** 当前公开可访问页面只能确认这些交付物存在，不能确认 GoAI 3.0 的器件、算子、模型格式或量化兼容清单。[GoAI 3.0 官方文档目录](https://www.gowinsemi.com/en/document/main/database/3343/?order=ASC&page=1&support_search=&type=category)
5. **当前建议：先把 GoAI/NPU 作为一个短门禁分支，而不是主路径承诺。** 若实物确认为 QN88（SDRAM），且高云未提供 QN88 版本 NPU/可替换存储接口，则直接转向面向本板 SDRAM 的自研 INT8 RTL；若实物为 QN88P 或厂商明确支持当前板，再做 `1×K Conv2D` 最小兼容性实验。

## 1. 一手证据与版本边界

### 1.1 可公开访问的高云资料

| 资料 | 直接支持的事实 | 限制 |
|---|---|---|
| [Gowin NPU 官方页](https://www.gowinsemi.com/en/support/ip_detail/119/) | NPU 由 AHB、加速器、PSRAM 控制器、SPI Flash 控制器组成；列出四个算子 | 未给出精确张量、核尺寸、量化与资源约束 |
| [IPUG800-1.0E，NPU 用户指南](https://www.gowinsemi.com/upload/database_doc/2356/document/63085c571dde8.pdf) | 适用产品 `GW2AR-18C QFN88P`；参考板芯片 `GW2AR-LV18QN88PC8/I7`；端口和数据路径 | 2022-08-17 文档；对应 MJB/旧 NPU 流程，不是 GoAI 3.0 兼容说明 |
| [RN800-1.0E，NPU 发布说明](https://www.gowinsemi.com/upload/database_doc/2357/document/63085cb26caa3.pdf) | 设备 `GW2AR-18C QN88P`，AI 软件 `GoAI2.0_SDK`/`MJB_V1.0.0`，四个算子 | 未列出 GoAI 3.0 |
| [WP951-1.2E，GoAI 全栈白皮书](https://www.gowinsemi.com/upload/database_doc/2280/document/627018c3b0c0a.pdf) | GoAI 2.0 使用 TensorFlow/TensorFlow Lite；通过 TFLiteConverter/TOCO 生成量化 `.tflite` FlatBuffers，再由 SDK 解析 | 只证明 GoAI 2.0 流程，不代表 GoAI 3.0 或本板兼容 |
| [IPUG952-1.0E，旧 GoAI Acceleration IP](https://www.gowinsemi.com/upload/database_doc/746/document/5d7ef57bcbebc.pdf) | 支持 `GW2AR-18` 系列；卷积、ReLU、最大/平均池化；最终全连接/softmax 在处理器上做 | 2019 年旧 IP，与 2022 NPU IP/2026 GoAI 3.0 不能混为一个版本 |
| [GoAI 3.0 官方文档目录](https://www.gowinsemi.com/en/document/main/database/3343/?order=ASC&page=1&support_search=&type=category) | SDK 1.0E、MUG1526 1.0E、MRN1526 1.0E 的版本和发布日期 | 文档/SDK下载要求登录，正文尚未取得 |

### 1.2 本机高云官方安装包证据

本机安装的是 `D:\software\Gowin\Gowin_V1.9.12.03_x64`。以下文件可供后续 Agent 在不启动 EDA 的情况下复核：

- `IDE\ipcore\NPU\npu.ipspec`：NPU 1.0 的设备白名单为 `GW2AR-18C-QFN88P*` 和 `GW3ANRT-6A-*`。
- `IDE\ipcore\NPU\doc\npu.html`：重复确认四个算子与 AHB/PSRAM/SPI Flash 数据路径。
- `IDE\data\examples\mjb_npu\readme.txt`：参考工程目标为 `GW2AR-LV18QN88PC8/I7`。
- `IDE\data\examples\mjb_npu\mjb_npu.gprj`：工程器件同样是 `GW2AR-LV18QN88PC8/I7`，并包含 NPU、eMPU M1、相机输入和显示输出。
- `Programmer\bin\data\spi\gao_bridges\DK-GoAI-GW2AR18_QN88P v1.1.fs`：存在针对 DK-GoAI QN88P 的桥接比特流；它不是 Tang Nano 20K 兼容证明。
- 对 `D:\software\Gowin` 和常用用户文档目录的文件名检索未找到 GoAI 模型转换 SDK 或可执行文件；本机已有 NPU IP/参考工程不等于已经安装 GoAI 转换工具。

本机 NPU 计算模块主体为加密交付，无法从已安装 RTL 中可靠推出乘加位宽、舍入、饱和、零点或核尺寸上限。不得把反向猜测写入硬件契约。

## 2. 公开确认的算子、模型格式与存储路径

### 2.1 算子矩阵

| 运算 | NPU IP 公开状态 | ECG 使用建议 |
|---|---|---|
| `Conv2D` | **[确认]** | 用于尝试映射普通 `Conv1D`；`1×K` 参数能力仍未知 |
| `DepthwiseConv2D` | **[确认]** | 用于尝试映射 depthwise `Conv1D`；不要推断支持任意 grouped convolution |
| `MaxPool2D` | **[确认]** | 可尝试 `1×P` 时间池化；矩形窗口能力未知 |
| `AveragePool2D` | **[确认]** | 可尝试时间池化；超长全局池化核是否可接受未知 |
| ReLU | **[旧 IP 确认]** | IPUG952 明确可由控制位使能；仍需确认 NPU 1.0/GoAI 3.0 的融合规则 |
| Dense / Fully Connected | **[加速器未确认]** | 旧 IP 明确由处理器完成；首轮可在 MCU/PC 后处理 |
| Softmax / Sigmoid / 阈值 | **[加速器未确认]** | 放在 MCU/PC；多标签 ECG 应用 sigmoid，不能改成 softmax |
| Residual Add / `ADD` | **[未知]** | 不应进入 GoAI 首个候选模型；若主干必须残差，优先自研 RTL 或取得 GoAI 3.0 明确支持证据 |
| Global Average Pool | **[未单列]** | 只有 `AveragePool2D` 被列出；能否用全长窗口等价实现需实测 |
| BatchNorm | **[未知]** | 训练后先折叠入 Conv 权重/偏置，再导出；必须检查转换后的图中无独立 BN |
| Concat / reshape / transpose / pad / dilation | **[未知]** | 首个兼容模型避免；布局变换尽量在导出前消除 |
| Conv1D | **[未列出]** | 只能作为 `1×K Conv2D` 映射假设验证，不能直接宣称支持 |

注意：“TensorFlow Lite 标准支持某算子”不等于“GoAI NPU 支持该算子”。最终判断以目标版本 GoAI 转换器是否完整接管图、生成的层表以及硬件结果为准。

### 2.2 模型与量化格式

- **[确认，GoAI 2.0]** 官方白皮书描述的入口是 TensorFlow/TensorFlow Lite；最终模型由 TFLiteConverter 或 TOCO 转换并量化为 `.tflite` FlatBuffers，GoAI 2.0 SDK从中提取权重、偏置、层参数和模型函数。
- **[未知，GoAI 3.0]** 当前不能确认它是否仍仅接收 `.tflite`、是否增加 ONNX/PyTorch 入口、是否自动量化、是否只接受 PTQ，或支持哪些 TensorFlow/TFLite 版本。
- **[未知，Gowin NPU 1.0]** 公开 IP 文档没有给出输入/权重的有符号性、每张量/每通道 scale、zero-point、bias 位宽、累加位宽、舍入和饱和公式。
- [TensorFlow Lite 官方 INT8 规范](https://www.tensorflow.org/lite/performance/quantization_spec) 可作为待验证候选：激活一般为按张量 `int8`，Conv2D 权重通常为按输出通道 `int8` 且零点为 0，bias 为 `int32`。**这不是高云兼容性保证**；只有 GoAI 版本文档和转换结果完全一致后，才能写入本项目量化契约。

因此后续 Agent 不应直接把已有 ONNX INT8 模型送入 GoAI。安全顺序是：先取得 GoAI 3.0 文档并锁版本，再用极小 TensorFlow/Keras 模型导出全整型 TFLite，记录转换器实际接受的量化参数；若只能走 GoAI 2.0，则严格按该 SDK 的 TensorFlow/TFLite 版本重建模型入口。

### 2.3 官方 NPU 的内存与控制路径

```text
MCU / AHB master
  ├─ 通过 AHB 写入输入、模型参数和控制寄存器
  └─ 读取状态/最终计算数据
            │
            ▼
      Gowin NPU accelerator
        ├─ PSRAM：前一层/当前层中间特征，逐层读写
        └─ SPI Flash：当前层权重和偏置，计算时读取
```

IPUG800 的物理端口包括 16-bit PSRAM 数据、PSRAM 时钟/RWDS/片选、4-bit SPI Flash，以及 32-bit AHB 从接口。它不是“输入一个 TFLite 文件即可运行”的独立核：仍需要 AHB master/MCU 控制面、模型参数装载和板级存储连接。官方参考工程使用 eMPU M1；Tang Nano 20K 上的 BL616 与该 AHB 从口不存在公开的直接连接证明。

另一个未确认的硬门禁是 **SPI Flash 所有权和地址分区**。NPU 文档要求从 SPI Flash 读取权重/偏置，而 Tang Nano 20K 的 64-Mbit QSPI Flash 还用于保存 FPGA 配置。当前没有官方证据说明二者能否共用同一颗 Flash、NPU 权重起始地址和长度、配置区大小、用户数据区、启动后的管脚复用时序，以及 Gowin Programmer/权重下载器的擦除粒度。在这些事实冻结前，不得写入权重镜像，更不得假设“指定偏移写入”不会覆盖配置数据；即使后续允许持久化，也应先备份并校验配置镜像，首轮仍只允许 SRAM 下载。

## 3. GW2AR-18C / Tang Nano 20K 支持状态

| 对象 | 状态 | 证据与含义 |
|---|---|---|
| `GW2AR-18C QFN88P` 芯片/封装 | **公开确认支持 NPU IP** | IPUG800 和 RN800 均明确列出；本机 `npu.ipspec` 也列为支持 |
| `GW2AR-LV18QN88PC8/I7` | **公开参考设计已使用** | IPUG800 的 MJB V1.2 参考板与本机参考工程均使用该料号 |
| `GW2AR-LV18QN88C8/I7`（不带 P） | **未确认支持 NPU IP** | 本机 NPU 白名单不包含 QN88；DS226 表明 QN88 为 SDR SDRAM，QN88P 为 PSRAM |
| 标准 Sipeed Tang Nano 20K V1.3 | **未确认，现有资料指向不兼容** | 本地板卡数据手册写 64 Mbit SDRAM，本地原理图写 `GW2AR-LV18-QN88C8/I7`；官方 NPU 数据路径依赖 QN88P 的 PSRAM |
| 当前 `project/` 中的 `GW2AR-LV18QN88PC8/I7` 配置 | **只证明 EDA 配置，不证明实物** | 工程选择可能与板上芯片不一致，必须以丝印/JTAG/原理图/存储读写四项证据确认 |
| GoAI 3.0 对上述器件的支持 | **未知** | MUG1526/MRN1526 正文尚未取得，不能用 2022 NPU 支持表替代 2026 GoAI 3.0 支持表 |

关键本地资料：

- `datasheet/Sipeed Tang nano 20K Datasheet V1.3-en_US.pdf`：写明 `64Mbit SDRAM (SIP) + 64Mbit QSPI FLASH`。
- `datasheet/Tang_Nano_20K_3923_Schematics.pdf`：FPGA 标注为 `GW2AR-LV18-QN88C8/I7`。
- `datasheet/DS226-2.1_GW2AR系列FPGA产品数据手册.pdf`：表 2-2 明确 QN88 为 32-bit/64-Mbit SDR SDRAM，QN88P 为 16-bit/64-Mbit PSRAM，并说明后缀 `P` 表示 PSRAM。

**当前判断：** 若实物确为标准 QN88 Tang Nano 20K，则不能直接使用公开交付的 QN88P NPU IP。除非高云支持明确提供 QN88/SDRAM 版本或可替换存储控制器，否则自研 RTL 应成为板端主路线；仍可保留 GoAI 作为模型/量化可行性探索，但不能把 GoAI 生成物直接当作本板部署物。

## 4. `Conv1D → 1×K Conv2D` 映射分析

### 4.1 数学映射

原始 ECG 张量通常表示为 `[N, C, L]`，其中 `C=12`、首轮 `L=1000`。若走 TensorFlow/TFLite 常见的 channels-last Conv2D，可重排为：

```text
Conv1D 输入： [N, C_in, L]
Conv2D 输入： [N, H=1, W=L, C_in]     # NHWC
Conv1D 权重： [C_out, C_in, K]
TF Conv2D 核：[Hk=1, Wk=K, C_in, C_out]
步幅：       s  → (1, s)
膨胀：       d  → (1, d)
时间填充：   p  → 仅 W 方向填充；H 方向保持 0
```

TensorFlow 官方 Conv2D 定义的默认布局是 NHWC，kernel 是 `[filter_height, filter_width, in_channels, out_channels]`。[TensorFlow Conv2D 官方定义](https://www.tensorflow.org/api_docs/python/tf/nn/conv2d)

十二导联必须放在**通道维**。把输入排成 `[N, 12, L, 1]` 并用二维核跨越 12 个导联，会改变普通 Conv1D 的权重共享与通道求和语义，除非模型本来就设计成二维“导联×时间”卷积。

### 4.2 GoAI 可用所需条件

以下条件必须全部通过，才能接受该映射：

1. 转换器接受高度为 1 的输入和 `1×K` 矩形 Conv2D 核，不会将维度错误折叠或拒绝。
2. GoAI/NPU 支持实际模型用到的 `K`、stride、padding、输入/输出通道数；若使用 dilation 或 groups，也必须有明确支持证据。首个模型建议不使用 dilation 和任意 groups。
3. `DepthwiseConv1D` 只在转换后确实变成 `DepthwiseConv2D(1×K)`、depth multiplier 受支持时才可接受。
4. 转换后的图中只剩目标版本明确支持的 NPU 算子。BatchNorm 必须折叠；residual add、concat、transpose 等不能静默落到不存在的 CPU fallback。
5. 全整型量化的 scale、zero-point、bias、累加、requantize 舍入与 NPU 完全一致；逐层输出必须可导出并和整数 Golden 比较。
6. `1×P` 池化窗口以及全局平均池化所需的长窗口被支持；否则池化/分类头移到 MCU/PC，或改用已验证的分级小窗口池化。
7. 最终输入布局、导联顺序、mV/ADC 单位和零点在 `ecg_io_contract.json` 中冻结；转换前后抽样张量哈希一致。

### 4.3 对模型结构的建议

为了最大化 GoAI 短门禁通过率，首个候选应是**无残差的顺序 CNN**：

```text
Input [1, 1, 1000, 12]
  → Conv2D(1×K) + ReLU
  → MaxPool2D/AveragePool2D(1×P) 或已验证的 stride Conv2D
  → 若干 Conv2D/DepthwiseConv2D + ReLU
  → 输出短特征
  → MCU/PC 完成 flatten/global average、dense、sigmoid 和多标签阈值
```

这不是最终精度最优模型，只是转换器与 NPU 的探针。若研究模型必须使用 residual add、SE、attention、LayerNorm、dilated TCN 或任意 grouped convolution，不应为迁就未证实的 GoAI 能力而静默改模型语义；应转自研固定算子 RTL，或先取得 GoAI 3.0 的明确支持清单。

## 5. 后续 Agent 的最小兼容性验证计划（本轮不执行）

### Gate A：文档和器件锁定

1. 使用用户授权的高云账号取得 `MUG1526-1.0E`、`MRN1526-1.0E` 和 GoAI 3.0 SDK 1.0E；记录来源 URL、发布日期、文件 SHA-256 和 SDK 包 SHA-256。
2. 从两份文档逐项抄录：支持器件、主机系统、TensorFlow/TFLite/ONNX 版本、算子及参数限制、量化格式、输出文件、许可限制。
3. 通过实物丝印、JTAG ID、EDA 器件选择、内存读写四项证据确认是 QN88 还是 QN88P。任一证据矛盾时停止 NPU 路线。
4. 锁定 SPI Flash 芯片、容量、配置镜像占用范围、NPU 权重地址、擦除块大小、下载工具写入/整片擦除行为和启动后管脚所有权；未确认前禁止写权重或配置 Flash。

**交付物：** `docs/goai/goai_version_lock.md`、`docs/goai/operator_matrix.csv`、`docs/goai/flash_map.md`、`docs/preflight-report.md` 中的器件/内存章节。

### Gate B：转换器微模型矩阵

按从小到大只创建固定输入、batch=1 的微模型：

| 编号 | 模型 | 要回答的问题 |
|---|---|---|
| M0 | 单个普通 `Conv2D(1×3)` | 是否接受高度 1/矩形核/12 输入通道 |
| M1 | `Conv2D(1×3)+ReLU` | ReLU 是否融合、输出量化是否一致 |
| M2 | `DepthwiseConv2D(1×3)+Conv2D(1×1)` | depthwise 和 pointwise 的参数限制 |
| M3 | `MaxPool2D(1×2)` 与 `AveragePool2D(1×2)` | 矩形池化和边界舍入 |
| M4 | odd/even K、VALID/SAME、stride 1/2 | 长度、填充与输出 shape 规则 |
| M5 | 小型顺序 ECG trunk | 多层中间特征、参数/权重文件和控制表能否生成 |

每个模型都同时保存 FP32 TensorFlow、量化 TFLite、GoAI 层表/转换日志、固定输入、每层 TensorFlow/TFLite 输出及其 scale/zero-point。出现“算子落回 CPU”“忽略层”“自动改 shape”均判失败，不能仅凭转换进程退出码为 0 接受。

**交付物：** `goai/probes/`、`runs/<run_id>/goai_convert_report.json`、`runs/<run_id>/layer_compare.json`。

### Gate C：IP 集成与硬件门禁

仅在 Gate A/B 通过且器件/存储明确兼容后，才允许：

1. 生成目标器件 NPU IP 和最小 AHB 控制工程；先仿真 AHB、输入装载、PSRAM 特征往返和 SPI Flash 权重读取。
2. 依据 BlueStar 五级验证顺序做算子、逐层整数、顶层协议、综合/PnR、SRAM 实板测试；不得跳级。
3. 综合后核对真实资源、时序与 IP 许可状态；首次实板仅 SRAM 下载，不烧 Flash。

**交付物：** NPU/IP 版本清单、AHB 寄存器访问记录、逐层比对报告、综合/PnR 报告、SRAM 板测日志。若使用厂商加密 IP，必须记录其版本和生成参数，不能只保存生成后的网表。

## 6. GoAI 与自研 RTL 的决策门禁

```text
实物是否为 QN88P，或厂商是否书面确认 QN88/SDRAM 可用？
  ├─ 否 → 自研 INT8 RTL + 本板 SDRAM 控制器（主路线）
  └─ 是
      ↓
GoAI 目标版本是否明确支持器件、1×K/1×P、所需量化？
  ├─ 否 → 自研 RTL
  └─ 是
      ↓
微模型是否完整转换且逐层整数一致？
  ├─ 否 → 仅允许一次有明确原因的兼容结构调整；仍失败则自研 RTL
  └─ 是
      ↓
顺序 ECG trunk 是否满足量化精度、容量、资源和时序门禁？
  ├─ 否 → 依据失败证据回训练/量化；若是算子或架构限制则自研 RTL
  └─ 是 → 接受 GoAI 路线，进入 SRAM 实板闭环
```

### 立即可采用的分流规则

- **芯片/内存失败优先于模型实验。** 实物为 QN88 时，不应花大量时间把完整 ECG 模型适配到只公开支持 QN88P 的 NPU IP。
- **同一兼容问题最多做一个最小结构改写。** 例如 residual add 不支持，可另建一个无残差探针；不能连续改模型直到已不再是同一研究问题。
- **量化误差和工具不支持分开记录。** 前者回训练/量化，后者回架构/RTL，不把转换失败误写成精度失败。
- **自研 RTL 的首个算子集**应覆盖 `Conv1D/1×K MAC`、requantize/clip、ReLU、pool、residual add、global average、dense；按实物 QN88 的 64-Mbit SDRAM 重建存储契约，不复制 BlueStar Skill 中面向其他板卡的 PSRAM 参数。

## 7. 尚未确认、需要后续 Agent 挖掘的问题

1. MUG1526/MRN1526 中 GoAI 3.0 的目标器件表，是否包含 GW2AR-18C、QN88 或 QN88P。
2. GoAI 3.0 的真实模型入口：TensorFlow SavedModel、Keras、TFLite、ONNX 或其他格式；对应版本矩阵。
3. 完整算子及参数限制，尤其是矩形 kernel/pool、height=1、channels 上限、stride/padding/dilation/groups、activation fusion。
4. 精确量化语义：signed/unsigned、per-tensor/per-channel、zero-point、bias/accumulator 位宽、乘数/右移、舍入和饱和。
5. 生成物格式：FPGA bitstream/IP、权重/偏置镜像、层参数表、MCU 固件及逐层调试接口。
6. NPU 权重与 FPGA 配置是否共用 Tang Nano 的 QSPI Flash；若共用，安全分区、擦除和升级/回退方法是什么。
7. 加密 NPU IP 的许可是否允许当前教育版 EDA、当前板卡和计划中的公开仓库；不得把受限 SDK/IP 二进制提交到 GitHub。
8. 高云是否能提供 QN88 SDRAM 变体、可替换 PSRAM 控制器的 NPU 版本，或对 Tang Nano 20K 的正式参考设计。

## 8. 审核口径

后续 Agent 若声称“GoAI 支持十二导联 ECG”，审核时至少要求同时提供：精确 GoAI/EDA/IP 版本、实物料号与内存类型、转换后算子清单、量化参数清单、`1×K` 微模型日志、逐层整数对拍、资源/时序报告和 SRAM 板测证据。只展示 TensorFlow/TFLite 推理成功、EDA 工程能打开或 QN88P 参考工程存在，均不足以证明 Tang Nano 20K 上可部署。
