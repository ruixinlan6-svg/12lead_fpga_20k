# ANSI/AAMI EC57:2012 QRS/VEB 评测要求与本项目边界

- 核查日期：2026-08-27
- 核查范围：标准状态、FDA 认可含义、QRS/VEB 五项指标、标准数据库、事件匹配与报告产物
- 证据范围：AAMI/ANSI、FDA、PhysioNet/WFDB 一手来源；未使用二手论文定义代替标准
- 法规声明：本文是研究与工程规划，不是 FDA 法规意见，也不能替代持证法规专业人员对具体 intended use、产品代码和申报路径的判断

## 结论先行

1. 截至核查日，ANSI 与 AAMI 的目录把现行文件列为 **ANSI/AAMI EC57:2012/(R)2020**；该版于 2012-12-18 批准、2020-10-09 重确认。FDA 认可数据库当前列出的名称仍为 **ANSI/AAMI EC57:2012**，认可号 **3-118**，认可范围为完整标准。AAMI 2025—2026 年公开信息显示下一次重确认/潜在修订仍在进行，不能写成已有更新版本发布。[AAMI 目录](https://aami.org/standard/ansi-aami-ec572012-r2020-pdf/)、[ANSI 目录与文档历史](https://webstore.ansi.org/standards/aami/ansiaamiec572012r2020)、[ANSI 合法预览](https://webstore.ansi.org/preview-pages/AAMI/preview_ANSI%2BAAMI%2BEC57-2012%2B%28R2020%29.pdf)、[AAMI 2026 委员会动态](https://aami.org/wp-content/uploads/2026/04/6-April-24-2026.pdf)、[FDA 认可条目 3-118](https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfStandards/detail.cfm?standard__identification_no=31679)
2. 不能准确表述为“心率/心律失常算法要获 FDA 认可，必须通过 EC57”。更准确的说法是：EC57 是 FDA 完整认可、且与多类心律失常/心电监护产品代码相关的共识测试与报告方法；采用并声明符合可简化审评证据，但共识标准通常是自愿的，除非被法规援引。FDA 明确允许能提供等效安全有效性保证的替代方法。[FDA 共识标准使用说明](https://www.fda.gov/medical-devices/premarket-submissions-selecting-and-preparing-correct-submission/division-standards-and-conformity-assessment)、[FDA 共识标准指南](https://www.fda.gov/media/71983/download)、[FDA 心律失常检测器特殊控制指南](https://www.fda.gov/medical-devices/guidance-documents-medical-devices-and-radiation-emitting-products/arrhythmia-detector-and-alarm-class-ii-special-controls-guidance-document-industry-and-fda-staff)
3. EC57 是**测试和报告方法**，ANSI 合法预览明确说明它“not a performance standard”；因此它不是给所有算法设定一条通用分数线的“通过证书”。具体接受标准应由 intended use、风险分析、与合法 predicate 的比较及申报策略确定，并在测试前冻结。FDA 特殊控制指南同样要求申报者说明所采用的接受标准，必要时 FDA 可要求补充信息。[ANSI 合法预览](https://webstore.ansi.org/preview-pages/AAMI/preview_ANSI%2BAAMI%2BEC57-2012%2B%28R2020%29.pdf)、[FDA 特殊控制指南：测试报告与接受标准](https://www.fda.gov/medical-devices/guidance-documents-medical-devices-and-radiation-emitting-products/arrhythmia-detector-and-alarm-class-ii-special-controls-guidance-document-industry-and-fda-staff)
4. 用户要求的五项指标可纳入项目，但它们评价的是**逐心搏 QRS 定位与 VEB/PVC 识别**。现有 PTB-XL `NORM/MI/STTC/CD/HYP` 五超类模型是 10 秒、十二导联、记录级多标签分类器，只输出五个记录级 logits，不能从这些 logits 直接计算 EC57 五项指标。
5. PhysioNet 维护的 `bxb` 是 ANSI/AAMI 逐拍比较参考实现。标准窗口为 150 ms；其 `VEB false positive rate` 明确定义为 `VFP/(VTN+VFP)×100%`，单位是**百分比**，不是 `FP/hour`。如果项目还需要“每小时 PVC 误报数”，可以作为补充指标单列，但不得把它标成 EC57 `V FPR`。[WFDB `bxb` 文档](https://physionet.org/physiotools/wag/bxb-1.htm)、[`bxb.c` 指标公式](https://physionet.org/files/wfdb/10.7.0/app/bxb.c)

## 1. 标准版本与 FDA 认可边界

### 1.1 当前版本状态

- ANSI 目录将 `ANSI/AAMI EC57:2012 (R2020)` 标为 most recent，且记录其修订自 2012 原版、无已列出的 amendment/correction。[ANSI 目录](https://webstore.ansi.org/standards/aami/ansiaamiec572012r2020)
- ANSI 合法预览显示：2012 年批准，2020 年重确认；目录包括数据库、排除记录、测试要求、逐拍比较、逐运行比较、VF/AF 和 ST 比较等章节。本文不复制受版权保护的标准正文。[ANSI 合法预览](https://webstore.ansi.org/preview-pages/AAMI/preview_ANSI%2BAAMI%2BEC57-2012%2B%28R2020%29.pdf)
- AAMI 2025 年把下一次动作列为 `EC57:2012/(R)202X` 重确认，2026 年仍在征集参与 reaffirmation and potential revisions；这只是制修订进程证据，不是新版本发布。[AAMI 2025 Standards Monitor](https://aami.org/wp-content/uploads/2025/11/14-November-7-2025.pdf)、[AAMI 2026 Standards Monitor](https://aami.org/wp-content/uploads/2026/04/6-April-24-2026.pdf)
- FDA 认可数据库在核查日仍列 `ANSI AAMI EC57:2012`，FR 认可号 3-118，extent of recognition 为 complete standard；相关设备包括心律失常检测/报警、带心律失常报警的患者监护、ST 监护、心率监护、心电图机和带分析算法的动态心电图机等。FDA 条目没有把 `(R)2020` 写入名称，因此申报时应按 FDA 数据库中的认可名称/版本填写，并让法规人员确认重确认版声明形式。[FDA 认可条目](https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfStandards/detail.cfm?standard__identification_no=31679)

### 1.2 “FDA 必须通过 EC57”为什么不严谨

FDA 的官方表述是：

- 共识标准符合性通常是自愿的，除非标准被法规以引用方式纳入；
- 制造商可依赖 FDA 认可标准并提交 conformity declaration，也可用能满足相应法规要求的替代路径；
- 对“心律失常检测器和报警器”这类 Class II 设备，特殊控制指南建议按 EC57 评价逐搏检测算法，但明确允许说明替代方法、目标和局限；
- 数据库只验证了哪些声明，产品标签就只能支持相应声明，不能从 QRS/PVC 结果外推到全部诊断能力。

因此，项目文档建议统一使用：

> EC57 是本项目 QRS/VEB 算法的首选标准化验证与报告方法，也是 FDA 当前完整认可的相关共识标准；FDA 申报是否采用 EC57、还需哪些证据及接受门槛，取决于 intended use、产品分类和申报策略。EC57 结果本身不是 FDA 批准。

来源：[FDA 标准与符合性说明](https://www.fda.gov/medical-devices/premarket-submissions-selecting-and-preparing-correct-submission/division-standards-and-conformity-assessment)、[FDA 心律失常检测器特殊控制指南，第 10 节](https://www.fda.gov/medical-devices/guidance-documents-medical-devices-and-radiation-emitting-products/arrhythmia-detector-and-alarm-class-ii-special-controls-guidance-document-industry-and-fda-staff)

## 2. 五项指标的可执行定义

先把参考标注与算法标注按 EC57/AAMI 映射和逐拍时间匹配形成混淆矩阵，再计算统计量。以下 `×100%` 表示报告百分比；分母为零时应报告 `N/A`，不能写成 0。

| 指标 | 中文 | 公式 | 工程含义 |
|---|---|---:|---|
| QRS Se | QRS complex sensitivity | `QTP/(QTP+QFN)×100%` | 参考 QRS 中被算法检出的比例 |
| QRS +P | QRS complex positive predictivity | `QTP/(QTP+QFP)×100%` | 算法给出的 QRS 检测中真正为 QRS 的比例 |
| VEB Se / V Se | ventricular ectopic beat sensitivity | `VTP/(VTP+VFN)×100%` | 参考 VEB 中被正确识别为 VEB 的比例 |
| VEB +P / V +P | ventricular ectopic beat positive predictivity | `VTP/(VTP+VFP)×100%` | 算法报出的 VEB 中真正为 VEB 的比例 |
| VEB FPR / V FPR | ventricular ectopic beat false positive rate | `VFP/(VTN+VFP)×100%` | 非 VEB 判定机会中被误报成 VEB 的比例 |

公式依据是 PhysioNet/WFDB 10.7.0 的 AAMI 参考实现：`bxb.c` 构建 QRS/VEB 计数，并分别调用 `pstat` 计算上述五项；其中 VEB FPR 的分母明确是 `VTN+VFP`。[`bxb.c` 第 986—1003 行附近](https://physionet.org/files/wfdb/10.7.0/app/bxb.c)

### 2.1 VEB FPR 不是每小时误报数

EC57/WFDB 表中的 `V FPR` 是二分类意义上的 false-positive rate：

```text
V FPR = 100 × VFP / (VTN + VFP)  [%]
```

项目可以额外报告：

```text
VEB false alarms per hour = VFP / valid_test_hours  [events/hour]
```

但必须使用不同字段名和单位，例如 `veb_fp_per_hour`，不得用它替换 `veb_fpr_percent`。建议机器可读结果同时保存原始 `VTP/VFN/VFP/VTN`，避免百分比定义被误解。

### 2.2 VEB 与 PVC 的关系

在 WFDB 的 AAMI 映射中，PVC、R-on-T PVC、ventricular escape beat 被映射到 `V`；因此报告标题应优先使用标准术语 `VEB`，产品需求可在括号中说明“含 PVC 类”。不要把“VEB 五项统计”缩写成只覆盖一种 PVC 形态。[`bxb.c` AAMI beat mapping](https://physionet.org/files/wfdb/10.7.0/app/bxb.c)

## 3. 事件匹配与排除合同

### 3.1 必须采用的事件匹配

1. 输入必须是同一记录上的 reference annotation 与 test annotation，至少包含事件采样点和 beat type。
2. 使用 WFDB `bxb` 的标准模式；默认允许的最大时间差为 **150 ms**。匹配还会在相邻事件之间选择更合理的最近配对，不应自行实现“每个预测只找窗口内任意参考点”的简化算法。[`bxb` 官方文档](https://physionet.org/physiotools/wag/bxb-1.htm)、[`bxb.c` 匹配逻辑](https://physionet.org/files/wfdb/10.7.0/app/bxb.c)
3. 不得在正式报告中调整 `-w` 匹配窗，或用 `-f/-t` 选取更有利的时间段；`bxb` 官方文档明确说明这些选项会产生不符合 EC57 的非标准比较。开发调试结果与正式标准结果必须分目录保存。[`bxb` 官方文档](https://physionet.org/physiotools/wag/bxb-1.htm)
4. 全部 beat annotation 按 AAMI 类别映射到 `{N, V, F, S, Q}`；映射表和 WFDB 版本必须固化。不能只把数据库原始字符 `V` 当作唯一 VEB，也不能静默丢弃未知/融合/起搏标签。[WFDB test annotation 说明](https://physionet.org/physiotools/wag/evnode8.htm)、[`bxb.c` 映射实现](https://physionet.org/files/wfdb/10.7.0/app/bxb.c)

### 3.2 学习期、起搏记录和无效区间

- WFDB EC57 流程默认忽略每条记录最初 **5 分钟 learning period**，其余是正式 test period。[WFDB 获取测试标注说明](https://physionet.org/physiotools/wag/evnode8.htm)
- `bxb` 源码说明 AAMI 报告排除含起搏心搏的记录；WFDB 的 `mitxlist` 与 `ahaxlist` 是去除起搏记录后的标准列表，`ecgeval` 也将 `MITx/AHAx` 描述为 excluding paced records。正式测试应使用经过法规/标准复核的 canonical list，而不是临时按标签过滤。[`ecgeval` 数据库列表](https://physionet.org/physiotools/wag/ecgeva-1.htm)、[WFDB 10.7.0 canonical lists](https://physionet.org/content/wfdb/10.7.0/data/)
- reference 标注中的 VF 区间、signal shutdown/noise 区间有专门计数逻辑；不要先把这些片段裁掉再计算。测试端 shutdown 还要独立报告持续时间和漏检情况。[`bxb.c` VF/shutdown 处理](https://physionet.org/files/wfdb/10.7.0/app/bxb.c)
- 精确的“EC57:2012 表 1/表 2 对每个声明所要求的记录及排除项”应以购买/授权访问的 `(R)2020` 正文为最终签核依据；本项目实现阶段不能只依据本文或旧版 WFDB 文档自称已完成合规测试。

## 4. 记录级、数据库级汇总要求

正式结果至少保留三层：

1. **逐记录**：混淆矩阵计数、五项指标、有效时长、shutdown、未定义指标、所有 mismatch 事件；
2. **每数据库 gross**：先对所有记录的 `TP/FN/FP/TN` 求和，再计算指标；
3. **每数据库 average**：对分母有效的逐记录指标做等权算术平均，并同时给出参与平均的记录数。

WFDB `sumstats` 会在逐记录表后追加 Sum、Gross、Average 和总 QRS/VEB 数；gross 与 average 不能互相替代。[`sumstats` 官方说明](https://physionet.org/physiotools/wag/sumsta-1.htm)、[`sumstats.c` 参考实现](https://physionet.org/files/wfdb/10.7.0/app/sumstats.c)

报告规则建议冻结为：

- MIT DB 与 AHA DB 分开报告 gross/average，不得只给一个混合后的最好数字；
- 百分比旁边必须给分子/分母或原始计数；
- 每个数据库列出 included/excluded records 及理由；
- 可加 95% 置信区间、F1、FP/hour 和分噪声等级结果，但它们是补充项，不能替换 EC57 表项；
- 未定义项写 `N/A`；算法失败、文件缺失、超时和板端丢包必须进入失败报告，不能删除该记录后重算；
- 所有阈值、后处理、refractory period、lead selection 和量化参数必须在测试前冻结。

## 5. 标准数据库及适用能力

PhysioNet 的 ECG analyzer evaluation guide 列出 EC38/EC57 所用的五类标准数据库。各数据库服务的能力不同，不能把“列在 EC57 中”解释成“每个仅做 QRS/PVC 的设备必须对五库全部计算同一五项”。最终应按已声明能力和授权标准的 required/optional tables 选取。

| 数据库 | 官方/权威描述 | 对本项目的作用 |
|---|---|---|
| AHA DB | 80 条、每条 35 分钟；二通道动态 ECG，最后 30 分钟逐搏标注 | VEB/PVC 检测核心标准库；完整库并非 PhysioNet 公共下载，需核实 ECRI 获取与许可 |
| MIT-BIH Arrhythmia DB | 48 条半小时、47 名受试者、二通道、360 Hz，约 11 万专家逐搏标注 | QRS/VEB 核心公开验证库；按 canonical 排除规则形成报告集 |
| NST DB | 12 条半小时噪声测试记录/不同 SNR 派生记录 | QRS/VEB 抗噪声压力测试 |
| CU DB | 35 条约 8 分钟记录 | 持续性室性心律失常能力扩展 |
| ESC ST-T DB | 90 条约 2 小时记录 | 自动 ST 测量声明；不应拿来代替 QRS/VEB 核心库 |

来源：[PhysioNet ECG Databases](https://www.physionet.org/physiotools/wag/evnode3.htm)、[MIT-BIH Arrhythmia Database v1.0.0](https://physionet.org/content/mitdb/1.0.0/)、[AHA Database 权威说明及样例记录](https://physionet.org/content/ahadb/1.0.0/)、[WFDB Applications Guide](https://www.physionet.org/files/wfdb/10.7.0/wag.pdf)

FDA 对心律失常检测器的额外建议包括：至少用两个数据库评估；用于开发算法的数据库不应再用于验证其性能；如果使用 EC57 之外的库，应说明数据库开发和标注质量。它还建议实际患者波形和至少三名合格心脏科医生标注。这些是申报级验证约束，不能由 PTB-XL 训练分数替代。[FDA 特殊控制指南，第 10 节](https://www.fda.gov/medical-devices/guidance-documents-medical-devices-and-radiation-emitting-products/arrhythmia-detector-and-alarm-class-ii-special-controls-guidance-document-industry-and-fda-staff)

对本项目要求的五项 QRS/VEB 指标，建议把 **MIT-BIH + AHA** 固定为逐拍主报告，把 **NST** 固定为最低噪声压力报告；CU 与 ESC 只在新增持续性室性事件或 ST 声明时进入相应报告。AHA 的公开说明还提到 80-record development set 和 75-record withheld test set；PhysioNet 只开放一条最终被排除的样例，不能把该样例当作 AHA DB 完整测试。[AHA Database 权威说明](https://physionet.org/content/ahadb/1.0.0/)

## 6. 与当前 PTB-XL 五超类模型的边界

本项目当前合同是：`12×1000`（12 导联、100 Hz、10 秒）输入，输出 `NORM/MI/STTC/CD/HYP` 五个定点 logits，任务为记录级多标签分类。[本地 I/O 合同](../../contracts/ecg_io_contract.json)

它与 EC57 QRS/VEB 任务至少有四个根本差异：

| 当前 PTB-XL 任务 | EC57 QRS/VEB 任务 |
|---|---|
| 10 秒记录级诊断超类 | 连续 ECG 的逐心搏事件 |
| 输出五个记录级 logits | 输出 QRS 时间点及每搏 AAMI beat class |
| 主要指标 AUROC/AUPRC/F1 | QRS Se/+P、VEB Se/+P/FPR |
| 十二导联静态 ECG、100 Hz | 标准库多为二导联 Holter、250/360 Hz，含学习期、噪声和长时序 |

所以不能把 PTB-XL 的 `MI/STTC/CD/HYP` 结果改名成 VEB，也不能从 10 秒记录是否异常推导 QRS `TP/FN/FP`。若用户将“心率与 PVC 检测”列为产品目标，应新增一个独立但可共享底层特征的流式任务：

```text
ECG stream
  -> signal quality / lead selection
  -> QRS detector: emit sample_index
  -> beat window extractor
  -> beat classifier: N / V / F / S / Q
  -> rhythm/heart-rate state machine
  -> WFDB test annotations
  -> bxb + sumstats EC57 report

12-lead 10 s block
  -> existing PTB-XL five-superclass classifier
  -> NORM / MI / STTC / CD / HYP logits
```

两条任务可以后续做多任务训练或共享量化卷积核，但数据、输出契约、指标和法规声明必须分开。对 QN88 FPGA，首轮 EC57 硬件目标应先限定为“流式 QRS 时间点 + N/V beat class”，再决定是否扩展 F/S/Q、节律运行和 ST 测量。

## 7. 建议固化的评测产物

每次训练、量化或板端优化均应使用新的 `run_id`，并按项目强制追溯规则在运行前冻结原因和门槛。EC57 分支至少产生：

1. `dataset_manifest.json`：数据库名/版本/许可、记录清单、排除清单与理由、文件 SHA-256；
2. `evaluation_contract.yaml`：算法/固件/bitstream 哈希、采样率、导联选择、预处理、阈值、refractory period、AAMI 映射、WFDB 版本、标准模式参数；
3. `reference_annotations/` 与 `test_annotations/`：原始 WFDB annotation，不只保存最终百分比；
4. `bxb_per_record.txt`：逐记录混淆计数、五项指标和 shutdown；
5. `bxb_mismatches/`：`bxb -o` 产生的差异标注以及失败波形索引；
6. `sumstats_<database>.txt`：MIT、AHA、NST/CU（如适用）各自的 Sum/Gross/Average；
7. `metrics.json`：字段固定为 `qrs_se_percent`、`qrs_ppv_percent`、`veb_se_percent`、`veb_ppv_percent`、`veb_fpr_percent`，补充项使用 `veb_fp_per_hour`；
8. `board_trace.bin/jsonl`：板端每个输出的输入 sample index、检测 sample index、beat class/logit、串口丢包/溢出/复位状态；
9. `reproducibility.md`：可复现命令、工具版本、主机/FPGA 执行边界、运行日志与已知偏差；
10. `decision.md` 或对应 iteration record：与冻结门槛对比，结论只允许接受、回到训练、回到量化、回到 RTL/数据通路之一。

## 8. 实施前的硬门禁

- 取得并由合适人员核对授权版 `ANSI/AAMI EC57:2012/(R)2020`，冻结适用于本产品声明的 required/optional 表项与排除记录；
- 明确 intended use：研究型 QRS/PVC 演示、动态心电分析、患者监护报警还是诊断心电；不同声明不能共用一句“符合 EC57”概括；
- 训练库和正式验证库隔离；如果 MIT-BIH 被用于训练或调参，它只能作为开发结果，不能再宣称为独立验证；
- 先在 PC 上用固定 annotation golden 通过官方 `bxb/sumstats`，再验证量化软件输出，最后验证 FPGA 输出；
- 板端报告必须覆盖连续流边界、记录开始/结束、串口丢包、缓存溢出和复位；PC 上重放成功不等于硬件完成 EC57 验证；
- 没有完整 AHA DB 的合法副本、未按授权标准核对记录列表、或改过 150 ms 窗口时，只能称“EC57 风格内部评测”，不能称“完成 EC57 符合性测试”。

## 一手来源索引

1. AAMI，ANSI/AAMI EC57:2012/(R)2020 目录：[AAMI](https://aami.org/standard/ansi-aami-ec572012-r2020-pdf/)
2. ANSI，现行版本与历史：[ANSI Webstore](https://webstore.ansi.org/standards/aami/ansiaamiec572012r2020)
3. ANSI/AAMI，合法标准预览：[Preview PDF](https://webstore.ansi.org/preview-pages/AAMI/preview_ANSI%2BAAMI%2BEC57-2012%2B%28R2020%29.pdf)
4. FDA，认可共识标准 3-118：[Recognized Consensus Standards Database](https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfStandards/detail.cfm?standard__identification_no=31679)
5. FDA，共识标准的自愿性与申报使用：[Division of Standards and Conformity Assessment](https://www.fda.gov/medical-devices/premarket-submissions-selecting-and-preparing-correct-submission/division-standards-and-conformity-assessment)
6. FDA，心律失常检测器特殊控制：[Arrhythmia Detector and Alarm Guidance](https://www.fda.gov/medical-devices/guidance-documents-medical-devices-and-radiation-emitting-products/arrhythmia-detector-and-alarm-class-ii-special-controls-guidance-document-industry-and-fda-staff)
7. PhysioNet，MIT-BIH Arrhythmia Database：[MIT-BIH v1.0.0](https://physionet.org/content/mitdb/1.0.0/)
8. PhysioNet，AHA Database 权威说明：[AHA sample/excluded record page](https://physionet.org/content/ahadb/1.0.0/)
9. PhysioNet，标准数据库与评测协议：[WFDB Applications Guide](https://www.physionet.org/files/wfdb/10.7.0/wag.pdf)
10. PhysioNet，AAMI 逐拍比较器：[bxb manual](https://physionet.org/physiotools/wag/bxb-1.htm) 与 [`bxb.c`](https://physionet.org/files/wfdb/10.7.0/app/bxb.c)
11. PhysioNet，汇总工具：[sumstats manual](https://physionet.org/physiotools/wag/sumsta-1.htm) 与 [`sumstats.c`](https://physionet.org/files/wfdb/10.7.0/app/sumstats.c)
