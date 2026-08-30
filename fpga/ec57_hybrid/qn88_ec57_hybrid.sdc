// SDC Timing Constraints for Twelve-Lead ECG EC57 Hybrid Architecture
// 27.000 MHz System Clock (Period = 37.037 ns)

create_clock -name clk -period 37.037 -waveform {0.000 18.518} [get_ports {clk}]
