# Optimization Run: `20260827-0824-m3b-sram-download-retry`

## Identity

- Run ID: `20260827-0824-m3b-sram-download-retry`
- Stage: `hil`
- Status: `completed_with_blocker`
- Started/finished: 2026-08-27 08:24 Asia/Shanghai / 2026-08-27 09:48 Asia/Shanghai
- Agent/operator: Codex
- Baseline run: `20260826-2056-m3b-sync-bram`
- Git commit: pending (this record and the handshake/address repair are the deliverables of this retry)
- Data version and split hash: PTB-XL 1.0.3; frozen Golden manifest from `runs/20260826-1929-m2-input-quant-contract`; no retraining
- Config/contract paths: `contracts/ecg_io_contract.json`; `fpga/model_full/build/qn88_model_full/impl/pnr/qn88_model_full.fs`
- Environment: Gowin V1.9.12.03, GW2AR-LV18QN88C8/I7 Tang Nano 20K QN88, SRAM-only, COM10, 115200 8-N-1

## Problem and evidence

- Observed problem: the prior M3b bitstream passed RTL, synthesis and PnR, but physical SRAM programming was blocked by Programmer `Cable open failed`; COM10 remained on the earlier SDRAM probe and returned no ECG frame.
- Evidence from the baseline: `20260826-2056-m3b-sync-bram` records the failed cable-open attempts and no board logits; the generated image is present and its hash is frozen below.
- Primary metric or failure point: live Programmer target recognition and SRAM download, followed by a complete COM10 ECG frame.

## Optimization

- Method: revalidate the Gowin Programmer cable enumeration, repair only the FTDI A-interface driver binding (the interface was bound to `libusbK` while the Programmer D2XX path requires FTDI), and use the documented SRAM-only `--run 2 --fsFile` flow; after a successful download, send the frozen input and 10,293-byte weight stream in 100-byte SDRAM-safe bursts and parse COM10. During diagnosis, align model SDRAM request timing with the accepted QN88 probe and map each burst to a separate row-safe address.
- Why this method: the JTAG chain already identifies `GW2AR-18C`, so the failure is at USB channel ownership rather than the bitstream or model. A scoped driver rebinding isolates that boundary without changing the model, protocol, or persistent Flash contents.
- Alternatives considered and why not selected: Flash programming is prohibited until timing and SRAM gates pass; changing RTL or the Golden vector would confound a hardware-link diagnosis.
- Expected mechanism: a recognized cable loads the existing validated image into volatile SRAM, replacing the old SDRAM probe image so COM10 can exercise the model protocol; the row-safe mapping prevents a 26-word transfer from crossing the QN88 8-bit column boundary.

## Frozen acceptance criteria

- Success threshold: Programmer identifies the attached QN88 and exits 0 after SRAM download; COM10 returns `ECG P1 S1 D1` with logits `{32,-22,-21,-19,-21}` for the frozen vector; record download and inference timings separately.
- Failure/rollback threshold: cable-open/programmer error, no ECG frame, any status bit 0, or any logit mismatch rejects this run; do not write Flash and do not alter the model contract.
- Fixed test set, thresholds and measurement conditions: `runs/20260826-1929-m2-input-quant-contract/hex`, 12,000 INT8 input bytes, 10,293 INT8 parameter bytes, 100-byte bursts, 115200 8-N-1, COM10, volatile SRAM only.

## Execution

- Entry command or script: Gowin `programmer_cli.exe --device GW2AR-18C --run 2 --fsFile <qn88_model_full.fs>`; `tools/hil/qn88_model_full_test.py --run runs/20260826-1929-m2-input-quant-contract --port COM10`.
- GPU/card or hardware connection used: local Tang Nano 20K QN88 USB/JTAG and COM10; no GPU.
- Calibration/Golden sample manifest: `runs/20260826-1929-m2-input-quant-contract/hex/expected_logits.hex`.
- Deviations from the plan: the QN88 USB Debugger A interface was rebound to the installed FTDI bus driver. JTAG SRAM reconfiguration does not reliably clear a failed user FSM, so the repeatable sequence is to load the UART probe SRAM image first, observe `QN88 UART OK`, then load the model image. No Flash operation was issued.

## Results

| Metric | Baseline | This run | Delta | Comparable? |
|---|---:|---:|---:|---|
| Programmer/QN88 SRAM download | `Cable open failed` | target `GW2AR-18C`, 100%, exit 0, status `0x00006020` | recovered | yes |
| Formal model PnR resources | 14,729 logic, 37/46 SDPB, 24/24 DSP | 14,644 logic, 37/46 SDPB, 24/24 DSP | small logic reduction | yes |
| COM10 ECG frame | no frame; old SDRAM probe | formal run returned `ECG P0 S0 D0 L=00 00 00 00 00` | board model gate rejected | yes |
| Logits | unavailable | no valid model logits; failure frame parsed as `[-48, 0, 0, 0, 0]` from raw `L=00 00 00 00 00`; expected `[32,-22,-21,-19,-21]` | gate rejected | yes |
| Download / inference latency | unavailable | SRAM programming about 5.5 s; inference did not complete within 180 s | no complete latency | no |

- Per-class or per-layer findings: software and direct RTL Golden remain exact `{32,-22,-21,-19,-21}`; the physical model image did not assert `P1/S1/D1`.
- Failed samples/first mismatch: debug-only telemetry reached `ST_SDRAM_READ` and later reported a readback mismatch (`0xFFFFFFFF` versus a nonzero FIFO word); a fixed 26-word/column-stride stream previously failed at the column boundary. After the row-safe stride, the formal image still fails the first full model SDRAM gate, so the physical data-bus/timing root cause remains open.
- Logs and report paths: `fpga/model_full/build/qn88_model_full/impl/pnr/qn88_model_full.rpt.txt`, `fpga/model_full/build/qn88_model_full/impl/pnr/qn88_model_full_tr_content.html`, `runs/20260827-0824-m3b-sram-download-retry.json`.
- Artifact paths and SHA-256: `fpga/model_full/build/qn88_model_full/impl/pnr/qn88_model_full.fs`; final formal image SHA-256 `1AB9719AF390A46243D0AF39F6370C24036C32EDD4346B48201A0ACAEC3DDC4C`.
- Download evidence: Programmer target `USB Debugger A/0/None/null`, device `GW2AR-18C(0x0000081B)`, SRAM-only progress 100%, status `0x00006020`, User Code `0x00007F23` on the final image. The UART probe independently returned `QN88 UART OK` on COM10.
- Unverified items: complete physical model SDRAM readback, board timing closure, and ECG logits; Flash was not touched.

## Decision

- Decision: `continue`
- Reason: the USB/JTAG boundary is now verified, and the final formal image downloads to QN88 SRAM, but the model-level SDRAM readback/ECG gate remains rejected (`P0 S0 D0`; no `D1`). Continue at RTL/SDRAM timing and then repeat the SRAM/HIL gate; do not write Flash.
- What changed in the project baseline: model SDRAM requests now follow the accepted QN88 probe handshake, and logical 100-byte bursts use row-safe address spacing; HIL gained optional `--wait-done`, `--wait-ack`, and `--input-pause` controls for diagnostic images. The formal source has no debug telemetry.
- One primary question for the next run: why does the model top's first physical SDRAM readback return an invalid word although the standalone four-burst QN88 probe returns `P1 E0`?
