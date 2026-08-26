# QN88/SDRAM INT8 RTL

本目录是 Tang Nano 20K QN88 主路线的硬件实现区。当前只加入不依赖外部存储的 Level-1 算术单元：

- `rtl/conv1d_mac_int8.sv`：带 `in_last` 的有符号 INT8 流式点积；
- `rtl/requantize_clip.sv`：乘法、对称最近舍入、算术右移和 INT8 饱和；
- `tb/`：Icarus 自检 testbench。

SDRAM 控制器、DMA、UART 顶层和实际模型权重必须在 M2 整数 Golden 及 QN88 SDRAM 读写门禁通过后再加入。不得复制 test2 中面向 PSRAM 或其他器件的契约。
