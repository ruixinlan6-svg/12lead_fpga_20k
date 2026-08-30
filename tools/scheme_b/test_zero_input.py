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

def rescale8(val, prod_m, qshift=31):
    numerator = val * prod_m
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

hex_dir = Path("runs/20260826-1929-m2-input-quant-contract/hex")
w1 = read_hex(hex_dir / "features_0_weight.hex")
b1 = read_hex(hex_dir / "features_0_bias.hex")
w2 = read_hex(hex_dir / "features_3_weight.hex")
b2 = read_hex(hex_dir / "features_3_bias.hex")
w3 = read_hex(hex_dir / "features_6_weight.hex")
b3 = read_hex(hex_dir / "features_6_bias.hex")
wh = read_hex(hex_dir / "head_weight.hex")
bh = read_hex(hex_dir / "head_bias.hex")

L1_PRODUCT_M = 16867375
L1_BIAS_M    = 134939
L2_PRODUCT_M = 16391448
L2_BIAS_M    = 131131
L3_PRODUCT_M = 18880629
L3_BIAS_M    = 151045
H_PRODUCT_M  = 12529589
H_BIAS_M     = 37360384

def run_forward(x_in):
    # L1: Conv (12 -> 16, k=7, p=3), ReLU, MaxPool (stride=2)
    # x_in: (12, 1000)
    p1 = np.zeros((16, 500), dtype=int)
    for oc in range(16):
        conv_out = np.zeros(1000, dtype=int)
        for t in range(1000):
            acc = 0
            for ic in range(12):
                for k in range(7):
                    t_in = t + k - 3
                    if 0 <= t_in < 1000:
                        acc += x_in[ic, t_in] * w1[oc * 84 + ic * 7 + k]
            conv_val = conv_quant(acc, b1[oc], L1_PRODUCT_M, L1_BIAS_M)
            conv_out[t] = max(0, conv_val)
        for t_p in range(500):
            p1[oc, t_p] = max(conv_out[t_p * 2], conv_out[t_p * 2 + 1])
    
    # L2: Conv (16 -> 32, k=7, p=3), ReLU, MaxPool (stride=2)
    p2 = np.zeros((32, 250), dtype=int)
    for oc in range(32):
        conv_out = np.zeros(500, dtype=int)
        for t in range(500):
            acc = 0
            for ic in range(16):
                for k in range(7):
                    t_in = t + k - 3
                    if 0 <= t_in < 500:
                        acc += p1[ic, t_in] * w2[oc * 112 + ic * 7 + k]
            conv_val = conv_quant(acc, b2[oc], L2_PRODUCT_M, L2_BIAS_M)
            conv_out[t] = max(0, conv_val)
        for t_p in range(250):
            p2[oc, t_p] = max(conv_out[t_p * 2], conv_out[t_p * 2 + 1])

    # L3: Conv (32 -> 32, k=5, p=2), ReLU
    r3 = np.zeros((32, 250), dtype=int)
    for oc in range(32):
        for t in range(250):
            acc = 0
            for ic in range(32):
                for k in range(5):
                    t_in = t + k - 2
                    if 0 <= t_in < 250:
                        acc += p2[ic, t_in] * w3[oc * 160 + ic * 5 + k]
            conv_val = conv_quant(acc, b3[oc], L3_PRODUCT_M, L3_BIAS_M)
            r3[oc, t] = max(0, conv_val)

    # GAP: 32 ch
    gap = np.zeros(32, dtype=int)
    for oc in range(32):
        acc = sum(r3[oc, :])
        gap[oc] = rescale8(acc, 8589934)

    # Head: 32 -> 5
    logits = []
    for oc in range(5):
        acc = sum(gap[ic] * wh[oc * 32 + ic] for ic in range(32))
        logits.append(conv_quant(acc, bh[oc], H_PRODUCT_M, H_BIAS_M))
    return logits, gap

# Test 1: All Zeros
x_zero = np.zeros((12, 1000), dtype=int)
l_zero, gap_zero = run_forward(x_zero)
print("All-Zeros input -> logits:", l_zero, "gap:", list(gap_zero))

# Test 2: Real Input
x_real = np.array(read_hex(hex_dir / "input.hex")).reshape(12, 1000)
l_real, gap_real = run_forward(x_real)
print("Real input      -> logits:", l_real)