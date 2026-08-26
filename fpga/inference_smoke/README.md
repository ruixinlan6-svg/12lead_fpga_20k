# QN88 SRAM INT8 inference smoke

This is a deliberately small physical smoke for the frozen signed INT8 MAC
and requantize/clip semantics. It streams eight fixed activation/weight pairs,
whose dot product is 240, then applies a unit multiplier and one-bit shift,
expecting 120. LEDs expose started/pass/fail/busy/done/result status.

It is not a full ECG model or accuracy benchmark. Program the generated `.fs`
to SRAM only; require an independent LED observation before marking the smoke
as physically passed.
