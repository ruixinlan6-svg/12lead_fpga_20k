# Gowin EDA Synthesis & PnR TCL Script for Twelve-Lead ECG EC57 Hybrid Pipeline
# Device: GW2AR-LV18QN88C8/I7

set_device -name GW2AR-18C GW2AR-LV18QN88C8/I7

set_option -verilog_std sysv2017
set_option -top_module qn88_ec57_hybrid_top
set_option -output_base_name qn88_ec57_hybrid

add_file -type verilog ecg_sync_sp_ram.sv
add_file -type verilog ecg_sync_dp_ram.sv
add_file -type verilog ecg_requant_mac.sv
add_file -type verilog beat_window_buffer.sv
add_file -type verilog ecg_biquad_timeshare.sv
add_file -type verilog lead_sqi_select.sv
add_file -type verilog qrs_detector_fixed.sv
add_file -type verilog nv_cnn_core.sv
add_file -type verilog rhythm_engine.sv
add_file -type verilog ec57_uart_protocol.sv
add_file -type verilog qn88_ec57_hybrid_top.sv

add_file -type cst qn88_ec57_hybrid.cst
add_file -type sdc qn88_ec57_hybrid.sdc

run syn
run pnr
