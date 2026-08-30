# RED-phase reproduction

With scenario 10 present and the baseline `beat_window_buffer.sv`, an idle-cycle
`qrs_valid` for already stored R index 2100 was classified as a reference error.
The exact failing assertion was:

```text
[SCENARIO 10] delayed QRS handshake and future-reference rejection
FATAL: fpga\ec57_hybrid\tb\tb_beat_window_buffer.sv:104: [FAIL] timeout: expected 1 windows, received 0 at time 51170000
```

The process exited with code 1. The final post-fix execution is archived separately
as `behavioral_simulation.log`.
