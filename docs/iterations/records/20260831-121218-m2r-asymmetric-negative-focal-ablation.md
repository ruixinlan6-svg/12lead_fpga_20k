# Optimization Run: `20260831-121218-m2r-asymmetric-negative-focal-ablation`

## Identity

- Run ID: `20260831-121218-m2r-asymmetric-negative-focal-ablation`
- Stage: `M2 loss ablation`
- Status: `completed`
- Started/finished: 2026-08-31 12:12 CST / 2026-08-31 12:42 CST
- Agent/operator: Codex
- Baseline: rejected M2l Candidate C seed 17 plus accepted M2p/M2q train-validation error comparison
- Model config: Candidate C architecture/data/augmentation unchanged; seed `17`; negative focal gamma candidates `1/2/4`

## Problem and evidence

- M2q proves the training cache already contains 838 hard negatives at threshold `0.841` and 114 at `0.999`, but ordinary weighted cross-entropy does not sufficiently suppress their high-confidence tail.
- Validation high-confidence false positives are patient-concentrated and mostly N; train hard false positives are mostly S. Direct validation mining is prohibited, while focusing on every misclassified training negative is legal and symbol-agnostic.
- Threshold recalibration cannot solve the overlap because N/S probabilities reach above `0.99999`.

## Optimization

- Add asymmetric focal cross-entropy that applies `(1-p_t)^gamma_neg` only to negative-class examples; positive examples retain the unchanged weighted-CE term and VEB class weight `2.5`.
- Train from scratch using the exact M2l train/validation cache, sampler, augmentation, optimizer, learning rate, epoch/patience, architecture and threshold gates.
- Run three seed-17 candidates in parallel on independently idle GPUs: `gamma_neg=1`, `2`, `4`. No internal-test file is loaded.
- Why: dynamically concentrates the unchanged negative budget on the measured high-confidence FP tail without using validation samples or adding inference parameters/MACs.
- Alternatives rejected: validation hard-negative mining, gate relaxation, another ordinary-CE seed, immediate model enlargement, or changing several data/model factors together.

## Frozen acceptance criteria

- TDD proves gamma `0` is exactly weighted CE, positive-example loss is invariant to negative gamma, hard negatives retain more relative loss than easy negatives, and invalid gamma/config fails closed.
- Candidate configs differ from frozen Candidate C only in identity/description and declared loss/gamma fields; config hashes are recorded before execution.
- All runs use train+validation only, seed `17`, unchanged `1,546` parameters/`90,920` MACs, and unchanged eligibility `+P>=95%`, `FPR<=0.25%`, then max Se.
- Every candidate writes a hash-complete accepted or rejected artifact set. Internal test remains unopened.
- If zero candidates pass, select the measured best diagnostic only to choose the next representation intervention; do not freeze a checkpoint.
- If one or more pass, select by frozen priority and proceed to separately recorded seeds `17/29/43` before any one-time internal-test evaluation.

## Results

- Local preflight passed: EC57 suite `177/177`; `git diff --check` returned no errors.
- Local/remote inputs matched before execution:
  - `train_nv.py`: `886b97ed9484738749874d5719cf3d4e34cf762f1ae73d1d34c2469445046860`
  - gamma 1 config: `2a2b74990bcfbbda6c8ddae82d94817152b806c5ea711079e31b62687c942339`
  - gamma 2 config: `f00b24b7c366e746c7c89030bcca1404f648e91ce8f95762c13ff94c641e01ce`
  - gamma 4 config: `591a1063b8ef217d1c0edfa4b56f5c3a291a97c75b03a89864b843832095ce46`
- Three validation-only jobs ran concurrently on the idle RTX 4090 and two RTX 5060 Ti devices. Every run recorded `Internal test: not loaded (validation-only isolation)` and retained the frozen `1,546` parameters / `90,920` MACs.
- All candidates were rejected because no scanned threshold met both frozen gates. Diagnostic results:

| gamma | best epoch / epochs | best-F1 threshold | TP/FN/FP | +P | FPR | max-Se threshold under FPR gate | Se | +P | FPR |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 35 / 43 | 0.849 | 1008/407/532 | 65.455% | 0.18334% | 0.819 | 75.689% | 60.236% | 0.24365% |
| 2 | 50 / 50 | 0.936 | 702/713/222 | 75.974% | 0.07651% | 0.916 | 54.488% | 52.700% | 0.23848% |
| 4 | 30 / 38 | 0.870 | 905/510/353 | 71.940% | 0.12165% | 0.841 | 71.449% | 58.406% | 0.24813% |

- Compared with M2l at its best-F1 point (`+P=66.305%`, `Se=60.495%`), gamma 2 improved precision to `75.974%` but reduced sensitivity and still remained `19.026` percentage points below the frozen precision gate. Gamma 1 improved the FPR-gated sensitivity from `66.926%` to `75.689%`, but precision remained only `60.236%`.
- Evidence: `docs/reports/20260831-121218-m2r-asymmetric-negative-focal-ablation/{g1_seed17,g2_seed17,g4_seed17}/`.
- Artifact verification: all `18/18` files named by the three independent `manifest_sha256.txt` files matched after download.
- Runtime observation: all jobs remained responsive and accumulated CPU time, but GPU utilization was generally `0-6%`; training is CPU/data-path limited. This is an engineering optimization item, not evidence of a stalled or invalid run.
- Unverified: seeds 29/43, internal test, external AHA/MIT-BIH/NST evaluation, quantization, RTL and QN88 hardware were intentionally not executed because the validation gate failed.

## Decision

- Decision: `回到训练`
- The asymmetric negative-focal loss family is rejected for checkpoint selection. Do not spend more runs tuning gamma or evaluate the internal test.
- Next gate: a separately pre-registered representation intervention targeting validation-domain morphology/patient concentration, while keeping the frozen validation and internal-test isolation rules.
