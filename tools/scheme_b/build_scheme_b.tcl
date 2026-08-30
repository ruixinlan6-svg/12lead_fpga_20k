# Gowin Headless Build Script for Scheme B (Stream Core + SDRAM Layer Streaming)
set script_dir [file normalize [file dirname [info script]]]
set root [file normalize [file join $script_dir "../.."]]
set gowin_ip "D:/software/Gowin/Gowin_V1.9.12.03_x64/IDE/ipcore/SDRC_EMB/data/GENERAL"
set build_dir [file join $root "fpga/scheme_b/build"]
file mkdir $build_dir

create_project -name qn88_scheme_b -dir $build_dir -pn GW2AR-LV18QN88C8/I7 -device_version C -force

add_file [file join $root "fpga/scheme_b/qn88_scheme_b_top.sv"]
add_file [file join $root "fpga/scheme_b/weight_storage_ram.sv"]
add_file [file join $root "fpga/scheme_b/sdram_layer_dma.sv"]
add_file [file join $root "fpga/scheme_b/tiny_ecgcnn_stream_core.sv"]
add_file [file join $root "fpga/model_full/ecg_sync_dp_ram.sv"]
add_file [file join $root "fpga/model_full/qn88_uart_byte_rx.sv"]
add_file [file join $root "fpga/uart_probe/qn88_uart_frame_tx.v"]
add_file [file join $root "fpga/sdram_probe/pins.cst"]
add_file [file join $root "fpga/sdram_probe/timing.sdc"]
add_file [file join $root "fpga/sdram_probe/sdrc_defines.v"]

foreach source {top_defines.v sdrc_top.v sdrc_control_fsm.v sdrc_user_interface.v sdrc_autorefresh.v SDRAM_controller_top_SIP.v} {
    add_file [file join $gowin_ip $source]
}

set_option -top_module qn88_scheme_b_top
set_option -include_path [file join $root "fpga/sdram_probe"]
set_option -use_sspi_as_gpio 1
set_option -use_cpu_as_gpio 1
set_option -use_i2c_as_gpio 1

run all