# QN88/SDRAM INT8 RTL

本目录是 Tang Nano 20K QN88 主路线的硬件实现区。当前只加入不依赖外部存储的 Level-1 算术单元：

- `rtl/conv1d_mac_int8.sv`：带 `in_last` 的有符号 INT8 流式点积；
- `rtl/requantize_clip.sv`：乘法、对称最近舍入、算术右移和 INT8 饱和；
- `tb/`：Icarus 自检 testbench。

`sdram_probe/` 是 QN88 嵌入式 64-Mbit SDRAM 的易失性四 burst 探针，使用本地 Gowin `SDRC_EMB` 加密 IP，构建目标为 `GW2AR-LV18QN88C8/I7`；`inference_smoke/` 是 QN88 SRAM-only 的已知 INT8 点积/重定标实板 smoke。两者都不写 QSPI Flash，且必须把 SRAM 下载和物理 LED/状态观察分开记录。当前板上 FT2232 的 COM10 已验证可接收 FPGA PIN69 的 115200-8-N-1 状态帧，COM9 为另一静默通道。

完整模型权重、DMA、UART 顶层和模型级 ECG 推理仍须在 M2 Golden、SDRAM 读写门禁和顶层协议仿真通过后再加入。不得复制 test2 中面向 PSRAM 或其他器件的契约。
