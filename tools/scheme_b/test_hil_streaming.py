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

ser = serial.Serial("COM10", 115200, timeout=0.1)

# Drain RX buffer
while ser.read(256):
    pass

print(f"1. Sending ECG0 header (4 bytes)...")
ser.write(b"ECG0")
ser.flush()
time.sleep(0.005)

print(f"2. Sending {len(input_bytes)} input bytes in 100-byte chunks...")
for off in range(0, len(input_bytes), 100):
    ser.write(input_bytes[off : off + 100])
    ser.flush()
    time.sleep(0.002)

print(f"3. Sending {len(weight_bytes)} weight bytes in 100-byte chunks...")
for off in range(0, len(weight_bytes), 100):
    ser.write(weight_bytes[off : off + 100])
    ser.flush()
    time.sleep(0.002)

print("All bytes transmitted! Monitoring serial output...")

deadline = time.monotonic() + 5.0
received = bytearray()
while time.monotonic() < deadline:
    chunk = ser.read(256)
    if chunk:
        received.extend(chunk)
        while b"\n" in received:
            line, received = received.split(b"\n", 1)
            line_str = line.decode("ascii", "replace").strip()
            if line_str.startswith("ECG "):
                print(f"  BOARD RX: {line_str}")
                if " D1 " in line_str:
                    fields = line_str.split("L=", 1)[1].split()
                    logits = [signed_byte(int(x, 16)) for x in fields]
                    print(f"\n=======================================================")
                    print(f"Final Result from FPGA:")
                    print(f"  Parsed Logits: {logits} (hex: {fields})")
                    print(f"  Expected:      {expected}")
                    if logits == expected:
                        print(">>> [SUCCESS] 100% BIT-EXACT MATCH WITH GOLDEN LOGITS! <<<")
                    else:
                        print(f">>> [HIL MISMATCH] Expected {expected}, got {logits} <<<")
                    print(f"=======================================================")
                    ser.close()
                    exit(0)
    time.sleep(0.01)

ser.close()
print("Timeout waiting for D1 frame!")