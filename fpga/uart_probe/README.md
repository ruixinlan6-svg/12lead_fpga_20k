# QN88 UART observability probe

This volatile SRAM-only probe emits `QN88 UART OK\r\n` every 250 ms at
115200 8-N-1.  It uses the user-confirmed QN88 mapping from the local Tang
Nano 20K schematic: FPGA PIN69 (`SYS_TX`) to `BL616_UART_RX`, and PIN70
(`SYS_RX`) from `BL616_UART_TX`.

The probe exists only to identify the host serial channel and validate the
FPGA → BL616 → USB path.  It does not touch QSPI Flash or SDRAM contents and
does not claim model-level ECG functionality.  The local PnP/pyserial scan
shows both COM9 and COM10 as healthy FT2232 ports; this probe's heartbeat was
received byte-for-byte on COM10 and not on COM9.  Program the generated `.fs`
to SRAM only, then passively monitor COM10 with the serial skill after flushing
its input buffer.
