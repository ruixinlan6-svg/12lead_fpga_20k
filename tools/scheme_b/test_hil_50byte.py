import time
import serial
from pathlib import Path

def signed_byte(v):
    return v - 256 if v >= 128 else v

def read_hex_bytes(path):
    vals = []
    for line in Path(path).read_text(encoding="ascii").splitlines():
        line = line.strip()
        if line:
            vals.append(int(line, 16) & 0xFF)
    return bytes(vals)

hex_dir = Path("runs/20260826-1929-m2-input-quant-contract/hex")
input_bytes = read_hex_bytes(hex_dir / "input.hex")

weight_files = [
    "features_0_weight.hex",
    "features_0_bias.hex",
    "features_3_weight.hex",
    "features_3_bias.hex",
    "features_6_weight.hex",
    "features_6_bias.hex",
    "head_weight.hex",
    "head_bias.hex"
]
weight_bytes = b"".join(read_hex_bytes(hex_dir / fn) for fn in weight_files)

expected = [32, -22, -21, -19, -21]
print("Expected logits:", expected, "hex:", [f"{((x+256)&0xFF):02X}" for x in expected])

ser = serial.Serial("COM10", 115200, timeout=1.0)
time.sleep(0.2)
ser.reset_input_buffer()
ser.reset_output_buffer()

print(f"1. Sending ECG0 header (4 bytes)...")
ser.write(b"ECG0")
ser.flush()
time.sleep(0.05)

print(f"2. Sending {len(input_bytes)} input bytes in 50-byte chunks (pause 5ms)...")
for off in range(0, len(input_bytes), 50):
    ser.write(input_bytes[off : off + 50])
    ser.flush()
    time.sleep(0.005)

time.sleep(0.05)

print(f"3. Sending {len(weight_bytes)} weight bytes in 50-byte chunks (pause 5ms)...")
for off in range(0, len(weight_bytes), 50):
    ser.write(weight_bytes[off : off + 50])
    ser.flush()
    time.sleep(0.005)

print("All bytes transmitted successfully! Reading response from FPGA...")

deadline = time.monotonic() + 5.0
resp = bytearray()
while time.monotonic() < deadline:
    chunk = ser.read(256)
    if chunk:
        resp.extend(chunk)
        lines = resp.splitlines()
        for l in lines:
            line_str = l.decode("ascii", "replace").strip()
            if line_str.startswith("ECG "):
                print(f"  BOARD RX: {line_str}")
                if " D1 " in line_str:
                    ser.close()
                    # Parse logits
                    fields = line_str.split("L=", 1)[1].split()
                    logits = [signed_byte(int(x, 16)) for x in fields]
                    print(f"\nFinal Result:\n  Parsed Logits: {logits} (hex: {fields})")
                    if logits == expected:
                        print(">>> [SUCCESS] 100% BIT-EXACT MATCH WITH GOLDEN LOGITS! <<<")
                    else:
                        print(f">>> [HIL TEST MISMATCH] Expected {expected}, got {logits} <<<")
                    exit(0)
    time.sleep(0.01)

ser.close()
print("Timeout!")