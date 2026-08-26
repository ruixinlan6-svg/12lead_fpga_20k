# QN88 SDRAM 首读为零问题说明

## 1. 问题范围

目标板为 Sipeed Tang Nano 20K，实物封装为 `GW2AR-LV18QN88C8/I7`（QN88）。
QN88 使用 Gowin 内置 SDRAM SIP；本问题只涉及 FPGA 内的 `SDRC_EMB` 控制器和
volatile SDRAM 读写，不涉及 QSPI Flash，也不代表完整 ECG 模型已经部署成功。

## 2. 初始现象

最初的探针能够综合、布局布线并下载到 SRAM，控制器也报告初始化完成，但 COM10
反复收到：

```text
SDRAM I1 P0 E1 D=0000 X=A5A5
```

含义是：初始化标志为 1，读写比较失败，首个失配数据的高 16 位为 `0000`，期望值
高 16 位为 `A5A5`。因此不能仅凭“初始化完成”判断 SDRAM 数据通路正常。

## 3. 复位路径与排除结果

当前复位路径为：

```text
rst_btn → button_rst_n → por_cnt → por_done → rst_n → I_sdrc_rst_n
```

实现位置见 [qn88_sdram_probe_top.v](../../fpga/sdram_probe/qn88_sdram_probe_top.v)。
其中 `por_cnt` 在释放按键后计数 65,536 个 27 MHz 时钟周期，约 2.43 ms，
再释放 `SDRC_EMB` 和探针状态机。

复位实验只改变这一项，结果仍为 `I1 P0 E1 D=0000 X=A5A5`。因此：

- 控制器复位位置已经明确；
- 延长复位可以作为上电稳健性措施保留；
- “首读为零”不能归因于复位释放过早。

## 4. 证据链和定位过程

| 阶段 | 单变量变化 | 板级结果 | 结论 |
|---|---|---|---|
| 基线 | 内部线网连接 SDRAM 端口 | `D=0000 X=A5A5` | 数据路径未恢复 |
| 复位 A/B | 增加 2.43 ms POR | 结果不变 | 排除复位为主因 |
| 顶层端口 | 将 `O_sdram_*`、`IO_sdram_dq` 置为顶层端口 | 高 16 位变为 `D=A5A5` | Gowin 重新识别 QN88 SDRAM SIP，原始首读零根因定位 |
| 低位观测 | UART 改报低 16 位 | `D=0001 X=0000` | 发现用户数据启动值有一拍偏移 |
| 读长度 | 只比较 `data_len=25` 的有效字 | 尾部失配消失 | 忽略一个旧数据尾脉冲 |
| 突发切换 | 每个 burst 重装写数据基值 | `P1 E0` | 修复第二突发继承上一突发计数的问题 |

## 5. 最终根因

### 5.1 原始“首读高位为零”

Gowin QN88 内置 SDRAM 依赖特定的顶层端口名：

```text
O_sdram_clk, O_sdram_cke, O_sdram_cs_n, O_sdram_cas_n,
O_sdram_ras_n, O_sdram_wen_n, O_sdram_dqm,
O_sdram_addr, O_sdram_ba, IO_sdram_dq
```

原设计把这些信号保留为模块内部线网。综合后的 `qn88_sdram_controller` 没有保留
有效的 DQ/返回数据路径，导致首读高 16 位为零。将这些端口提升到设计顶层后，综合网表
重新出现 `sdrc_data_out`、`IO_sdram_dq` 以及 SDRAM 地址/命令端口，PnR 也将它们映射到
QN88 内置 SDRAM 位置。

公开参考实现也采用同样的顶层端口命名：[Tang Nano 20K SDRAM 示例](https://github.com/nand2mario/sdram-tang-nano-20k/blob/main/src/sdram_top.v)。

### 5.2 完整比较失败的后续 RTL 问题

顶层端口修复后，数据通路虽恢复，但测试器仍暴露出三个独立的接口/状态问题：

1. 首个用户返回字为 `A5A5_0001`，而原期望寄存器从 `A5A5_0000` 开始；期望流按观测到的用户接口启动语义对齐。
2. `data_len=25` 的 QN88 传输末尾会出现一个不应参与比较的旧数据脉冲；比较窗口收敛到 25 个有效字。
3. 突发切换时原写数据寄存器没有重装，第二突发从上一突发的低位计数继续；切换时重装 `A5A5_0000 + burst*0x0100` 基值。

这些问题不是复位问题，但如果不修复，仍会表现为 `P0 E1`，容易掩盖首读为零已经被解决的事实。

## 6. 当前实现和验证结果

当前实现保留：

- QN88 SDRAM 魔法端口为顶层端口；
- 约 2.43 ms 的确定性 POR；
- 25 个有效字比较窗口；
- 每个突发独立重装写数据基值；
- 仅 SRAM 下载，禁止 Flash 写入。

最终比特流：

```text
fpga/sdram_probe/build/qn88_sdram_probe/impl/pnr/qn88_sdram_probe.fs
SHA-256: 1B1ACF201B380AD6B3F1D4AB807C73CFF6E2022DB521CFAEAF873A000B9EDE50
```

QN88 SRAM 下载成功，COM10 清空输入缓冲后连续 8 次收到：

```text
SD I1 P1 E0 C=19 D=0000 X=0000
```

`P1 E0` 表示四个突发的 volatile 读写 smoke 通过；`D/X` 在无失配时保持零，不能将
它们解释为实际数据内容。

## 7. 未覆盖范围

本结论仅覆盖当前 27 MHz、`data_len=25`、四突发、SRAM 下载条件下的控制器 smoke：

- 未做长时间 SDRAM 保持/刷新压力测试；
- 未做 Flash 启动验证；
- 未接入完整 ECG 模型的连续数据流；
- 尚未证明 GoAI/NPU 的 QN88/SDRAM 兼容性。

因此，后续模型部署必须继续沿用同一顶层端口契约，并在进入模型流量前重新建立
软件 Golden、RTL 和板级逐字对拍。

## 8. 追溯入口

- [迭代索引](../iterations/INDEX.md)
- [复位实验](../iterations/records/20260826-1743-m4-qn88-sdram-por-reset.md)
- [魔法端口实验](../iterations/records/20260826-1757-m4-qn88-sdram-magic-ports.md)
- [最终突发重装实验](../iterations/records/20260826-1840-m4-qn88-sdram-burst-reseed.md)
- [SDRAM 探针 README](../../fpga/sdram_probe/README.md)

本文基于修复提交 `d9e80cd`；本文件用于问题说明，不替代各轮不可覆盖的实验记录。
