# QN88 embedded SDRAM probe

This probe writes and reads four `data_len=25` user transfers through Gowin's
`SDRC_EMB` controller, then shows initialization/pass/error state on the six
active-low Tang Nano 20K LEDs. It also emits a read-only
`SDRAM I? P? E? D=xxxx X=xxxx` status frame at 115200 8-N-1 on the documented
BL616 UART pins, so the board result can be captured without relying on visual
LED observation. `D` and `X` are the high 16-bit words of the first read and
expected values. It is
volatile only: the test does not touch QSPI Flash.

The vendor IP is encrypted and remains in the local Gowin installation. The
build script references `IDE/ipcore/SDRC_EMB/data/GENERAL` at build time; no
vendor source is copied into Git. The target is the user-confirmed
`GW2AR-LV18QN88C8/I7` (QN88), not the historical QN88P LED project. The
transfer (`data_len=25`, bank 2, row 2) follows the local GW2AR vendor
testbench interface convention. On this QN88 32-bit configuration the useful
comparison window is 25 returned words; the controller emits one stale tail
pulse, which the read FSM intentionally ignores. The observed first user word
is one low-word count above the initial producer register, so the golden stream
starts at `A5A5_0001` and is recorded as an interface timing contract.

`sdrc_defines.v` is the auditable configuration header normally emitted by the
Gowin IP generator. The vendor RTL remains encrypted and is referenced from
the local Gowin installation.

## QN88 connection rule and first-read diagnosis

For the GW2AR/QN88 embedded SDRAM, the names `O_sdram_clk`, `O_sdram_cke`,
`O_sdram_cs_n`, `O_sdram_cas_n`, `O_sdram_ras_n`, `O_sdram_wen_n`,
`O_sdram_dqm`, `O_sdram_addr`, `O_sdram_ba`, and `IO_sdram_dq` must be
**top-level ports** of the Gowin design. Keeping them as internal wires allows
synthesis to prune the physical SIP data path; the symptom is
`I1 P0 E1 D=0000` even when the controller reset is extended. The accepted QN88
smoke build keeps a deterministic 16-bit POR hold as a robustness measure, but
the hardware A/B test showed that POR was not the cause of the zero first read.

The 2026-08-26 accepted run is recorded in
`docs/iterations/records/20260826-1840-m4-qn88-sdram-burst-reseed.md`; the
preceding magic-port diagnosis is preserved in
`docs/iterations/records/20260826-1757-m4-qn88-sdram-magic-ports.md`. It built
and programmed SRAM artifact `qn88_sdram_probe.fs` (final SHA-256
`1B1ACF201B380AD6B3F1D4AB807C73CFF6E2022DB521CFAEAF873A000B9EDE50`) and
returned eight clean COM10 frames: `SD I1 P1 E0 C=19 D=0000 X=0000`.
During diagnosis, the same frame temporarily reported the high and low words
and the terminal read count; those intermediate failures are preserved in the
iteration records. The final `P1 E0` is a volatile four-burst smoke result, not
a long-duration retention or full ECG-model traffic claim.

Acceptance requires: Gowin synthesis/PnR succeeds for QN88, the SRAM bitstream
is downloaded, LED0 indicates SDRAM initialization, LED1 indicates four
write/read bursts passed, and LED2 indicates no mismatch. A failed or
ambiguous result keeps `read_write_test_passed=false` in the hardware contract.
