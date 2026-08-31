# Optimization Run: `20260831-120235-m2p-validation-error-taxonomy`

## Identity

- Run ID: `20260831-120235-m2p-validation-error-taxonomy`
- Stage: `M2 validation-only failure diagnosis`
- Status: `completed`
- Started/finished: 2026-08-31 12:02 CST / 2026-08-31 12:07 CST
- Agent/operator: Codex
- Baseline: rejected M2l Candidate C seed-17 checkpoint, model SHA-256 `1b2d30d21d35f1171480f15939bfdd6851c0aed17d4a6c54056213e61341fb56`
- Model config: unchanged rejected checkpoint; no training in this run

## Problem and evidence

- Cohort expansion materially improved the best FPR-gated Se to `66.926%`, but no threshold reached +P `95%`; even threshold `0.999` had 52 false positives and +P `83.851%`.
- Aggregate counts do not show whether the residual errors are dominated by native S beats, a few patients/records, feature outliers, or broad waveform overlap.
- Changing loss, sampling or architecture without locating this residual error structure would be an ungrounded optimization.

## Optimization

- Run inference only on the already used validation NPZ with the exact rejected checkpoint; never load internal-test.
- Freeze diagnostic thresholds to `0.841` (maximum Se within FPR gate), `0.899` (best F1), and `0.999` (highest scanned threshold).
- Produce full confusion counts, FP/FN native-symbol taxonomy, patient/record concentration, probability and four-feature quantiles, and a deduplicated error CSV with exact patient/record/sample/source hashes.
- Preserve model/config/cache SHA-256 and generate an independent artifact manifest.
- Why: distinguish hard-negative/sampling failure from patient-domain shift or insufficient representation before the next training intervention.
- Alternatives rejected: rerun another seed, relax +P/FPR gates, inspect internal-test, or immediately enlarge the model.

## Frozen acceptance criteria

- TDD proves exact confusion counts, native-symbol grouping, patient/record grouping, deterministic ordering and validation-only input handling.
- Recomputed counts at all three thresholds exactly match the saved M2l threshold scan.
- Every emitted error row maps to one validation cache row and retains patient ID, record ID, sample index, native symbol and source SHA-256.
- Output includes full (not top-only) patient and record count maps plus compact ranked summaries; no raw waveform or internal-test data is copied.
- All artifacts have SHA-256 entries and local/remote tool hashes match.
- The next training change must cite a measured dominant failure mode from this report and receive a new run ID.

## Results

- TDD was red on the missing module and green after implementation; both exact-taxonomy tests passed. Local/remote tool SHA-256 matched: `424e8e091c51c57efed0e879817bb12a1a39e4229f966a8d55b700850d358aa4`.
- Validation-only replay processed `291,589` samples and explicitly recorded `internal_test_loaded=false`. Model/config/validation hashes matched M2l.
- All three confusion matrices exactly reproduced M2l: threshold `0.841`=`947/468/725/289449`, `0.899`=`856/559/435/289739`, `0.999`=`270/1145/52/290122` for VTP/VFN/VFP/VTN.
- At `0.841`, FP native symbols were `N=538` (74.21%) and `S=187` (25.79%). The top five FP patients contributed `583/725` (80.41%); the top five records contributed `465/725` (64.14%).
- At `0.899`, FP native symbols were `N=345` and `S=90`; the top five patients contributed `331/435` (76.09%).
- At `0.999`, FP native symbols were `N=46` and `S=6`; `p03217=34` and `p06034=11` alone contributed `45/52` (86.54%), proving a highly patient-concentrated high-confidence tail.
- V probability median was `0.94886`, but N and S maxima were both above `0.99999`; threshold calibration alone cannot create a 95% +P operating point.
- `1,870` unique error rows retained exact cache index, patient, record, native symbol, sample index, source hash, probability and normalized features. Summary/error hashes matched their manifest.
- Evidence: `docs/reports/20260831-120235-m2p-validation-error-taxonomy/validation_audit/`.

## Decision

- Decision: `接受诊断；回到训练`
- Next gate: M2q train-domain replay to distinguish available hard negatives from cross-patient representation failure.
