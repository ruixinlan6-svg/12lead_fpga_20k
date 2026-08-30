# Optimization Run: `20260827-1145-m5-scheme-b-sdram-streaming`

## Identity

- Run ID: `20260827-1145-m5-scheme-b-sdram-streaming`
- Stage: `rtl | synth | hil`
- Status: `completed`
- Started/finished: 2026-08-27T11:45:00+08:00 / 2026-08-27T21:50:00+08:00
- Agent/operator: Antigravity
- Baseline run: `20260826-1929-m2-input-quant-contract`
- Git commit: HEAD
- Data version and split hash: PTB-XL INT8 PTQ 5-class contract
- Config/contract paths: `runs/20260826-1929-m2-input-quant-contract/contract.json`
- Environment: Windows, Gowin V1.9.12.03 x64, Sipeed Tang Nano 20K (GW2AR-LV18QN88C8/I7)

## Problem and evidence

- Observed problem: 在方案 A（全片上并行展开）中，特征图与全部权重静态占用 36 个 BSRAM（占用率 78%），导致片上剩余 Block RAM 极少，无法扩展至更深更宽的 1D-CNN/ResNet/TCN 模型。
- Evidence from the baseline: Gowin PnR 报告显示方案 A 占用 36/46 BSRAM，DSP 24/24。
- Primary metric or failure point: 需在保持 100% 逐层 Bit-Exact 精度的前提下，将 BSRAM 资源大幅压缩至 $\le 28$ 个（利用率 $\le 61\%$）。

## Optimization

- Method: 实施**方案 B：双缓存乒乓特征图（ActBuf_A / ActBuf_B 16 KB）+ 分层权重 DMA 流式加载**。
- Why this method:
  1. 特征图仅需在两块 16 KB BRAM 之间交替乒乓，彻底省去每层独立特征图 BRAM。
  2. 权重通过微秒级 DMA 逐层从参数存储区重载至 8 KB `WeightBuf`，显著节约片上常驻 RAM。
  3. 解耦计算与存储，为后续直接接入外部 64 Mbit SDRAM 运行大模型奠定标准 DMA 基础。
- Alternatives considered and why not selected:
  - 方案 A（全片上展开）：BRAM 耗尽，扩展性为 0。
  - 直接外部 SDRAM 单字随机访问：延迟极高，且无法利用突发 DMA 优势。
- Expected mechanism: 利用双口同步 BRAM 特性，在层间切换时触发 DMA 状态机快速覆写 WeightBuf。

## Frozen acceptance criteria

- Success threshold:
  1. 算子及逐层仿真 `tb_scheme_b_core.sv` 与顶层仿真 `tb_scheme_b_top_27mhz.sv` 100% Bit-Exact 零误差（Logits: `[32, -22, -21, -19, -21]`）。
  2. Gowin 综合与 PnR 成功，BSRAM $\le 28$ 个，DSP 24/24，时序满足 27 MHz 要求无负裕量。
  3. 硬件在环测试（HIL）成功返回 `ECG P1 S1 D1` 且无通信死锁。
- Failure/rollback threshold: 任何层出现精度偏移、时序违例（TNS < 0）或 BSRAM 超标。
- Fixed test set, thresholds and measurement conditions: `runs/20260826-1929-m2-input-quant-contract/hex` 中的 12,000 字节波形与 10,293 字节参数。

## Execution

- Entry command or script:
  - `iverilog -g2012 -o sim_core.vvp tools/scheme_b/tb_scheme_b_core.sv ... && vvp sim_core.vvp`
  - `iverilog -g2012 -o sim_top_27mhz.vvp tools/scheme_b/tb_scheme_b_top_27mhz.sv ... && vvp sim_top_27mhz.vvp`
  - `& "D:\software\Gowin\Gowin_V1.9.12.03_x64\IDE\bin\gw_sh.exe" tools/scheme_b/build_scheme_b.tcl`
  - `& "D:\software\Gowin\Gowin_V1.9.12.03_x64\Programmer\bin\programmer_cli.exe" --device GW2AR-18C --run 2 --fsFile ...`
  - `python tools/hil/qn88_model_full_test.py --run runs/20260826-1929-m2-input-quant-contract --port COM10 --burst-pause 0.002 --wait-done`
- GPU/card or hardware connection used: Tang Nano 20K on COM10 (115200 baud).

## Results

| Metric | Baseline (Scheme A) | This run (Scheme B) | Delta | Comparable? |
|---|---:|---:|---:|---|
| Primary model metric (Logits) | `[32, -22, -21, -19, -21]` | `[32, -22, -21, -19, -21]` (Sim) | 0 diff (Bit-Exact) | Yes |
| Quantization/parity error | 0 mismatch | 0 mismatch (Sim) | 0 | Yes |
| BSRAM Utilization | 36 / 46 (78%) | **28 / 46 (61%)** | **-8 BSRAM (-22%)** | Yes |
| DSP Utilization | 24 / 24 (100%) | 24 / 24 (100%) | 0 | Yes |
| Logic LUTs | 1,842 (9%) | 2,178 (11%) | +336 LUTs | Yes |
| Fmax (MHz) | 27.200 MHz | **27.819 MHz** | +0.619 MHz | Yes |
| Timing Slack (TNS) | 0.000 (Met) | **0.000 (Met)** | 0.000 | Yes |
| Core Latency | ~280 ms | ~328 ms | +48 ms | Yes |

- Per-class or per-layer findings:
  - Pool1 ($16 \times 500$): 8000/8000 比特级一致 (0 error).
  - Pool2 ($32 \times 250$): 8000/8000 比特级一致 (0 error).
  - ReLU3 ($32 \times 250$): 8000/8000 比特级一致 (0 error).
  - GAP (32 ch): 32/32 比特级一致 (0 error).
  - Dense Head (5 logits): 5/5 比特级一致 `[32, -22, -21, -19, -21]` (Hex: `20 EA EB ED EB`).
- Logs and report paths:
  - Gowin PnR Report: `fpga/scheme_b/build/qn88_scheme_b/impl/pnr/qn88_scheme_b.rpt.txt`
  - Gowin Timing Report: `fpga/scheme_b/build/qn88_scheme_b/impl/pnr/qn88_scheme_b.tr.html`
- Artifact paths and SHA-256:
  - Bitstream: `fpga/scheme_b/build/qn88_scheme_b/impl/pnr/qn88_scheme_b.fs`

## Decision

- Decision: `partial_accept`
- Reason: 方案 B 在 RTL 仿真和 Gowin PnR 上验证了“双缓存 16 KB 乒乓特征图 + 8 KB 参数片上缓存”架构，BSRAM 从 36 块降至 28 块（节省 22%），时序收敛至 27.819 MHz。但必须明确：当前 SDRAM 控制引脚在顶层为常置非活动状态，权重实际存放于片上参数 RAM 块中，尚未完成物理外部 64 Mbit SDRAM 实时流式读取；且缺少独立归档的 COM10 原始物理 HIL 报文日志。因此该成果仅作为“片上双缓存乒乓与分层 DMA 硬件微基准”，不能称为“已完成 SDRAM 权重流”。
- What changed in the project baseline: 建立了 `fpga/scheme_b/` 核心代码库与 `docs/scheme_b/README.md`，确立了双缓存乒乓与分层流式 DMA 原型架构。
- One primary question for the next run: 如何在通过独立 SDRAM 读写门禁后，将 DMA 控制器物理挂接至板载 64 Mbit SDRAM？