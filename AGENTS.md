# 十二导联 ECG 本地部署：项目级 Agent 约束

本目录的目标硬件是 **Sipeed Tang Nano 20K / Gowin GW2AR-18C**。开始任何实现前，先阅读：

1. `docs/superpowers/plans/2026-08-26-ecg-fpga-closed-loop.md`
2. `datasheet/2026-08-26_十二导联ECG文献与数据集证据.md`
3. `docs/goai/GOWIN_GOAI_ECG_GUIDE.md` 与 `datasheet/2026-08-26_Gowin-GoAI_十二导联ECG可用性.md`
4. 若本机存在，阅读本地专用的 `datasheet/REMOTE_LRX_AGENT_CONNECTION.md`；该文件不进入公共仓库
5. 当前 Agent skill catalog 中可用的 `bluestar-fpga-skill`

## 已确认边界

- 当前目录已初始化为 Git 仓库，远端为 `ruixinlan6-svg/12lead_fpga_20k`，主分支为 `main`。不要重新初始化、改写公共历史或覆盖现有 `project/` LED 板级基线。
- `train/` 当前无实现。数据下载、远端训练、JTAG 扫描、综合、下载和烧录都必须由后续明确任务授权；不要因为阅读本计划而自动执行。
- 首轮研究默认采用 PTB-XL 100 Hz、10 秒、12 导联、5 个诊断超类多标签任务。若任务或标签定义改变，先更新共享 I/O 契约和数据划分，不得静默改变语义。
- 本项目是研究原型，不输出临床诊断结论，不把测试集或板端演示数据加入训练。

## 硬件事实与硬门禁

- 现有工程目标为 `GW2AR-18C`；PnR 报告记录的器件号是 `GW2AR-LV18QN88PC8/I7`，工具版本为 Gowin `V1.9.12.03`。
- 板卡资料给出的资源为 20,736 LUT4、46 个 BSRAM（828 Kbit）、48 个 18x18 乘法器、64 Mbit 板载动态存储及 64 Mbit QSPI Flash。
- 原理图/板卡文档与现有工程对 QN88/QN88P、SDRAM/PSRAM 的描述存在差异。任何 NPU 存储架构开始前，必须用实物丝印、JTAG 扫描、EDA 器件选择和存储器读写测试四项证据锁定真实器件与内存类型。
- BlueStar Skill 中 Tang Primer 25K 的 50 MHz、24-bit PSRAM word 地址、8 路 SIMD、32 KB 双缓存仅是参考，不得直接复制为本项目契约。
- 首次板级下载只允许 SRAM 模式；持久化 Flash 烧录需要在仿真、时序和 SRAM 上板结果通过后得到明确授权。

## GPU 与 FPGA 工具规则

- GPU 连接只使用 SSH 别名 `ecg-gpu-server`，并遵循 `datasheet/REMOTE_LRX_AGENT_CONNECTION.md`。每次先验证身份、GPU 占用和计算进程；不得停止他人进程。
- 小型 1D ECG 模型优先采用“每张空闲卡一个独立候选/随机种子”，只有单次实验确实需要时才使用多卡数据并行。
- 远端 Python 使用说明中的绝对路径，结果写入远端项目 `runs`；同步回本地时保留配置、数据清单、随机种子、指标、模型哈希和日志。
- FPGA 工作依次通过：算子单测、整数 Golden 逐层比对、顶层协议仿真、Gowin 综合/PnR、SRAM 实板测试。禁止跳过前级直接上板。
- BSRAM 数据通路使用纯同步读写模板；控制复位与 RAM 数据读写分离。综合后必须核对 BSRAM/DSP 是否真正被推断，不能只看 RTL 仿真通过。

## 结果回传要求

每个实验使用唯一 `run_id`，至少保存：配置、数据版本与划分哈希、浮点指标、量化指标、逐层整数比对、资源/时序报告、板端延迟（核心推理与通信分开）、输出一致性及模型/比特流哈希。最终结论只能是“接受、回到训练、回到量化、回到 RTL/存储架构”之一，并附触发证据。

## 强制优化追溯规则

- 每一轮数据、训练、量化、GoAI、RTL、综合或板测优化，执行前先从 `docs/iterations/TEMPLATE.md` 创建唯一 `docs/iterations/records/<run_id>.md`。
- 执行前必须写明基线、问题证据、优化手法、选择原因、替代方案和冻结的验收门槛；不得在看到测试结果后补写原因或修改门槛。
- 执行后补齐优化前后差值、失败样本、资源/时序/延迟、产物路径与 SHA-256、未验证项和接受/拒绝/回退决定。
- 失败、无收益、中止和回滚也必须记录。旧记录不得覆盖；假设、方法或门槛发生变化时创建新 `run_id`。
- 每轮结束同步更新 `docs/iterations/INDEX.md`。任何包含训练、量化、部署或板测结论的提交，没有对应记录与索引更新则不得视为完成。
