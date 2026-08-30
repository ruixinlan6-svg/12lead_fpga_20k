# Optimization Run: `20260829-1815-m1-m2-central-audit-correction`

## Identity

- Run ID: `20260829-1815-m1-m2-central-audit-correction`
- Stage: `audit/algorithm`
- Status: `completed`
- Started/finished: `2026-08-29T18:15:00+08:00 / 2026-08-29T18:22:52+08:00`
- Agent/operator: Codex Central Audit and Correction Specialist
- Baseline run: `20260829-1215-m2-veb-candidate-ablation` (with M1e baseline `20260829-1100-m1e-twave-and-span-optimized-qrs`)
- Git commit: dirty worktree (preserving existing worktree and uncommitted changes)
- Data version and split hash: Official LUDB `1.0.1` (all 200 development records, 2,805 files verified against `SHA256SUMS.txt`), `cache_ec57_beats_v1`
- Config/contract paths: `contracts/ec57_hybrid_io_contract.json`, `contracts/ec57_hybrid_metrics_contract.json`, `docs/datasets/data_role_registry.csv`
- Environment: local Windows PowerShell, Python 3.10.16 (`torch_evn`), CPU-only evaluation

## Problem and evidence

- Observed problems:
  1. **Evaluation Span Reference Clipping in `evaluate_ludb.py`**:
     - In `M1e`, `train/ec57/evaluate_ludb.py` constructed `evaluation_span = (min(reference_indices_250) - 37.5, max(reference_indices_250) + 37.5)`.
     - In LUDB 10-second recordings, human annotations typically cover central beats (e.g. 1.0s to 8.5s). Clipping evaluation to this window dropped 322 out of 339 false positive detections outside the reference span from the denominator, artificially inflating Gross +P from 84.327% to 99.563%.
     - This violated the frozen contract in Section 1.2 & 3.1 of the project plan: LUDB 10-second development evaluation must score the entire 10-second recording with `learning_period_s=0` without clipping based on reference answers.
  2. **Float/Fixed Self-Comparison in `qrs_detector.py`**:
     - In `M1e`, `train/ec57/qrs_detector.py`'s `detect_qrs_float` was modified to directly instantiate `CausalPureIntegerQRSDetector` and round inputs to `int`.
     - This caused float/fixed mismatch to report 0 as a self-comparison rather than an independent floating-point algorithmic reference.
  3. **Missing Causal Searchback in `CausalPureIntegerQRSDetector`**:
     - The detector maintained `searchback_indices` and `rr_history` state, but its streaming `step()` method did not implement the planned $1.66 \times \text{median RR}$ searchback to recover sub-threshold beats.
  4. **Test Suite Deficiencies**:
     - Tests did not sufficiently verify independent prefix vs full-run execution, arbitrary chunk split equivalence on multiple deterministic waveforms, fail-closed behavior on float inputs for fixed-point paths, or output irrevocability.
  5. **Invalid Milestone Acceptance and Revocation Requirements**:
     - `M1e` (`20260829-1100-m1e-twave-and-span-optimized-qrs.md`) was falsely accepted and marked M1 as closed based on the clipped evaluation span.
     - `M2` (`20260829-1215-m2-veb-candidate-ablation.md`) was falsely accepted and frozen, even though all 3 seeds severely violated the frozen gates (Seed 17: Se 50.87%, +P 31.77%, FPR 8.67%; Seed 29: Se 42.94%, +P 40.84%, FPR 4.94%; Seed 43: Se 55.05%, +P 31.56%, FPR 9.47% vs required Se $\ge 90.0\%$, +P $\ge 95.0\%$, FPR $\le 0.25\%$, seed span $\le 2.0\%$).

## Optimization

- Method:
  1. **Restore Full 10-Second Record LUDB Evaluation**:
     - In `train/ec57/evaluate_ludb.py`, removed `evaluation_span` reference clipping and passed `evaluation_span=None` with `learning_period_s=0`. All detections across the full 10-second window are evaluated against references without clipping based on reference answers.
  2. **Restore Independent Floating-Point QRS Reference**:
     - In `train/ec57/qrs_detector.py`, restored `detect_qrs_float` to use the true independent floating-point pipeline (`qrs_filter_float`, `_moving_integral_float`, `_adaptive_candidates`, `apply_refractory_and_searchback_float`).
  3. **Implement Strictly Causal Pure-Integer 1.66×Median RR Searchback**:
     - In `CausalPureIntegerQRSDetector.step()`, maintain valid RR history; when no primary QRS is detected for $(n - \text{last\_peak\_sample}) \times 100 \ge 166 \times \text{median\_rr}$, causally search back for eligible sub-threshold candidates ($\ge 50$ samples post-R), commit the best candidate, update state and threshold, and emit the peak irrevocably.
  4. **Enforce Fail-Closed on Float and Bool Inputs for Fixed-Point Paths**:
     - Ensure `detect_qrs_fixed`, `CausalPureIntegerQRSDetector.step`, `qrs_filter_fixed`, and `qrs_energy_fixed` reject non-integer, float, and boolean inputs with `QRSReferenceError`.
  5. **Strengthen Test Suite**:
     - Added tests comparing independent prefix runs vs full runs up to the same point (`test_prefix_invariance_independent_runs_on_diverse_waveforms`).
     - Added arbitrary chunk streaming equivalence tests across diverse deterministic waveforms and random seeds (`test_arbitrary_chunk_streaming_equivalence_diverse_signals`).
     - Added fail-closed tests for float and bool inputs in fixed-point paths (`test_fixed_paths_fail_closed_on_float_and_bool_inputs`).
     - Added tests for causal searchback, startup protection, T-wave suppression, cross-window boundaries, and output irrevocability (`test_causal_streaming_searchback_recovers_subthreshold_beat`, `test_output_irrevocability_in_streaming`, `test_twave_and_startup_transient_protection`, `test_independent_float_reference_differs_honestly_from_causal_integer_reference`).
     - All 121 tests pass 100%.
  6. **Formal Revocation of M1e and M2 Acceptance**:
     - Explicitly revoke M1e acceptance / M1 closed status and M2 acceptance / M2 frozen status in this central audit record.
     - Mark M2 back to training (`回到训练`); retain M2 model checkpoints as failed experimental records; prohibit their use as input to M3.
     - Update `docs/iterations/INDEX.md` to express these revocations via this new record without rewriting historical record body text.
  7. **Full 200-Record LUDB Re-Evaluation**:
     - Re-ran all 200 LUDB records on the restored legitimate criteria and output complete reports to `docs/reports/20260829-1815-m1-m2-central-audit-correction/`.

- Why this method:
  - Restores scientific integrity and compliance with project contracts and ANSI/AAMI EC57 guidelines.
  - Prevents propagating invalid claims and unverified models to downstream quantization and FPGA RTL stages.

- Alternatives considered and why not selected:
  - Keeping reference span clipping was rejected because it conceals false positive detections.
  - Keeping float/fixed self-comparison was rejected because it prevents detecting fixed-point conversion anomalies.
  - Relaxing M2 gates or freezing the sub-par M2 model was rejected because it violates pre-frozen criteria.

## Frozen acceptance criteria

- Success threshold:
  - Full 200 LUDB records evaluated under the legitimate 10-second full-record criteria (`learning_period_s=0`, `evaluation_span=None`).
  - Gross QRS Se $\ge 99.50\%$ and Gross QRS +P $\ge 99.50\%$.
  - Float vs fixed independent path differences truthfully reported.
  - Fixed path must be 100% pure integer, strictly causal, prefix-invariant, chunk-equivalent, and fail-closed on float inputs.
  - Unit tests must pass 100%.
- Failure / rollback threshold:
  - If QRS Gross Se $< 99.50\%$ or Gross +P $< 99.50\%$ on full-record evaluation, decision must be `回到训练` (back to training) and stop immediately.
  - No CNN training, quantization, RTL development, board testing, or Flash writing permitted.

## Execution

- Entry commands:
  - `D:\software\anaconda\envs\torch_evn\python.exe train/ec57/evaluate_ludb.py --data-root data/ludb/1.0.1 --output-dir docs/reports/20260829-1815-m1-m2-central-audit-correction --run-id 20260829-1815-m1-m2-central-audit-correction`
  - `D:\software\anaconda\envs\torch_evn\python.exe -m unittest discover -s tests/ec57 -p "test_*.py" -v`
- Manifest: 200 LUDB 1.0.1 development records, `SHA256SUMS.txt` verified.
- Status: `completed`

## Results

| Metric | Target Gate | M1e Claimed (Clipped Span) | M1d Baseline (Full Record) | **This Run (Corrected Full Record)** | Status |
|:---|:---:|:---:|:---:|:---:|:---:|
| **Gross QTP (Fixed)** | - | 1,824 | 1,824 | **1,824 / 1,832** | - |
| **Gross QFN (Fixed)** | $\le 9$ | 8 | 8 | **8** | **PASSED** ($\text{Se} = 99.563\%$) |
| **Gross QFP (Fixed)** | $\le 9$ | 8 (clipped) | 339 | **333** | **FAILED** (+P gate not met) |
| **Gross QRS Se (Fixed)** | $\ge 99.50\%$ | 99.563% | 99.563% | **99.563%** | **PASSED** |
| **Gross QRS +P (Fixed)** | $\ge 99.50\%$ | 99.563% (false) | 84.327% | **84.562%** | **FAILED** (requires Route 2 Veto) |
| **Average QRS Se (Fixed)**| $\ge 99.50\%$ | 99.556% | 99.556% | **99.556%** | **PASSED** |
| **Average QRS +P (Fixed)**| $\ge 99.50\%$ | 99.591% (false) | 83.954% | **84.182%** | **FAILED** |
| **Gross QTP (Float)** | - | 1,824 | - | **1,830 / 1,832** | - |
| **Gross QFN (Float)** | - | 8 | - | **2** ($\text{Se} = 99.891\%$) | - |
| **Gross QFP (Float)** | - | 8 | - | **657** ($\text{+P} = 73.583\%$) | - |
| **Float/Fixed Mismatches** | 0 (self-compare in M1e) | 0 | - | **1,672 (Independent diffs)** | **REPORTED** |
| **Pure Integer / Causal** | Required | Int/Causal | Int/Causal | **100% Int, Causal Searchback, 121/121 PASS** | **CLOSED** |

- Per-class findings:
  1. **QRS 敏感度 (Gross Se) 稳定保持达标（99.563% $\ge 99.50\%$）**：全库 200 条记录中，仅记录 `data/74` 存在 8 处由于微伏导数衰减引起的漏检（QFN=8），其余 199 条记录全部 100% 检出。
  2. **QRS 阳性预测率 (Gross +P) 为 84.562%（333 QFP），未达 $\ge 99.50\%$ 门槛**：
     - 在恢复整条 10 秒无裁剪评测后，证明了绝大多数 QFP 是由于人工标注未延伸至 10 秒整段首尾造成的非标注生理心搏，以及部分病理高尖 T 波。
     - 纯前端 DSP 滤波无法通过单一全局/动态阈值在整记录口径下将 QFP 压减至 $\le 9$。必须在下一阶段通过路线 2（轻量级候选特征门控 / Veto 判别器）进行二次甄别。
  3. **独立浮点参考真实呈现算法差异**：浮点参考与因果定点在 200 条记录上产生 1,672 处独立差异，彻底消除了 M1e 的同实现自比较假象。
  4. **单元测试集全面强化**：121 项单元测试全部通过（121/121 PASS），覆盖了前缀独立运行等价、任意 chunk 分割等价、浮点/布尔 fail-closed 拦截、因果 searchback、启动保护、T 波抑制与输出不可撤回性。

### 撤销声明 (Revocation Statements)

1. **撤销 M1e 验收与 M1 闭环结论**：
   - 撤销 `20260829-1100-m1e-twave-and-span-optimized-qrs.md` 中的 `接受` 与 `M1-reference-accepted` 结论。
   - M1 阶段状态恢复为未通过/开启（`milestone: M1-reference-open`，`decision: 回到训练`）。
2. **撤销 M2 候选模型验收与模型冻结结论**：
   - 撤销 `20260829-1215-m2-veb-candidate-ablation.md` 中的 `接受` 与 `M2-fp32-model-frozen` 结论。
   - M2 三个随机种子实测指标（Se 42.935%~55.046%、+P 31.561%~40.840%、FPR 4.937%~9.474%）严重未达到冻结门槛（Se $\ge 90.0\%$, +P $\ge 95.0\%$, FPR $\le 0.25\%$, 种子跨度 $\le 2.0\%$）。
   - M2 状态恢复为未通过/回到训练（`decision: 回到训练`）。
   - M2 产出的 checkpoint `model_fp32.pt`（种子 17, 29, 43）仅保留作为失败实验档案，严禁作为 M3 量化、RTL 生成或硬件部署的输入。

- Logs and report paths: `docs/reports/20260829-1815-m1-m2-central-audit-correction/`
- Artifact paths and SHA-256:
  - `docs/reports/20260829-1815-m1-m2-central-audit-correction/summary.json` (`5a51aeba0f045ea1535d97a0e84c86d6aae503c091934a51ab01810c2a386807`)
  - `docs/reports/20260829-1815-m1-m2-central-audit-correction/ludb_per_record_metrics.csv` (`3d9cb935c3ec675d13e9160d6acadf3de32752edba7438de861b6e0574786de2`)
  - `docs/reports/20260829-1815-m1-m2-central-audit-correction/failed_samples.csv` (`4ec34819a0efd613362a17a2731868172f2ba715a2a757d8e17b525a944b74f8`)
  - `docs/reports/20260829-1815-m1-m2-central-audit-correction/float_fixed_qrs_diff.json` (`dccbef6e9ae80d531b63a141b34c4047dedad1bc7f952589a120ea255ddc3659`)
  - `docs/reports/20260829-1815-m1-m2-central-audit-correction/config.json` (`1070a9ec64856946b1db162128b3df7673a58c197638efb4ed54cf50b2cc8920`)
  - `docs/reports/20260829-1815-m1-m2-central-audit-correction/source_metadata.json` (`17e9d51bdf04052e243845d56ba1e31190bd8fb9257c0f131613c7d1360e5108`)
  - `docs/reports/20260829-1815-m1-m2-central-audit-correction/environment.json` (`7b2e77a3546f4d54bdfb4af3c3e028b3d9d07621dcea28987a43860cc4ae1d4b`)
  - `docs/reports/20260829-1815-m1-m2-central-audit-correction/annotation_counts_by_record.json` (`c3b09854574c72cfb7a403bd1f0136031209577db5bc372e4bbc0bef01a2bfd3`)
  - `docs/reports/20260829-1815-m1-m2-central-audit-correction/ludb_raw_file_manifest.json` (`3ee27e25b07aa281cf38fbef311471f5f669e795405f79dcd35b3a066a709bf7`)
  - `docs/reports/20260829-1815-m1-m2-central-audit-correction/evaluation_errors.json` (`a5338d955b09046ec0b16f3a9625b7955c763aae07dc722e474e6078745f932f`)
  - `docs/reports/20260829-1815-m1-m2-central-audit-correction/sha256_manifest.txt`
- Unverified items:
  - 未使用锁定数据库（INCART, MIT-BIH, AHA, NST）。
  - M1 与 M2 均未闭环，严禁进入 M3 量化、RTL 综合、板端部署或 Flash 烧录。

## Decision

- Decision: `回到训练` (Back to training)
- Reason:
  1. 在恢复后的 200 条 LUDB 10 秒整记录无裁剪评测中，因果定点 QRS Gross Se 为 99.563%（达标），但 Gross +P 为 84.562%（未达到 $\ge 99.50\%$ 门槛，QFP=333）。
  2. M1e 的错误结论与 M2 的不合规冻结已由本记录正式撤销；M1 保持开放，M2 回到训练，旧模型禁止流入下游。
  3. 严格遵守门禁与任务约束：立即任务在此终止，不启动任何模型训练、量化、RTL 或上板操作。
- What changed in the project baseline:
  - 纠正了 `evaluate_ludb.py` 评测口径，恢复了全 10 秒 `learning_period_s=0` 评测。
  - 纠正了 `qrs_detector.py`，恢复了真正独立的浮点参考，并为因果定点补齐了严格纯整数因果不可撤回的 $1.66 \times \text{median RR}$ searchback 与 fail-closed 类型防护。
  - 将单元测试集扩充至 121 项并全部验证通过。
  - 纠正了项目状态，撤销了虚假的 M1/M2 闭环，保持后续硬件开发的严格纪律。
- One primary question for the next run:
  - 当未来获得授权开启新训练 run 时，如何在因果纯整数前提下设计 Route 2 轻量级假阳性 Veto 判别器，使整记录 +P 突破 99.50% 并合法关闭 M1 门禁？
