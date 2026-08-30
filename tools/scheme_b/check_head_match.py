from pathlib import Path
import numpy as np

def signed_byte(v):
    return v - 256 if v >= 128 else v

def conv_quant(acc, bias, prod_m, bias_m, qshift=31):
    numerator = acc * prod_m + bias * bias_m
    if numerator < 0:
        rounded = (-numerator) + (1 << (qshift - 1))
        scaled = -(rounded >> qshift)
    else:
        rounded = numerator + (1 << (qshift - 1))
        scaled = rounded >> qshift
    if scaled > 127: return 127
    elif scaled < -128: return -128
    else: return scaled

def read_hex(path):
    vals = []
    for line in Path(path).read_text(encoding="ascii").splitlines():
        line = line.strip()
        if line:
            vals.append(signed_byte(int(line, 16) & 0xFF))
    return vals

wh = read_hex("runs/20260826-1929-m2-input-quant-contract/hex/head_weight.hex")
bh = read_hex("runs/20260826-1929-m2-input-quant-contract/hex/head_bias.hex")
H_PRODUCT_M = 12529589
H_BIAS_M = 37360384

target = [32, -26, -50, 10, 4]
gap = read_hex("runs/20260826-1929-m2-input-quant-contract/expected_hex/gap.hex")

print("Expected Head weights length:", len(wh))
print("Expected Head bias:", bh)

# Let us check what weights were used for each output class oc:
# L0 matched 32. What if wh or bh had an offset or was read with an address offset?
for w_offset in range(-20, 20):
    for b_offset in range(-10, 10):
        res = []
        for oc in range(5):
            acc = 0
            for ic in range(32):
                w_idx = oc * 32 + ic + w_offset
                w_val = wh[w_idx] if 0 <= w_idx < len(wh) else 0
                acc += gap[ic] * w_val
            b_idx = oc + b_offset
            b_val = bh[b_idx] if 0 <= b_idx < len(bh) else 0
            res.append(conv_quant(acc, b_val, H_PRODUCT_M, H_BIAS_M))
        if res == target:
            print(f"MATCH with w_offset={w_offset}, b_offset={b_offset} -> {res}")
        if res[0] == 32 and res[1] == -26:
            print(f"Partial match (L0,L1) with w_offset={w_offset}, b_offset={b_offset} -> {res}")