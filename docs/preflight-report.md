# M0 预检报告

## 时间与范围

- 检查时间：2026-08-26 14:34（Asia/Shanghai）
- 基线提交：`06b5d232b685f75b8b453a23b5b373226af66f35`
- 本轮仅做环境、工具、JTAG 和远端 GPU 只读检查；未下载数据、未训练、未综合、未下载 FPGA、未写 Flash。

## 结果摘要

| 检查项 | 结果 | 证据/限制 |
|---|---|---|
| Python | 通过 | 本地 Python 3.14.4 |
| Icarus Verilog | 通过 | 12.0；已有 LED 基线仿真通过 |
| Gowin EDA | 可调用 | `gw_sh.exe` 位于本地 V1.9.12.03 安装目录 |
| Programmer | 可调用 | `programmer_cli.exe` 位于本地 V1.9.12.03 安装目录 |
| SSH 别名 | 通过 | `ecg-gpu-server` 可认证；身份检查成功；未记录主机地址/密钥 |
| 远端训练 Python | 通过 | `lrx_train` 环境 Python 3.10.20，PyTorch 2.7.1+cu128，CUDA 设备数 3 |
| GPU 0 | 当前候选空闲 | RTX 5060 Ti，0/16311 MiB，0% 利用率；启动任务前仍需复查 |
| GPU 1 | 暂不自动占用 | RTX 5060 Ti，39/16311 MiB，0% 利用率；存在少量系统占用，启动前需复查 |
| GPU 2 | 不可用 | RTX 4090，962/49140 MiB，15% 利用率；存在其他计算进程 |
| JTAG | 通过但不完整 | 发现 2 个 USB Debugger；1 个设备，报告 GW2ANR 系列/ID `0x0000081B` |
| 精确封装 | 未通过 | JTAG 输出未区分 QN88/QN88P |
| 存储器类型 | 未通过 | 尚未完成非破坏性 SDRAM/PSRAM 读写测试 |
| 串口 | 未确认 | 本机 WMI 串口枚举未返回端口；需要后续识别 USB-UART 设备 |

## 硬件冲突

当前 EDA 工程选择 `GW2AR-LV18QN88PC8/I7`，而本地 Tang Nano 20K 资料指向不带 P 的 QN88/SDR SDRAM。公开 NPU IP 的范围是 QN88P/PSRAM。故硬件契约仍为 provisional；在物理丝印、JTAG/EDA 和存储器测试一致前，不得把 GoAI/NPU 作为本板可部署事实。

## 允许的下一步

1. 记录板上 FPGA 丝印或清晰照片，确认 QN88/QN88P。
2. 在不写配置 Flash 的前提下，准备独立的 volatile memory test bitstream，确认 SDRAM/PSRAM 接口。
3. 完成后再创建 M1 数据登记和训练记录；启动远端实验前复查 GPU 0/1 的计算进程。

## 禁止事项

- 不得把 GPU 2 的任务停止或迁移。
- 不得向 QSPI Flash 写入权重或配置。
- 不得在未冻结 I/O/量化契约时下载 PTB-XL 或生成模型部署结论。
