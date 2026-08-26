// =============================================================================
// Timing Constraints (.sdc) for Tang Nano 20K (GW2AR-18C)
// 27 MHz Clock Constraint: Period = 37.037 ns
// =============================================================================
create_clock -name clk -period 37.037 -waveform {0 18.518} [get_ports {clk}]
