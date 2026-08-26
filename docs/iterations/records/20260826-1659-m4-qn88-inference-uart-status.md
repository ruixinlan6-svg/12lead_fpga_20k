# Optimization Run: `20260826-1659-m4-qn88-inference-uart-status`

## Identity

- Run ID: `20260826-1659-m4-qn88-inference-uart-status`
- Stage: `hil`
- Status: `completed`
- Started/finished: 2026-08-26 16:59 Asia/Shanghai / 2026-08-26 17:10 Asia/Shanghai
- Agent/operator: Codex `/root`
- Baseline run: `20260826-1627-m4-qn88-sram-inference-smoke`
- Git commit: pending
- Data version and split hash: not applicable
- Config/contract paths: `fpga/inference_smoke/`, `contracts/hardware_contract.json`
- Environment: Gowin EDA V1.9.12.03; QN88 `GW2AR-LV18QN88C8/I7`; local Tang Nano 20K; UART COM10

## Problem and evidence

- Observed problem: the inference smoke's LED result was not software-observable even though simulation, PnR, and SRAM transfer passed.
- Evidence from the baseline: the frozen known vector is expected to produce MAC `240` and requantized `120`; physical LED read-back was pending.
- Primary metric or failure point: capture a UART frame proving those exact values on the running QN88 SRAM image.

## Optimization

- Method: add a periodic read-only ASCII status frame to the known-vector smoke on PIN69/PIN70; keep arithmetic, vector, and LED semantics unchanged.
- Why this method: it reuses the now-verified COM10 path and makes the arithmetic result auditable without relying on visual LEDs.
- Alternatives considered and why not selected: LED-only observation is not machine-readable; Flash programming is unauthorized; changing the test vector would break the frozen Level-1 comparison.
- Expected mechanism: `INFER D=00F0 Q=78 P=1\r\n`-style frames will appear on COM10 after the MAC completes.

## Frozen acceptance criteria

- Success threshold: build/PnR and SRAM download pass; COM10 captures a frame with `D=00F0`, `Q=78`, and `P=1`.
- Failure/rollback threshold: missing frame, wrong arithmetic/status, or build/download failure; do not claim physical inference parity.
- Fixed test condition: eight fixed INT8 pairs, unit multiplier, shift 1, 115200 8-N-1, COM10 passive capture for 3 s, SRAM only.

## Execution

- Entry command or script: `fpga/inference_smoke/build_qn88.tcl`; BlueStar runner SRAM program; serial skill passive capture.
- GPU/card or hardware connection used: local Tang Nano 20K/QN88 and COM10.
- Calibration/Golden sample manifest: fixed vector dot product 240, requantized 120.
- Deviations from the plan: the previously unobservable arithmetic smoke was extended with passive UART only; the fixed vector, MAC, and requantization logic were unchanged.

## Results

| Metric | Baseline | This run | Delta | Comparable? |
|---|---:|---:|---:|---|
| Known-vector MAC | 240 (simulation) | `00F0` on COM10 | observed | yes |
| Requantized result | 120 (simulation) | `78` on COM10 | observed | yes |
| Physical pass flag | unverified | `P=1`; 276 bytes / 3.1 s | pass | gate |

- Per-class or per-layer findings: fixed eight-pair signed INT8 dot product is 240 (`00F0`); requantized result is 120 (`78`); pass flag is 1.
- Failed samples/first mismatch: none in the UART frame; LED state remains unobserved.
- Logs and report paths: `fpga/inference_smoke/build/qn88_int8_inference_smoke/impl/pnr/qn88_int8_inference_smoke.rpt.txt`; COM10 passive capture after buffer flush.
- Artifact paths and SHA-256: `fpga/inference_smoke/build/qn88_int8_inference_smoke/impl/pnr/qn88_int8_inference_smoke.fs`; `A219ADA9A20560F8CF7F8235FD5C25AA9D7D551621F8D0FBD6A95F643BA8DCC2`.
- Unverified items: this is an arithmetic/handshake smoke, not a full ECG model deployment or accuracy result; physical LEDs were not independently read.

## Decision

- Decision: `accept`
- Reason: build, SRAM transfer, and repeatable COM10 frame all meet the frozen smoke threshold; this validates the arithmetic path and status channel, not the complete ECG model.
- What changed in the project baseline: UART status output only; no model, quantizer, or vector change.
- One primary question for the next run: integrate the same status channel into a model-derived golden-vector path after the SDRAM gate is resolved.
