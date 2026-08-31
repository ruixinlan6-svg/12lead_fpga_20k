# Optimization Run: `20260831-120736-m2q-train-domain-error-comparison`

## Identity

- Run ID: `20260831-120736-m2q-train-domain-error-comparison`
- Stage: `M2 train/validation domain diagnosis`
- Status: `completed`
- Started/finished: 2026-08-31 12:07 CST / 2026-08-31 12:12 CST
- Agent/operator: Codex
- Baseline: accepted M2p validation taxonomy on rejected M2l checkpoint
- Model config: unchanged rejected checkpoint; no training in this run

## Problem and evidence

- M2p shows high-confidence false positives are mostly native N and concentrated in a few validation patients.
- It is not yet known whether analogous high-scoring N/S negatives already exist in the training cache (sampling/loss problem) or are absent there (patient-domain/representation problem).
- Using validation errors directly as training examples would contaminate model development; the comparison must remain read-only and training examples must come only from the train split.

## Optimization

- Extend the audited inference tool to accept only `train` or `validation`, still making `internal_test` impossible through the CLI.
- Replay the exact checkpoint over the frozen train NPZ at thresholds `0.841`, `0.899`, `0.999` and produce the same full taxonomy and hashes.
- Compare train versus validation N/S/V score tails, false-positive rates and patient concentration without changing any model or cache.
- Why: choose between deterministic training-only hard-negative weighting and a new patient-generalizing representation using measured domain behavior.
- Alternatives rejected: mine validation examples, relax gates, run another seed, or alter the model before this comparison.

## Frozen acceptance criteria

- TDD proves train/validation are accepted split names and internal-test/unknown splits are rejected.
- Train replay uses the M2l train NPZ SHA-256 `762c61f7520b4d1f5cb9a0e648bee083a74c6bdf8bd2f42468a114ba869c674a`; model/config hashes remain unchanged.
- Output reports full train confusion and patient/record/native-symbol maps at all three thresholds, with an independent artifact manifest.
- No internal-test file is opened and no training or cache mutation occurs.
- The next intervention is chosen from the measured train/validation difference and gets a new run ID.

## Results

- Split-guard TDD was red before implementation and green after it; train/validation are accepted and internal-test/test/locked/empty names are rejected. Local/remote tool SHA-256 matched: `d03fc678f85960e2490f10a7004ee1ab48400eaefb80542f32528f0f39b2e695`.
- Train-only replay used the exact model/config and train NPZ SHA-256 `762c61f7520b4d1f5cb9a0e648bee083a74c6bdf8bd2f42468a114ba869c674a`; it recorded `evaluation_split=train` and `internal_test_loaded=false`.
- At threshold `0.841`, train VTP/VFN/VFP/VTN=`23072/5961/838/115301`, Se `79.468%`, +P `96.495%`, FPR `0.72155%`. Train FP were `N=224/S=614`; validation FP were `N=538/S=187`.
- At `0.899`, train=`21053/7980/675/115464`, +P `96.893%`; validation +P remained `66.305%`.
- At `0.999`, train=`8183/20850/114/116025`, +P `98.626%`; FP were `N=27/S=87`. Validation at the same threshold had `N=46/S=6` FP and +P `83.851%`.
- Train contains genuine high-confidence hard negatives, but the symbol mix reverses across domains. Train/validation N p99 scores were `0.449/0.621`; S medians were `0.0122/0.2412`. This proves both an available hard-negative learning signal and a patient-domain shift.
- Train error artifacts contain `21,688` unique rows and match their SHA-256 manifest.
- Evidence: `docs/reports/20260831-120736-m2q-train-domain-error-comparison/train_audit/` and M2p validation audit.

## Decision

- Decision: `接受诊断；回到训练`
- Next gate: M2r asymmetric negative-focal ablation on seed 17.
