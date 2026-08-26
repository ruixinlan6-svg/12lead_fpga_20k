# M1 PTB-XL FP32 基线

这组脚本只负责建立软件参考，不包含 FPGA 下载或 Flash 写入。

## 数据目录

数据应放在远端私有目录，例如：

```text
C:/Users/Administrator/Desktop/LRX/12lead_fpga_20k_m1/data/ptb-xl/1.0.3/
```

脚本会下载 PTB-XL 1.0.3 的元数据和 `records100/*_lr` 信号文件。数据本体、缓存和 checkpoint 不进入 Git 仓库。

## 运行顺序

```powershell
python download_ptbxl.py --root C:/.../data/ptb-xl/1.0.3
python make_registry.py --root C:/.../data/ptb-xl/1.0.3 --output C:/.../runs/<run_id>
python ptbxl_baseline.py --root C:/.../data/ptb-xl/1.0.3 --registry C:/.../runs/<run_id>/data_registry.yaml --run-dir C:/.../runs/<run_id>/seed0 --seed 0 --device cuda:0
python ptq_int8.py --root C:/.../data/ptb-xl/1.0.3 --registry C:/.../runs/<run_id>/data_registry.yaml --checkpoint C:/.../runs/<run_id>/seed0/checkpoint_best.pt --output C:/.../runs/<run_id>-ptq
```

`data_registry.yaml` 使用 JSON-compatible YAML，便于只依赖 Python 标准库读取；训练脚本只依赖远端环境已有的 PyTorch、WFDB 和 NumPy。

首轮先跑单个 seed 的 smoke test，确认数据读取和标签映射，再按 M1 门禁使用至少两个 seed。启动每个远端候选前必须重新检查 GPU 进程，并把配置、指标、checkpoint SHA-256 和日志写入同一个 `runs/<run_id>`。

`make_registry.py --available-only --max-per-split N` 可在数据尚未完整落盘时生成有界 smoke registry；该结果只能验证软件链路。`ptq_int8.py` 会输出 `quantization_contract.json`、`weights_int8.pt`、`golden_vectors.npz` 和 `metrics_int8.json`，其舍入/饱和语义与 M3 的 RTL 单元一致。
