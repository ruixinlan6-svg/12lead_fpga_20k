# QN88 embedded SDRAM probe

This probe writes and reads four 32-word patterns through Gowin's
`SDRC_EMB` controller, then shows initialization/pass/error state on the six
active-low Tang Nano 20K LEDs. It is volatile only: the test does not touch
QSPI Flash.

The vendor IP is encrypted and remains in the local Gowin installation. The
build script references `IDE/ipcore/SDRC_EMB/data/GENERAL` at build time; no
vendor source is copied into Git. The target is the user-confirmed
`GW2AR-LV18QN88C8/I7` (QN88), not the historical QN88P LED project.

`sdrc_defines.v` is the auditable configuration header normally emitted by the
Gowin IP generator. The vendor RTL remains encrypted and is referenced from
the local Gowin installation.

Acceptance requires: Gowin synthesis/PnR succeeds for QN88, the SRAM bitstream
is downloaded, LED0 indicates SDRAM initialization, LED1 indicates four
write/read bursts passed, and LED2 indicates no mismatch. A failed or
ambiguous result keeps `read_write_test_passed=false` in the hardware contract.
