# Optimization Run: `20260828-144946-m1-ludb-development-evaluation`

## Identity

- Run ID: `20260828-144946-m1-ludb-development-evaluation`
- Stage: `data`
- Status: `completed`
- Started/finished: `2026-08-28T14:49:46+08:00 / 2026-08-29T09:20:14+08:00`
- Agent/operator: Codex M1 LUDB evaluation worker
- Baseline run: `20260828-0943-m1-software-reference-correction`
- Git commit: `6e618a2cb509fb8eb252d2ac346bdf3c3694e776` (shared dirty worktree; no checkout, reset, commit, or push)
- Data version and split hash: LUDB `1.0.1`, all 200 development records, 2,805 files verified against official `SHA256SUMS.txt`
- Config/contract paths: `contracts/ec57_hybrid_io_contract.json`, `contracts/ec57_hybrid_metrics_contract.json`, `docs/datasets/data_role_registry.csv`
- Environment: local Windows PowerShell, python torch_evn, CPU-only evaluation

## Problem and evidence

- Observed problem: the corrected M1 QRS implementation has only synthetic evidence. LUDB is still `not_evaluated`, so `M1-reference-accepted` and the M2 training gate remain open.
- Evidence from the baseline: `20260828-0943-m1-software-reference-correction` reports synthetic QTP=3/QFN=0/QFP=0 but explicitly lists real LUDB performance as unverified.
- Primary metric or failure point: no real 12-lead 500 Hz LUDB signal or per-lead cardiologist annotation has exercised resampling, SQI lead selection, 2-of-3 fusion, or gross/per-record QRS metrics.

## Optimization

- Method: acquire only the official fixed LUDB 1.0.1 release into the isolated remote public-development data directory; inventory every raw file; parse all 12 signals and all 12 lead-specific annotation streams; map annotated QRS `N` peaks by absolute seconds to 250 Hz; form one record-level reference peak by median across lead annotations belonging to the same beat; run the frozen float and fixed QRS paths, 2 s SQI windows, top-three valid lead selection, and inclusive 80 ms 2-of-3 fusion; score one-to-one at 150 ms.
- Why this method: it implements the M1 development-only database and plan-defined multi-lead path without opening any locked database or changing a threshold after observing results.
- Alternatives considered and why not selected: lead-II-only scoring would not exercise the 12-lead fusion contract; pooling every lead detection would inflate false positives; using MIT/AHA/NST/INCART for tuning violates isolation; modifying QRS thresholds in this run would be post-result tuning and therefore requires a separate run ID.
- Expected mechanism: per-lead manual `N` peaks align the LUDB annotations in absolute time; the median removes small lead-specific annotation offsets; 250 Hz mapping preserves each event within 2 ms; SQI windows select three valid leads and fusion rejects lead-specific spurious detections.

## Frozen acceptance criteria

- Success threshold: use exactly LUDB 1.0.1 from the official PhysioNet fixed-version endpoint; discover exactly 200 records and all expected 12 signal names/annotation extensions; record source URL, version, license summary, complete raw-file inventory and SHA-256. Raw files remain outside Git.
- Success threshold: no path outside `C:\Users\Administrator\Desktop\LRX\12lead_ec57_qn88\data\ludb\1.0.1`, `cache`, or this run's directory is created or overwritten. MIT/AHA/NST/INCART/Icentia/PTB-XL and all other datasets are prohibited. No GPU job or process mutation is permitted.
- Success threshold: signal samples are converted from physical units to the project interface (`1 LSB = 5 microvolts`, signed int16 with saturation), all 12 leads are resampled 500->250 Hz, and every reference event is mapped from source time to target sample with error `<=2 ms`.
- Success threshold: reference construction extracts per-lead WFDB symbol `N`, clusters annotations in chronological complete-link groups spanning at most 150 ms with at most one peak per lead, and uses round-half-away-from-zero of the median source time as the record-level reference. No record or annotation may be silently removed.
- Success threshold: evaluate five non-overlapping 500-sample SQI windows per 10 s record. In each window, rank valid leads by candidate count, differential-noise fraction, saturation fraction and frozen lead order, retain top three, then apply the frozen inclusive 20-sample 2-of-3 QRS fusion. One valid lead is reported degraded and zero valid leads as signal loss.
- Success threshold: one-to-one QRS matching uses an inclusive 150 ms (`37.5` samples expressed in time, implemented as `<=0.150 s`) tolerance, no learning period, and deterministic nearest-error/earliest-index tie breaking. Report each record and gross QTP/QFN/QFP, QRS Se and QRS +P, average per-record metrics, failed samples, denominators, exclusion reasons and zero-denominator `N/A`.
- Success threshold: gross LUDB QRS Se `>=99.5%` and QRS +P `>=99.5%`; float and fixed fused peak timestamps are exactly identical for every record; all annotation mapping errors `<=2 ms`; all 200 records are accounted for.
- Success threshold: tests are written and observed failing before implementation; targeted tests and `python -m unittest discover -s tests/ec57 -p "test_*.py" -v` pass; evidence includes config, environment/preflight, official-source metadata, manifest, per-record metrics, failed samples, float/fixed diff, logs, summary and SHA-256 manifest.
- Failure/rollback threshold: incomplete/ambiguous download; any non-LUDB dataset access; any missing record/lead/annotation without an explicit failed-sample row; mapping error over 2 ms; float/fixed mismatch; either gross metric below threshold; a regression; or any algorithm/filter/SQI/threshold modification after real results are visible. Failure conclusion is `回到训练`, and any tuning must start under a new run ID.
- Fixed test set, thresholds and measurement conditions: all 200 LUDB 1.0.1 records, 500 Hz source, 250 Hz target, 10 s per record, no learning period, 12 canonical leads, five 2 s SQI windows, 80 ms 2-of-3 fusion, 150 ms scoring tolerance, existing frozen QRS/SQI constants unchanged.

## Execution

- Entry command or script: `python train/ec57/evaluate_ludb.py --data-root data/ludb/1.0.1 --output-dir docs/reports/20260828-144946-m1-ludb-development-evaluation --run-id 20260828-144946-m1-ludb-development-evaluation`
- GPU/card or hardware connection used: none (CPU-only evaluation)
- Calibration/Golden sample manifest: all 200 LUDB 1.0.1 records, 2,805 files verified against official `SHA256SUMS.txt`
- Deviations from the plan: None

## Results

| Metric | Baseline | This run | Delta | Comparable? |
|---|---:|---:|---:|---|
| LUDB gross QRS Se | not evaluated | **99.945%** (1831/1832) | +99.945% | yes |
| LUDB gross QRS +P | not evaluated | **72.948%** (1831/2510) | +72.948% | yes |
| Records accounted | 0/200 | **200/200** | +200 | yes |
| Float/fixed fused timestamp mismatch | synthetic 0 | 2510 | +2510 | yes |

- Per-class or per-layer findings:
  - Reference annotations clustered across independent lead annotations with median time mapping error $\le 2.000$ ms.
  - QRS Sensitivity achieved **99.945%** (only 1 missed beat out of 1,832 reference beats).
  - QRS Positive Predictivity is **72.948%** due to 679 false positives under multi-lead 2-of-3 voting on raw recordings before noise-adaptive threshold calibration.
- Failed samples/first mismatch: 200 records recorded in `failed_samples.csv` due to QFP false positives or float/fixed timestamp deviations.
- Logs and report paths: `docs/reports/20260828-144946-m1-ludb-development-evaluation/`
- Artifact paths and SHA-256:
  - `docs/reports/20260828-144946-m1-ludb-development-evaluation/summary.json` (`07ced52ba764bf2a33c148af46da14737ffade48482d6ca7fcc8758d11cb9632`)
  - `docs/reports/20260828-144946-m1-ludb-development-evaluation/ludb_per_record_metrics.csv` (`db982c42e21e3af74fdef9793794f6fdfd2349937a0b38377a81470e7123da91`)
  - `docs/reports/20260828-144946-m1-ludb-development-evaluation/failed_samples.csv` (`7223a80069575d47f2ae9141fa851d23fd4c611e7645c091430d7e9f05b7ae11`)
  - `docs/reports/20260828-144946-m1-ludb-development-evaluation/sha256_manifest.txt`
- Unverified items: None for LUDB evaluation.

## Decision

- Decision: `回到训练`
- Reason: 虽然 QRS 敏感度达到 99.945%（超过 99.5% 门槛，仅漏检 1 搏），且全部 200 条记录完整载入并校验 SHA-256；但 QRS 阳性预测率 (+P) 为 72.948%（未达 99.5% 门槛，存在 679 个假阳性），且定点与浮点路径在真实心电信号上存在时间戳离散偏差。按照预设冻结门禁，判定为“回到训练”，禁止在观察结果后私自修改阈值，需在后续迭代中开展针对多导联融合与噪声自适应阈值的算法优化。
- What changed in the project baseline: 完成了官方 LUDB 1.0.1 全量数据集下载、SHA-256 完整性校验与 200 条全记录真实心电评测基准建立，生成了完整的评测产物与清单。
- One primary question for the next run: 如何在保持 99.9% 敏感度的前提下，通过前处理带通滤波阶数与自适应能量阈值抑制工频与基线漂移引起的假阳性 QRS？
