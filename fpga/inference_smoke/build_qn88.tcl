# Headless Gowin build for the QN88 SRAM-only INT8 inference smoke.
set root [file normalize [file dirname [info script]]]
set build_dir [file join $root build]
set rtl_dir [file normalize [file join $root .. rtl]]
file mkdir $build_dir
create_project -name qn88_int8_inference_smoke -dir $build_dir -pn GW2AR-LV18QN88C8/I7 -device_version C -force
add_file [file join $root qn88_int8_inference_smoke.sv]
add_file [file join $root conv1d_mac_int8_gowin.v]
add_file [file join $root requantize_clip_gowin.v]
add_file [file join $root pins.cst]
add_file [file join $root timing.sdc]
set_option -top_module qn88_int8_inference_smoke
set_option -use_sspi_as_gpio 1
set_option -use_cpu_as_gpio 1
set_option -use_i2c_as_gpio 1
run all
