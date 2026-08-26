# Optimization Run: `<run_id>`

## Identity

- Run ID:
- Stage: `data | train | quant | goai | rtl | synth | hil | external`
- Status: `planned | running | completed | failed | aborted`
- Started/finished:
- Agent/operator:
- Baseline run:
- Git commit:
- Data version and split hash:
- Config/contract paths:
- Environment: Python/CUDA/Gowin/device/board as applicable

## Problem and evidence

- Observed problem:
- Evidence from the baseline:
- Primary metric or failure point:

## Optimization

- Method:
- Why this method:
- Alternatives considered and why not selected:
- Expected mechanism:

## Frozen acceptance criteria

- Success threshold:
- Failure/rollback threshold:
- Fixed test set, thresholds and measurement conditions:

## Execution

- Entry command or script:
- GPU/card or hardware connection used:
- Calibration/Golden sample manifest:
- Deviations from the plan:

## Results

| Metric | Baseline | This run | Delta | Comparable? |
|---|---:|---:|---:|---|
| Primary model metric | | | | |
| Quantization/parity error | | | | |
| LUT / FF / BSRAM / DSP | | | | |
| Fmax | | | | |
| Core / end-to-end latency | | | | |

- Per-class or per-layer findings:
- Failed samples/first mismatch:
- Logs and report paths:
- Artifact paths and SHA-256:
- Unverified items:

## Decision

- Decision: `accept | reject | rollback | continue`
- Reason:
- What changed in the project baseline:
- One primary question for the next run:
