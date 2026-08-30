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
gap_exp = read_hex("runs/20260826-1929-m2-input-quant-contract/expected_hex/gap.hex")

# Head weights: 5 outputs, each has 32 inputs.
# In RTL tiny_ecgcnn_stream_core.sv line 257:
# w_raddr = oc_idx * 32 + ic_idx
# In Head layer:
# for oc in 0..4:
#    acc = sum(gap_mem[ic] * w_dout)
#    logit[oc] = conv_quant(acc, bias_mem[oc], H_PRODUCT_M, H_BIAS_M)

# What if gap_mem had all constant values C?
for c in range(-50, 50):
    logits = [conv_quant(sum(c * wh[oc * 32 + ic] for ic in range(32)), bh[oc], H_PRODUCT_M, H_BIAS_M) for oc in range(5)]
    if logits == target:
        print(f"MATCH: all gap_mem = {c} -> {logits}")

# What if gap_mem had an offset or scale?
for s in np.linspace(-5, 5, 201):
    logits = [conv_quant(sum(int(round(gap_exp[ic] * s)) * wh[oc * 32 + ic] for ic in range(32)), bh[oc], H_PRODUCT_M, H_BIAS_M) for oc in range(5)]
    if logits == target:
        print(f"MATCH: gap_mem scaled by {s:.3f} -> {logits}")

# What if head weights or bias were read at different address?
# Check L1, L2, L3, GAP outputs from Golden:
p1 = read_hex("runs/20260826-1929-m2-input-quant-contract/expected_hex/pool1.hex")
p2 = read_hex("runs/20260826-1929-m2-input-quant-contract/expected_hex/pool2.hex")
r3 = read_hex("runs/20260826-1929-m2-input-quant-contract/expected_hex/relu3.hex")
print("Expected pool1 sample:", p1[:10])
print("Expected pool2 sample:", p2[:10])
print("Expected relu3 sample:", r3[:10])
print("Expected gap:", gap_exp)