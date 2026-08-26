set root [file normalize [file dirname [info script]]]
set rtl [file normalize [file join $root .. .. fpga model_full]]
set build [file join $rtl build_core]
file mkdir $build
create_project -name model_core_only -dir $build -pn GW2AR-LV18QN88C8/I7 -device_version C -force
add_file [file join $root core_synth_top.sv]
add_file [file join $rtl ecg_sync_dp_ram.sv]
add_file [file join $rtl tiny_ecgcnn_full.sv]
set_option -top_module core_synth_top
# Only the mapped core netlist is needed by the device-level top. Running PnR
# on this standalone wrapper would expose all 73 scalar tensor ports and hit
# the QN88 regular-I/O limit before the netlist can be linked.
run syn
