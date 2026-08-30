# Twelve-Lead ECG QN88: FPGA Generic RTL Infrastructure Interface Assumptions

本文档记录 `fpga/ec57_hybrid/` 下通用 RTL 基础模块（单口 RAM、简单双口 RAM、定点 Requant MAC）的接口定义、位宽、时序延迟、读写冲突语义、数学舍入与饱和规则，以及后续在 M0 / M3 / M4 阶段与顶层和模型合同对接时必须核对的字段清单。

---

## 1. 模块清单与设计原则

| 模块名称 | 文件路径 | 定位与用途 |
|---|---|---|
| `ecg_sync_sp_ram` | `fpga/ec57_hybrid/ecg_sync_sp_ram.sv` | 参数化单端口同步 Block RAM，用于通用片上单端口缓存 |
| `ecg_sync_dp_ram` | `fpga/ec57_hybrid/ecg_sync_dp_ram.sv` | 参数化简单双端口同步 Block RAM (SDPB)，用于 CNN 层间特征与 FIFO/窗口缓存 |
| `ecg_requant_mac` | `fpga/ec57_hybrid/ecg_requant_mac.sv` | 参数化 32x32 乘累加量化缩放单元，支持 64-bit 乘积、对称最近舍入与 INT8 饱和 |

### 硬件推断铁律
1. **纯同步数据通路 (Data Path)**：RAM 的读写和数据寄存器均置于 `always @(posedge clk)` 纯同步时钟块中，不添加任何异步复位分支。
2. **禁止 RAM 阵列循环清零**：严禁在复位信号触发时使用 `for` 循环对 `mem` 阵列遍历清零，防止 GowinSynthesis 触发 `EX3934` 警告并推断为 45,000+ 分布式 LUT 寄存器。
3. **控制复位分离**：RAM 包装器保留 `rst_n` 作为接口兼容端口，但数据通路故意不引用它；调用者在复位期间必须拉低 `en/wr_en/rd_en`。Requant 的 valid/输出寄存器使用 `rst_n` 复位。
4. **属性约束**：RAM 阵列显式标注 `(* ram_style = "block" *)`，用于请求 GowinSynthesis 优先推断 BSRAM。实际是否映射到 GW2AR-18C BSRAM 必须以后续综合层次报告为准，本轮 Icarus 仿真不构成映射证据。

---

## 2. 单端口同步 RAM (`ecg_sync_sp_ram`)

### 2.1 端口与参数

```systemverilog
module ecg_sync_sp_ram #(
    parameter int DATA_WIDTH = 8,
    parameter int DEPTH      = 256,
    parameter int ADDR_WIDTH = (DEPTH > 1) ? $clog2(DEPTH) : 1
)(
    input  wire                  clk,
    input  wire                  rst_n,   // 兼容端口；数据通路故意不使用
    input  wire                  en,      // 芯片使能 (Chip Enable)
    input  wire                  we,      // 写使能 (1 = Write, 0 = Read)
    input  wire [ADDR_WIDTH-1:0] addr,    // 读写复用地址
    input  wire [DATA_WIDTH-1:0] din,     // 写入数据
    output reg  [DATA_WIDTH-1:0] dout     // 读出数据 (固定 1 拍延迟)
);
```

### 2.2 时序与语义契约
- **时钟沿**：全部操作在 `clk` 上升沿（`posedge clk`）同步采样。
- **读延迟**：固定 **1 个时钟周期**。当 `en=1` 时，周期 $T$ 采样 `addr`，周期 $T+1$ 采样后 `dout` 输出有效数据。
- **冲突语义（Read-First / Read-Before-Write）**：
  当 `en=1` 且 `we=1` 时，非阻塞赋值调度规则确保 `dout` 获取的是该地址在**被写入前的旧数据（Old Data）**，新数据 `din` 在该周期结束时写入 `mem[addr]`。在后续周期读该地址即可获得更新后的新数据。
- **使能保持**：当 `en=0` 时，内部存储器不发生写操作，`dout` 保持上一拍输出值不变。
- **复位责任**：调用者必须在 `rst_n=0` 时令 `en=0`。模块不复位 `mem` 或 `dout`，因此复位释放后的第一个合法读事务仍按一拍同步读规则返回已存数据。

---

## 3. 简单双端口同步 RAM (`ecg_sync_dp_ram`)

### 3.1 端口与参数

```systemverilog
module ecg_sync_dp_ram #(
    parameter int DATA_WIDTH = 8,
    parameter int DEPTH      = 256,
    parameter int ADDR_WIDTH = (DEPTH > 1) ? $clog2(DEPTH) : 1
)(
    input  wire                  clk,
    input  wire                  rst_n,    // 兼容端口；数据通路故意不使用
    
    // 写端口 (Write Port)
    input  wire                  wr_en,    // 写使能
    input  wire [ADDR_WIDTH-1:0] wr_addr,  // 写地址
    input  wire [DATA_WIDTH-1:0] wr_data,  // 写数据
    
    // 读端口 (Read Port)
    input  wire                  rd_en,    // 读使能
    input  wire [ADDR_WIDTH-1:0] rd_addr,  // 读地址
    output reg  [DATA_WIDTH-1:0] rd_data   // 读数据 (固定 1 拍延迟)
);
```

### 3.2 时序与语义契约
- **独立读写端口**：写端口与读端口具有独立使能信号与地址总线，支持同周期并发读写。
- **读延迟**：固定 **1 个时钟周期**。周期 $T$ 采样 `rd_en=1` 及 `rd_addr`，周期 $T+1$ 产生对应的 `rd_data`。
- **同址冲突语义（Read-First Collision）**：
  当前 RTL 行为模型规定：当 `wr_addr == rd_addr` 且 `wr_en=1` 与 `rd_en=1` 同沿发生时，`rd_data` 输出写入前的**旧数据（Old Data）**。在完成 Gowin 综合报告和映射后/原语仿真确认前，顶层不得依赖跨端口同址冲突结果；若必须依赖，应显式实例化并配置 Gowin 原语或增加 forwarding。
- **硬件映射**：目标是推断为 `SDPB`，但实际映射状态属于后续 Gowin 综合门禁，本轮未验证。
- **复位责任**：调用者必须在 `rst_n=0` 时令 `wr_en=rd_en=0`；模块不复位 `mem` 或 `rd_data`。

---

## 4. 定点 Requant MAC 模块 (`ecg_requant_mac`)

### 4.1 端口与参数

```systemverilog
module ecg_requant_mac #(
    parameter int ACC_WIDTH   = 32, // 累加器输入位宽 (signed int32)
    parameter int MULT_WIDTH  = 32, // 量化乘数位宽 (signed int32)
    parameter int OUT_WIDTH   = 8,  // 输出激活位宽 (signed int8)
    parameter int SHIFT_WIDTH = 5   // 右移位数位宽 (0..31)
)(
    input  wire                          clk,
    input  wire                          rst_n,      // 异步复位/同步释放 (复位流水线状态)
    input  wire                          in_valid,   // 输入有效指示 (高电平有效)
    input  wire signed [ACC_WIDTH-1:0]   in_acc,     // Signed 32-bit 累加和 (含 bias)
    input  wire signed [MULT_WIDTH-1:0]  in_mult,    // Signed 32-bit 量化乘数 (multiplier)
    input  wire        [SHIFT_WIDTH-1:0] in_shift,   // 5-bit 算术右移位数 (0..31)
    input  wire                          relu_en,    // 1 = 启用 ReLU 激活, 0 = 线性直通
    output reg                           out_valid,  // 输入采样沿 E0 -> 输出注册沿 E1
    output reg  signed [OUT_WIDTH-1:0]   out_data    // 饱和到 signed int8 的输出值 [-128, +127]
);
```

### 4.2 流水线与延迟
- **流水线深度**：两个寄存阶段。若输入在上升沿 `E0` 被采样，则 `E0` 后 `out_valid=0`（不存在前序请求时），结果在下一上升沿 `E1` 注册到 `out_data` 且 `out_valid=1`；空泡在 `E2` 传播到输出。这等于从接受沿到结果沿相隔一个完整时钟周期。若控制器在某个上升沿之后才驱动输入，则需要等待随后两个上升沿。
  - **Stage 1 / E0**：有符号乘法器计算 64-bit 乘积 `stage1_prod <= in_acc * in_mult`，并锁存 `shift`、`relu_en` 与 `valid`。
  - **Stage 2 / E1**：组合逻辑完成舍入、右移、饱和与可选 ReLU，随后注册到 `out_data/out_valid`。
- **流水线吞吐量**：当连续输入 `in_valid=1` 时，每个时钟周期可持续输出 1 个 `out_data` (1 Sample / Cycle Throughput)。
- **ReLU 范围**：`relu_en` 是为首版 CNN 的 Conv-ReLU 融合预留的暂定接口扩展；M3 整数参考必须明确接受相同语义，否则顶层应固定拉低或将 ReLU 拆成独立模块。

### 4.3 数学计算与舍入规范

1. **中间乘积 (64-bit Signed Full Precision Product)**：
   $$\text{prod} = \text{in\_acc} \times \text{in\_mult}$$
   - 取值范围：$[-2^{62}, +2^{62}]$，绝不溢出 64-bit 有符号整数范围。

2. **对称四舍五入远离零 (Round-Half-Away-From-Zero)**：
   为避免向负无穷截断产生的系统性直流偏置，针对移位数 $S \in [0, 31]$，定义舍入偏置项 $\text{round\_term}$：
   $$\text{round\_term} = \begin{cases} 0, & \text{if } S = 0 \\ 2^{S-1}, & \text{if } S > 0 \text{ and } \text{prod} \ge 0 \\ 2^{S-1} - 1, & \text{if } S > 0 \text{ and } \text{prod} < 0 \end{cases}$$
   $$\text{scaled\_val} = (\text{prod} + \text{round\_term}) \ggg S$$
   *注：在补码算术右移中，负数加 $2^{S-1}-1$ 后右移 $S$ 位，在数学上严格等价于向远离零方向舍入（例如 $-0.5 \to -1, -1.5 \to -2, -0.499 \to 0$）。*

3. **动态饱和截断与 ReLU (Dynamic Clamping & ReLU)**：
   针对输出位宽 $W = \text{OUT\_WIDTH} = 8$：
   $$\text{MAX\_VAL} = +127 \quad (8\text{'h7F}), \quad \text{MIN\_VAL} = -128 \quad (8\text{'h80})$$
   $$\text{out\_data} = \begin{cases} 0, & \text{if } \text{relu\_en} = 1 \text{ and } \text{scaled\_val} < 0 \\ +127, & \text{if } \text{scaled\_val} > +127 \\ -128, & \text{if } \text{scaled\_val} < -128 \\ \text{scaled\_val}[7:0], & \text{otherwise} \end{cases}$$

---

## 5. M0 / M3 / M4 中央审核与合同对接核对清单

后续在将本通用基础模块接入顶层 CNN 引擎与 M0 / M3 合同时，中央审核需核对以下关键字段：

| 检查项 | 基础设施约定 | 顶层/算法需确认项目 |
|---|---|---|
| **乘数位宽 (`MULT_WIDTH`)** | 支持 32-bit signed int | 确认 PTQ/QAT 导出的 `multiplier` 是否为 32-bit 或 16-bit 格式 |
| **右移位数 (`SHIFT_WIDTH`)** | 5-bit (支持 0..31 范围) | 确认导出量化配置中每层的 `shift` 是否均在 $[0, 31]$ 内 |
| **舍入规则** | `round-half-away-from-zero` | 确认 Python 整数参考模型 (`integer_reference.py`) 采用相同舍入公式 |
| **RAM 读延迟** | 固定 1 拍 | 确认 CNN 控制状态机、地址生成器与 MAC 累加节拍严格对齐 1 拍读延迟 |
| **Requant 延迟** | 输入采样沿 E0，结果注册沿 E1 | 顶层按 `out_valid` 握手，不用含糊的计数拍数推断数据有效 |
| **RAM 冲突处理** | Read-First | 确认算法与数据流是否依赖同址并发读写；若依赖 Write-First 则需添加旁路前推 (Forwarding) 逻辑 |
| **时钟约束** | 27 MHz (周期 37.037 ns) | 确认两级寄存结构在 Gowin 综合 PnR 后的 Setup/Hold 时序裕量充足 (WNS >= 0 ns) |
| **BSRAM 推断** | 纯同步无复位阵列 | 综合后核对 Gowin 报告中的 BSRAM 块数是否与预期一致，无 45k LUT 膨胀 |

---
*文档版本：v1.0 (2026-08-27)*
