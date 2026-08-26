open_project project.gprj
set_option -top_module led_flow_blink2
set_option -use_sspi_as_gpio 1
set_option -use_cpu_as_gpio 1
set_option -use_i2c_as_gpio 1
run all
