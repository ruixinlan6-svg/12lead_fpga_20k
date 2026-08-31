# Optimization Run: `20260831-081827-m2m-cache-selected-only-sqi`

## Identity

- Run ID: `20260831-081827-m2m-cache-selected-only-sqi`
- Stage: `M2 cache build performance repair`
- Status: `completed`
- Started/finished: 2026-08-31 08:18 CST / 2026-08-31 08:47 CST
- Agent/operator: Codex
- Baseline: running M2l cache build, PID `15376`, no output artifacts after about 32 minutes of active CPU work
- Model config: unchanged `candidate_c_dequantized`, seed `17`, validation-only threshold selection

## Problem and evidence

- The M2l process is not deadlocked: CPU time, source-read bytes and working set continue to move.
- Code inspection shows `build_record_examples` computes the 500-point fixed SQI and selected-only morphology features before checking `selected_keys` or excluding native `Q` markers.
- The frozen manifest contains `1,171,601` Q markers, and train negative sampling excludes additional N beats. Their SQI and selected-only features are discarded immediately, making the build materially slower without affecting cache contents.

## Optimization

- Preserve ordering, RR history, amplitude history, full-window peak state and all selected-beat outputs.
- Move only stateless selected-example work (QRS width and 500-point SQI) after the existing selected-key/trainable-symbol guard.
- Add a regression test proving unselected beats still influence temporal state while SQI is called exactly once per emitted example; retain existing feature equality tests.
- After tests pass, stop only the current owned cache process, verify it produced no artifacts, deploy the reviewed file, and restart the same M2l manifest/cache command.
- Why: removes discarded work while leaving source data, split, labels, selected keys, normalization, gates and model configuration unchanged.
- Alternatives rejected: continue an estimated additional long build, change sampling, omit temporal state updates, use imputation, or weaken cache acceptance.

## Frozen acceptance criteria

- New regression is red before the change and green after it.
- All EC57 tests pass and `git diff --check` has no errors.
- For every emitted example, waveform, sample identity, label and four raw features remain bit-exact relative to the pre-change algorithm.
- Unselected Q/N/S/V beats continue to update RR and amplitude histories exactly as before; they do not invoke fixed SQI or QRS-width calculation.
- Restart uses the exact M2l revised-audit SHA-256 and output directory; no source file, audit, split, threshold gate or Candidate C config changes.
- Cache must still pass every M2l provenance, count, finite-value, nonzero-IQR and SHA-256 gate before GPU training.

## Results

- RED: the new focused test observed four fixed-SQI calls for two emitted examples.
- GREEN: fixed-SQI calls fell to exactly two; both emitted four-feature vectors remained bit-exact against the captured pre-change values. Focused data tests passed `29/29` at this stage.
- The owned pre-change process was verified by command line and stopped at `454/912`; it had consumed about 32 minutes of CPU and had produced zero output artifacts.
- The reviewed file was deployed with matching local/remote SHA-256. At approximately the same source-read progress, the replacement process used about 10 minutes of CPU instead of 32 minutes, about a threefold improvement.
- The restarted cache completed all `912/912` records and wrote a hash-complete artifact set. Final split sizes were train `145,172`, validation `291,589`, internal-test `288,363`.
- Subsequent combined EC57 regression after M2n/M2o additions passed `169/169`; no cache data, labels, selected keys, normalization rule or model configuration changed.

## Decision

- Decision: `接受`（仅缓存性能优化范围）
- Next gate: M2n source-acquisition repair and M2o patient-coverage audit.
