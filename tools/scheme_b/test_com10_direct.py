import serial
import time
from pathlib import Path

def read_hex(path):
    vals = []
    for line in Path(path).read_text(encoding="ascii").splitlines():
        line = line.strip()
        if line:
            vals.append(int(line, 16) & 0xFF)
    return bytes(vals)

model_mem = Path("runs/20260826-1929-m2-input-quant-contract/hex")
input_bytes = read_hex(model_mem / "input.hex")
weight_files = [
    "features_0_weight.hex", "features_0_bias.hex",
    "features_3_weight.hex", "features_3_bias.hex",
    "features_6_weight.hex", "features_6_bias.hex",
    "head_weight.hex", "head_bias.hex"
]
weight_bytes = b"".join(read_hex(model_mem / f) for f in weight_files)

ser = serial.Serial("COM10", 115200, timeout=1.0)
time.sleep(0.5)
ser.reset_input_buffer()
ser.reset_output_buffer()

print("Sending resync character E...")
ser.write(b"E")
ser.flush()
time.sleep(0.1)

print("Sending payload ECG0 + input (12,000 bytes)...")
ser.write(b"ECG0" + input_bytes)
ser.flush()
time.sleep(0.2)

print("Sending weights (10,293 bytes in 100-byte chunks)...")
for offset in range(0, len(weight_bytes), 100):
    ser.write(weight_bytes[offset : offset + 100])
    ser.flush()
    time.sleep(0.005)

print("Payload sent! Reading response for 5 seconds...")
deadline = time.time() + 5.0
while time.time() < deadline:
    line = ser.readline()
    if line:
        print("RECV:", line.decode("ascii", errors="replace").strip())
        if b" D1 " in line:
            break

ser.close()