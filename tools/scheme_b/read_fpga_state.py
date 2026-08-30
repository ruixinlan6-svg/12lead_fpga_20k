import time
import serial

ser = serial.Serial("COM10", 115200, timeout=0.2)
ser.reset_input_buffer()
deadline = time.monotonic() + 1.5
while time.monotonic() < deadline:
    raw = ser.readline()
    if raw:
        print("FPGA Current State:", raw.decode("ascii", "replace").strip())
ser.close()