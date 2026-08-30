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

target = [-30, -34, 12, 11, 0]

# What if GAP output had some scale factor or was unsigned instead of signed?
gap = read_hex("runs/20260826-1929-m2-input-quant-contract/expected_hex/gap.hex")
print("Expected GAP:", gap)

# Test if GAP was treated as unsigned (gap + 256 if gap < 0):
gap_u8 = [x + 256 if x < 0 else x for x in gap]
test_u8 = [conv_quant(sum(gap_u8[ic] * wh[oc * 32 + ic] for ic in range(32)), bh[oc], H_PRODUCT_M, H_BIAS_M) for oc in range(5)]
print("GAP as unsigned:", test_u8)

# Test if wh was treated as unsigned:
wh_u8 = [x + 256 if x < 0 else x for x in wh]
test_wh_u8 = [conv_quant(sum(gap[ic] * wh_u8[oc * 32 + ic] for ic in range(32)), bh[oc], H_PRODUCT_M, H_BIAS_M) for oc in range(5)]
print("wh as unsigned:", test_wh_u8)

# Test if GAP had a fixed offset or shift:
for scale in np.linspace(-3.0, 3.0, 61):
    gap_scaled = [int(np.clip(round(x * scale), -128, 127)) for x in gap]
    test_scaled = [conv_quant(sum(gap_scaled[ic] * wh[oc * 32 + ic] for ic in range(32)), bh[oc], H_PRODUCT_M, H_BIAS_M) for oc in range(5)]
    if test_scaled == target:
        print(f"MATCH! Scale = {scale}")