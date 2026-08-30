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

# Head weights matrix W: (5, 32)
W = np.array(wh).reshape(5, 32)
b = np.array(bh)

# Expected acc for each class
for oc in range(5):
    acc_exp = sum(gap_exp[ic] * W[oc, ic] for ic in range(32))
    l_exp = conv_quant(acc_exp, b[oc], H_PRODUCT_M, H_BIAS_M)
    print(f"Class {oc}: acc_exp={acc_exp}, logit_exp={l_exp}")

print("---")
# What acc values give target logits [-30, -34, 12, 11, 0]?
# In conv_quant: scaled = (acc * 12529589 + b * 37360384) / 2^31
# So acc ≈ (target * 2^31 - b * 37360384) / 12529589
for oc in range(5):
    t = target[oc]
    approx_acc = (t * (1 << 31) - b[oc] * H_BIAS_M) / H_PRODUCT_M
    print(f"Class {oc}: target={t}, approx_acc={approx_acc:.1f}, check: {conv_quant(round(approx_acc), b[oc], H_PRODUCT_M, H_BIAS_M)}")

# Notice: approx_acc for all classes is NEGATIVE!
# Class 0: approx_acc = -5283.4
# Class 1: approx_acc = -5817.1
# Class 2: approx_acc = 2075.0
# Class 3: approx_acc = 2265.8
# Class 4: approx_acc = -77.6