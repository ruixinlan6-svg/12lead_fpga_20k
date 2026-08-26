# Headless Gowin build for the model-level QN88 ECG path.
# The embedded SDRAM controller remains a local Gowin IP dependency; no
# encrypted vendor source is copied into the repository.
set root [file normalize [file dirname [info script]]]
set gowin_ip "D:/software/Gowin/Gowin_V1.9.12.03_x64/IDE/ipcore/SDRC_EMB/data/GENERAL"
set build_dir [file join $root build]
file mkdir $build_dir
create_project -name qn88_model_full -dir $build_dir -pn GW2AR-LV18QN88C8/I7 -device_version C -force
add_file [file join $root qn88_model_full_top.sv]
# Link the RAM-mapped CNN as a separately synthesized SDPB netlist.  The
# source-level core is built by build_core_synth.tcl before this top build.
set core_netlist [file normalize [file join $root build_core model_core_only impl gwsynthesis model_core_only.vg]]
if {![file exists $core_netlist]} { error "missing core netlist: $core_netlist" }
add_file $core_netlist
add_file [file join $root qn88_uart_byte_rx.sv]
add_file [file join $root .. uart_probe qn88_uart_frame_tx.v]
add_file [file join $root .. inference_smoke pins.cst]
add_file [file join $root .. sdram_probe timing.sdc]
add_file [file join $root .. sdram_probe sdrc_defines.v]
foreach source {top_defines.v sdrc_top.v sdrc_control_fsm.v sdrc_user_interface.v sdrc_autorefresh.v SDRAM_controller_top_SIP.v} {
    add_file [file join $gowin_ip $source]
}
set_option -top_module qn88_model_full_top
set_option -netlist_hierarchy 2
set_option -include_path $root
set_option -include_path [file join $root .. sdram_probe]
set_option -use_sspi_as_gpio 1
set_option -use_cpu_as_gpio 1
set_option -use_i2c_as_gpio 1
run all
