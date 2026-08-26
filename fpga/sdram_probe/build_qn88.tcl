# Headless Gowin build for the volatile QN88 SDRAM probe.
# Run from the repository root with gw_sh.exe after confirming the local
# Gowin installation path. Vendor encrypted SDRC_EMB sources are referenced
# by absolute path and are not part of the public repository.
set root [file normalize [file dirname [info script]]]
set gowin_ip "D:/software/Gowin/Gowin_V1.9.12.03_x64/IDE/ipcore/SDRC_EMB/data/GENERAL"
set build_dir [file join $root build]
file mkdir $build_dir
create_project -name qn88_sdram_probe -dir $build_dir -pn GW2AR-LV18QN88C8/I7 -device_version C -force
add_file [file join $root qn88_sdram_probe_top.v]
add_file [file join $root .. uart_probe qn88_uart_frame_tx.v]
add_file [file join $root pins.cst]
add_file [file join $root timing.sdc]
add_file [file join $root sdrc_defines.v]
foreach source {top_defines.v sdrc_top.v sdrc_control_fsm.v sdrc_user_interface.v sdrc_autorefresh.v SDRAM_controller_top_SIP.v} {
    add_file [file join $gowin_ip $source]
}
set_option -top_module qn88_sdram_probe
set_option -include_path $root
set_option -use_sspi_as_gpio 1
set_option -use_cpu_as_gpio 1
set_option -use_i2c_as_gpio 1
run all
