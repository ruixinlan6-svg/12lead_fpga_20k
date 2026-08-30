from pathlib import Path

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

gap = read_hex("runs/20260826-1929-m2-input-quant-contract/expected_hex/gap.hex")
wh = read_hex("runs/20260826-1929-m2-input-quant-contract/hex/head_weight.hex")
bh = read_hex("runs/20260826-1929-m2-input-quant-contract/hex/head_bias.hex")

H_PRODUCT_M = 12529589
H_BIAS_M = 37360384

# Golden logits:
golden_logits = []
for oc in range(5):
    acc = sum(gap[ic] * wh[oc * 32 + ic] for ic in range(32))
    l = conv_quant(acc, bh[oc], H_PRODUCT_M, H_BIAS_M)
    golden_logits.append(l)
print("Golden logits:", golden_logits)

# What if wh was shifted by 1 (i.e. BSRAM read latency was off by 1)?
for shift in range(-5, 6):
    test_logits = []
    for oc in range(5):
        acc = 0
        for ic in range(32):
            idx = oc * 32 + ic + shift
            w = wh[idx] if 0 <= idx < len(wh) else 0
            acc += gap[ic] * w
        l = conv_quant(acc, bh[oc], H_PRODUCT_M, H_BIAS_M)
        test_logits.append(l)
    print(f"Shift {shift:2d}: {test_logits}")