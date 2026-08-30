# Headless Gowin EDA V1.9.12.03 Synthesis and PnR build script for
# QN88 Twelve-Lead ECG generic RTL primitives microbenchmark.

set script_dir [file normalize [file dirname [info script]]]
set rtl_dir    [file normalize [file join $script_dir .. ..]]
set build_dir  [file join $script_dir build]

file mkdir $build_dir

create_project -name gowin_primitives_microbench -dir $build_dir -pn GW2AR-LV18QN88C8/I7 -device_version C -force

add_file [file join $rtl_dir ecg_sync_sp_ram.sv]
add_file [file join $rtl_dir ecg_sync_dp_ram.sv]
add_file [file join $rtl_dir ecg_requant_mac.sv]
add_file [file join $script_dir ecg_gowin_primitives_microbench_top.sv]
add_file [file join $script_dir gowin_primitives_microbench.cst]
add_file [file join $script_dir timing.sdc]

set_option -top_module ecg_gowin_primitives_microbench_top
set_option -verilog_std sysv2017
set_option -use_sspi_as_gpio 1
set_option -use_cpu_as_gpio 1
set_option -use_i2c_as_gpio 1

run all
