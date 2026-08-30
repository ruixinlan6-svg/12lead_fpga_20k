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

# Target logits observed on FPGA:
target = [-26, -33, 16, 4, 1]

# What if GAP activations on FPGA were constant or all the same value C?
for c in range(-128, 128):
    gap_const = [c] * 32
    test_l = [conv_quant(sum(gap_const[ic] * wh[oc * 32 + ic] for ic in range(32)), bh[oc], H_PRODUCT_M, H_BIAS_M) for oc in range(5)]
    if test_l == target:
        print(f"MATCH FOUND! GAP was all {c}!")

# What if GAP was negated?
gap = read_hex("runs/20260826-1929-m2-input-quant-contract/expected_hex/gap.hex")
neg_gap = [-x for x in gap]
test_l = [conv_quant(sum(neg_gap[ic] * wh[oc * 32 + ic] for ic in range(32)), bh[oc], H_PRODUCT_M, H_BIAS_M) for oc in range(5)]
print("Negated GAP logits:", test_l)
if test_l == target:
    print("MATCH FOUND! GAP was negated!")