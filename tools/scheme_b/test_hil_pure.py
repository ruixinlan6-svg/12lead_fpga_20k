import serial
import time
from pathlib import Path

def signed_byte(v):
    return v - 256 if v >= 128 else v

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
expected_logits = [signed_byte(x) for x in read_hex(model_mem / "expected_logits.hex")]

print("Expected logits:", expected_logits, "hex:", [f"{x & 0xFF:02X}" for x in expected_logits])

ser = serial.Serial("COM10", 115200, timeout=0.1)
time.sleep(0.2)
ser.reset_input_buffer()
ser.reset_output_buffer()

print("Streaming ECG0 + 12,000 input bytes + 10,293 weight bytes...")
payload = b"ECG0" + input_bytes + weight_bytes
print(f"Total payload size: {len(payload)} bytes")

# Write payload in 1024-byte chunks
for off in range(0, len(payload), 1024):
    ser.write(payload[off : off + 1024])
    ser.flush()
    time.sleep(0.005)

print("All chunks written from host! Waiting for UART wire transmission & inference (3.0s)...")
time.sleep(3.0)

print("Reading response frames from board...")
response_lines = []
deadline = time.time() + 5.0
while time.time() < deadline:
    line = ser.readline()
    if line:
        s = line.decode("ascii", errors="replace").strip()
        if s.startswith("ECG"):
            print("  BOARD RX:", s)
            response_lines.append(s)
            if "D1" in s:
                break

ser.close()

passed = False
for line in reversed(response_lines):
    if line.startswith("ECG") and "L=" in line:
        parts = line.split("L=")
        header_parts = parts[0].split()
        logit_parts = parts[1].split()
        p_flag = "P1" in header_parts
        s_flag = "S1" in header_parts
        d_flag = "D1" in header_parts
        hex_tokens = logit_parts
        if len(hex_tokens) == 5:
            actual_logits = [signed_byte(int(tok, 16)) for tok in hex_tokens]
            print(f"Parsed Actual Logits: {actual_logits} (hex: {hex_tokens})")
            if actual_logits == expected_logits and p_flag and s_flag and d_flag:
                passed = True
                print(">>> [HIL TEST PASSED 100% BIT-EXACT] <<<")
            else:
                print(f">>> [HIL TEST FAILED] Logits diff: expected {expected_logits}, got {actual_logits} <<<")
        break

if not passed:
    print(">>> [HIL TEST FAILED: NO MATCH] <<<")