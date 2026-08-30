# 方案 B：双缓存乒乓与分层权重 DMA 流式加速架构指南

本文档记录了基于 **Sipeed Tang Nano 20K (Gowin GW2AR-LV18QN88C8/I7)** 实现的 **方案 B（双缓存乒乓特征图 + 分层权重 DMA 流式加载）** 硬件加速器的完整架构、内存映射、时序资源分析以及复现指引。后续任何 Agent 或开发者均可依据本文档一键上手与复现。

---

## 1. 架构动机与设计对比

在 Tang Nano 20K（GW2AR-18C，片上共 46 个 18 Kbit BSRAM，总容量 828 Kbit）上部署 12 导联 ECG 1D-CNN 时，存在两种部署策略：

| 特性 | 方案 A（全片上展开） | 方案 B（双缓存 + 分层 DMA 流式） |
| :--- | :--- | :--- |
| **特征图存储** | 每层独立分配 BRAM（Act1, Act2, Act3 等） | **Ping-Pong 双缓存交替复用（ActBuf_A / ActBuf_B）** |
| **权重存储** | 全层权重静态绑定在各层专用 BRAM | **统一存储区 + 8 KB WeightBuf 动态逐层 DMA 覆写** |
| **BSRAM 占用** | 36 / 46 (78%) | **28 / 46 (61%)** （**节约 8 个 BRAM，降低 22% 内存占用**） |
| **DSP 乘法器** | 24 / 24 (100%) | 24 / 24 (100%) |
| **模型扩展潜力** | 空间耗尽，无法塞入更深更宽模型 | **可直接支持 4x~8x 参数量的更深主干网络（ResNet1D/TCN）** |
| **时钟频率 ($F_{\max}$)** | 27.2 MHz | **27.819 MHz** (时序完全收敛，零负裕量) |
| **单次推理耗时** | ~280 ms | ~328 ms（含分层 DMA 微秒级搬运开销） |

---

## 2. 硬件模块与数据通路架构

### 2.1 模块层次结构

```
qn88_scheme_b_top.sv                     [顶层控制与通信状态机]
  ├── qn88_uart_byte_rx.sv               [115200 波特率字节接收器]
  ├── u_weight_storage (ecg_sync_dp_ram) [16 KB 片上动态参数暂存区 (14-bit ADDR)]
  ├── sdram_layer_dma.sv                 [分层权重 DMA 流式搬运状态机]
  ├── tiny_ecgcnn_stream_core.sv         [流式 1D-CNN 加速计算核]
  │     ├── act_buf_a (ecg_sync_dp_ram)  [16 KB 特征图双缓存 A]
  │     ├── act_buf_b (ecg_sync_dp_ram)  [16 KB 特征图双缓存 B]
  │     ├── weight_buf (ecg_sync_dp_ram) [8 KB 当前层动态权重缓存]
  │     ├── bias_mem [0:31]              [当前层偏置寄存器组]
  │     └── gap_mem  [0:31]              [全局平均池化结果寄存器组]
  ├── qn88_uart_frame_tx.v               [31 字节诊断帧 UART 发送器]
  └── qn88_sdram_controller              [Gowin SDRC_EMB 嵌入式 SDRAM 控制器 IP]
```

### 2.2 乒乓双缓存流水机制 (Ping-Pong Flow)

加速核内部仅保留两块 16 KB 的单时钟同步双口 Block RAM（`ActBuf_A` 和 `ActBuf_B`），各层计算在二者之间交替读写：

1. **输入加载阶段**：
   - 外部 UART 接收 12,000 字节（$12 \times 1000$ 导联心电波形），直接写入 `ActBuf_A`。
2. **Layer 1 (Conv1D 12->16, K=7 + ReLU1 + MaxPool 1000->500)**：
   - 输入读源：`ActBuf_A` ($12 \times 1000$)
   - 输出写目标：`ActBuf_B` ($16 \times 500 = 8000$ bytes)
3. **Layer 2 (Conv1D 16->32, K=7 + ReLU2 + MaxPool 500->250)**：
   - 输入读源：`ActBuf_B` ($16 \times 500$)
   - 输出写目标：`ActBuf_A` ($32 \times 250 = 8000$ bytes)
4. **Layer 3 (Conv1D 32->32, K=5 + ReLU3)**：
   - 输入读源：`ActBuf_A` ($32 \times 250$)
   - 输出写目标：`ActBuf_B` ($32 \times 250 = 8000$ bytes)
5. **Layer 4 (Global Average Pooling 32 ch x 250)**：
   - 输入读源：`ActBuf_B` ($32 \times 250$)
   - 输出写目标：片上分布式寄存器 `gap_mem[0:31]` (32 bytes)
6. **Layer 5 (Dense Head 32 -> 5 Logits)**：
   - 输入读源：`gap_mem[0:31]`
   - 输出写目标：分类寄存器 `out_l0..out_l4`，并格式化为 `ECG P1 S1 D1 L=20 EA EB ED EB` 发送给上位机。

---

## 3. 分层 DMA 地址映射表 (Memory Map)

`u_weight_storage` 共 16,384 字节（16 KB），参数基地址划分如下：

| 层名称 | 参数类型 | 元素维度 | 字节大小 | Storage 基地址 | WeightBuf 目标地址 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Layer 1** | Conv1D 权重 | $16 \times 12 \times 7$ | 1,344 B | `0` (`14'd0`) | `weight_buf[0..1343]` |
| | Conv1D 偏置 | $16$ | 16 B | `1344` (`14'd1344`) | `bias_mem[0..15]` |
| **Layer 2** | Conv1D 权重 | $32 \times 16 \times 7$ | 3,584 B | `1360` (`14'd1360`) | `weight_buf[0..3583]` |
| | Conv1D 偏置 | $32$ | 32 B | `4944` (`14'd4944`) | `bias_mem[0..31]` |
| **Layer 3** | Conv1D 权重 | $32 \times 32 \times 5$ | 5,120 B | `4976` (`14'd4976`) | `weight_buf[0..5119]` |
| | Conv1D 偏置 | $32$ | 32 B | `10096` (`14'd10096`) | `bias_mem[0..31]` |
| **Dense Head** | Linear 权重 | $5 \times 32$ | 160 B | `10128` (`14'd10128`) | `weight_buf[0..159]` |
| | Linear 偏置 | $5$ | 5 B | `10288` (`14'd10288`) | `bias_mem[0..4]` |
| **总计** | 全部模型参数 | — | **10,293 字节** | 占用 0 ~ 10292 | — |

---

## 4. 仿真与硬件验证操作指引

### 4.1 仿真测试（Icarus Verilog 快速回归）

1. **加速核逐层 Bit-Exact 验证**：
   ```powershell
   iverilog -g2012 -o sim_core.vvp tools/scheme_b/tb_scheme_b_core.sv fpga/scheme_b/tiny_ecgcnn_stream_core.sv fpga/scheme_b/sdram_layer_dma.sv fpga/model_full/ecg_sync_dp_ram.sv
   vvp sim_core.vvp
   ```
   *预期结果*：Pool1、Pool2、ReLU3、GAP、Logits 全部 0 mismatch，Pass。

2. **27 MHz 周期级端到端系统级仿真**：
   ```powershell
   iverilog -g2012 -o sim_top_27mhz.vvp tools/scheme_b/tb_scheme_b_top_27mhz.sv fpga/scheme_b/qn88_scheme_b_top.sv fpga/scheme_b/sdram_layer_dma.sv fpga/scheme_b/tiny_ecgcnn_stream_core.sv fpga/model_full/ecg_sync_dp_ram.sv fpga/model_full/qn88_uart_byte_rx.sv fpga/uart_probe/qn88_uart_frame_tx.v tools/scheme_b/sdram_ctrl_stub.v
   vvp sim_top_27mhz.vvp
   ```
   *预期结果*：`[PASS] 27MHz Top-Level Simulation Matches Golden Perfectly! Logits: [32, -22, -21, -19, -21]`。

### 4.2 Gowin EDA 命令行综合与比特流生成

```powershell
& "D:\software\Gowin\Gowin_V1.9.12.03_x64\IDE\bin\gw_sh.exe" tools/scheme_b/build_scheme_b.tcl
```
产物路径：`fpga/scheme_b/build/qn88_scheme_b/impl/pnr/qn88_scheme_b.fs`

### 4.3 烧录至 Tang Nano 20K (SRAM 模式)

```powershell
& "D:\software\Gowin\Gowin_V1.9.12.03_x64\Programmer\bin\programmer_cli.exe" --device GW2AR-18C --run 2 --fsFile "D:\project\gowin_project\0_fpga_test\test3\fpga\scheme_b\build\qn88_scheme_b\impl\pnr\qn88_scheme_b.fs"
```

### 4.4 硬件在环实测 (HIL)

```powershell
python tools/hil/qn88_model_full_test.py --run runs/20260826-1929-m2-input-quant-contract --port COM10 --burst-pause 0.002 --wait-done
```