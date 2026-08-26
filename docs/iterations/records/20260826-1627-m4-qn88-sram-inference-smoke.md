# Optimization Run: `20260826-1627-m4-qn88-sram-inference-smoke`

## Identity

- Stage: M4 QN88 SRAM-only INT8 inference smoke
- Date: 2026-08-26
- Owner: Codex implementation agent
- Status: passed_build_sram_transfer_led_pending
- Baseline: `20260826-1615-m3-int8-level1`

## Problem and evidence

- The signed INT8 MAC and requantize/clip units passed RTL Level-1 tests, but no QN88 physical bitstream has exercised their handshake and result path.
- A full ECG model bitstream is not yet frozen; this run deliberately proves the smallest deployable arithmetic slice before model-sized integration.

## Optimization

- Method: instantiate the frozen `conv1d_mac_int8` and `requantize_clip` units in a QN88 top, stream eight fixed signed activation/weight pairs, and compare the known dot-product/requantized result on-board.
- Why this method: it isolates arithmetic, sequencing, and SRAM programming from SDRAM and dataset concerns while remaining directly reusable for the eventual 12-lead layer.

## Frozen acceptance criteria

- Exact target `GW2AR-LV18QN88C8/I7`; synthesis/PnR succeeds.
- The bitstream is programmed to SRAM only.
- Expected dot product is 240 and expected symmetric INT8 requantized output is 120; the LED map exposes pass/fail/busy/done.
- A Programmer success proves configuration only; physical inference pass requires independent LED observation.

## Execution

- Local Icarus known-vector test passed. Gowin QN88 synthesis/PnR passed for `GW2AR-LV18QN88C8/I7`; SRAM-only programming used the connected `GW2AR-18C` family selector.

## Results

- The post-verification bitstream SHA-256 is `6CDCD68ACBD7F71AA912E49399C777A32BE59C875E01B4EC4B3BDCD3E5D50F69` (an earlier same-source build produced `F3BB31A378DB9E3BBE4610401BA119D041176312919E92B85A4EC9DC3F9DC75E`; Gowin output metadata is not byte-stable across rebuilds). Programmer reached 100% and reported `Successfully programmed FPGA (SRAM (Direct Run))`; reported status code was `0x00006020`. Resource report: 248/20736 logic, 1/24 DSP, 8 I/O.

## Decision

- Build, simulation, and SRAM transfer accepted. Physical inference pass remains LED-observation pending; this is not a full ECG benchmark or model-level accuracy result.
