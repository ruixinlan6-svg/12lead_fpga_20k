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
print("Expected GAP:", gap)

# Check logits for expected gap:
exp_logits = [conv_quant(sum(gap[ic] * wh[oc * 32 + ic] for ic in range(32)), bh[oc], H_PRODUCT_M, H_BIAS_M) for oc in range(5)]
print("Expected logits:", exp_logits)

# Let us check if some channels of GAP were missing, zeroed, shifted, or scaled:
# What if gap was truncated or padded?
for shift in range(-10, 10):
    g_shift = [gap[i+shift] if 0 <= i+shift < 32 else 0 for i in range(32)]
    res = [conv_quant(sum(g_shift[ic] * wh[oc * 32 + ic] for ic in range(32)), bh[oc], H_PRODUCT_M, H_BIAS_M) for oc in range(5)]
    if res == target:
        print(f"MATCH with gap shift {shift} -> {res}")

# What if GAP divider was different or had integer truncation difference?
# In RTL: gap_quant: numerator = acc * 17179869184 + 125 * 2^31 ...
# In Python: gap[ch] = sum(act[ch, :]) // 250