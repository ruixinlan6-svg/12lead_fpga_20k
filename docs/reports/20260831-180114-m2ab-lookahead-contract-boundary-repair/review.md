# M2x–M3a post-RR 研究中央审查

审查基线：`b1d5b9150a158025cb36134c78d7db2a0f7a9e3e`；审查对象为尚未提交的 M2x、M2y、M2z、M3a 代码、记录和报告。

## 结论

`partial_accept / 回到数据契约后重新训练`。研究证明 post-RR、非线性交互和显式 RR 耦合值得继续，但现有数值只能作为探索性证据，不能关闭 M2：所有候选均没有同时达到验证集 `VEB Se >= 90%`、`VEB +P >= 95%`、`VEB FPR <= 0.25%`；最接近的高精度点为 `+P=90.00%`，但 `Se=34.98%`。

## 独立规范审查结果

- P0：等待 `R[i+1]` 与旧 `beat_output_latency_max_ms=450`、4 特征 I/O 契约冲突；必须版本化，不得静默覆盖 v1。
- P1：原实现给首搏 `pre_rr=250`、末搏 `post_rr=median_rr`，并用测试固化三搏全保留，末搏并没有真实的一搏前瞻。
- P1：M2z/M3a 扩展 MLP 和 8 特征后没有同步共享契约。
- P2：报告 manifest 引用被 Git 忽略的 checkpoint/cache，公开工作树只能验证摘要与哈希，不能单独重放全部前向过程。

## 独立工程标准审查结果

- P0：6/8 特征改变了冻结接口和最坏等待时间，未建立新门禁。
- P1：四轮记录缺少完整 Git commit、环境、精确命令、失败样本以及可公开复核的产物集合。
- P1：约 44 MB 的数据库派生 NPZ（含 internal_test）不得进入公共 Git；本次确认 `.gitignore` 已排除 `*.npz`。
- P1：模型预算测试原先只覆盖参数/MAC，漏掉 8 KiB 权重包、2 KiB 最大单层激活，并意外移除了 forbidden-layer 回归测试。
- 代码异味：多个分析脚本高度重复，特征数量与位置数组分支分散；在 M2 门禁通过前不做无关重构。

## 已执行纠正

- 新增 `contracts/ec57_hybrid_io_lookahead_v2.json`，明确目标搏仍为 `R[i]`，输出由 `R[i+1]` 触发，总延迟为 post-RR 加分类计算延迟，超时输出 `UNCLASSIFIED_BEAT`。
- 恢复 4 特征为构建器和 CLI 默认；6/8 特征必须显式选择。
- lookahead 样本必须同时具有真实前一搏和后一搏；首末边界排除并计数，不再合成 RR。
- cache 增加精确 `feature_names`、`feature_contract_id`、`decision_latency_mode` 与上下文采样索引；训练配置/缓存宽度不一致时失败关闭。
- 恢复 forbidden-layer 测试，并增加权重包、激活、特征宽度和 v2 契约测试。
- 本地全套 EC57 测试在修复后重新运行；最终计数和哈希见对应迭代记录。

## 仍未验证

修复后的真实缓存重建、GPU 重训、三随机种子、internal_test、PTQ/QAT、整数 golden、RTL、综合、SRAM/HIL、EC57 锁定数据库均未在本审查结论中宣称通过。
