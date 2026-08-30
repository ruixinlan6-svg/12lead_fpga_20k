// 27.000 MHz Clock Constraint for Sipeed Tang Nano 20K (GW2AR-LV18QN88C8/I7)
create_clock -name clk -period 37.037 -waveform {0 18.518} [get_ports {clk}]
