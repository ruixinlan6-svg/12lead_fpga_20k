# QN88 SRAM INT8 inference smoke

This is a deliberately small physical smoke for the frozen signed INT8 MAC
and requantize/clip semantics. It streams eight fixed activation/weight pairs,
whose dot product is 240, then applies a unit multiplier and one-bit shift,
expecting 120. LEDs expose started/pass/fail/busy/done/result status.

The smoke also reports a passive UART frame on FPGA PIN69 (board USB bridge
channel COM10): `INFER D=00F0 Q=78 P=1\r\n`. PIN70 is reserved as RX but is not
interpreted. Use 115200 8-N-1 and flush the host input buffer before capture.

It is not a full ECG model or accuracy benchmark. Program the generated `.fs`
to SRAM only; require an independent LED observation before marking the smoke
as physically passed.
