// Configuration header for the Gowin SDRC_EMB QN88 probe.
//
// The vendor IP sources are encrypted and expect this generated header. Keep
// the header local and auditable rather than modifying the Gowin installation.
`define MODULE_NAME qn88_sdram_controller
`define GW2AR18
`define SDRAM_DATA_WIDTH 32
`define SDRAM_BANK_WIDTH 2
`define SDRAM_ADDR_ROW_WIDTH 11
`define SDRAM_ADDR_COLUMN_WIDTH 8
`define USER_ADDR_WIDTH 21
`define SDRAM_ADDR_WIDTH `SDRAM_ADDR_ROW_WIDTH
`define SDRAM_DQM_WIDTH (`SDRAM_DATA_WIDTH/8)
