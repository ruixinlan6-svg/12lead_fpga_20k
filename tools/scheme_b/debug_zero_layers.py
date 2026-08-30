import numpy as np
from pathlib import Path

def read_hex(path):
    vals = []
    for line in Path(path).read_text(encoding="ascii").splitlines():
        line = line.strip()
        if line:
            v = int(line, 16) & 0xFF
            vals.append(v - 256 if v >= 128 else v)
    return np.array(vals, dtype=np.int64)

input_data = read_hex("runs/20260826-1929-m2-input-quant-contract/hex/input.hex")
w1 = read_hex("runs/20260826-1929-m2-input-quant-contract/hex/features_0_weight.hex")
b1 = read_hex("runs/20260826-1929-m2-input-quant-contract/hex/features_0_bias.hex")
w2 = read_hex("runs/20260826-1929-m2-input-quant-contract/hex/features_3_weight.hex")
b2 = read_hex("runs/20260826-1929-m2-input-quant-contract/hex/features_3_bias.hex")
w3 = read_hex("runs/20260826-1929-m2-input-quant-contract/hex/features_6_weight.hex")
b3 = read_hex("runs/20260826-1929-m2-input-quant-contract/hex/features_6_bias.hex")
wh = read_hex("runs/20260826-1929-m2-input-quant-contract/hex/head_weight.hex")
bh = read_hex("runs/20260826-1929-m2-input-quant-contract/hex/head_bias.hex")

C1_PRODUCT_M = 1866162
C1_BIAS_M    = 96620514
R1_M         = 2673984300
C2_PRODUCT_M = 4606622
C2_BIAS_M    = 27912751
R2_M         = 2147483648
C3_PRODUCT_M = 2850107
C3_BIAS_M    = 5207031
R3_M         = 3101789594
GAP_M_EFF    = 32422936
H_PRODUCT_M  = 12529589
H_BIAS_M     = 37360384
QSHIFT       = 31

def conv_quant(acc, bias, prod_m, bias_m):
    numerator = acc * prod_m + bias * bias_m
    if numerator < 0:
        rounded = (-numerator) + (1 << (QSHIFT - 1))
        scaled = -(rounded >> QSHIFT)
    else:
        rounded = numerator + (1 << (QSHIFT - 1))
        scaled = rounded >> QSHIFT
    return np.clip(scaled, -128, 127)

def rescale8(val, m):
    numerator = val * m
    if numerator < 0:
        rounded = (-numerator) + (1 << (QSHIFT - 1))
        scaled = -(rounded >> QSHIFT)
    else:
        rounded = numerator + (1 << (QSHIFT - 1))
        scaled = rounded >> QSHIFT
    return np.clip(scaled, -128, 127)

def trace_forward(inp):
    # L1
    pool1 = np.zeros((16, 500), dtype=np.int64)
    for oc in range(16):
        for t in range(500):
            p_max = -128
            for sub in range(2):
                t_in = 2 * t + sub
                acc = 0
                for ic in range(12):
                    for k in range(7):
                        t_k = t_in + k - 3
                        if 0 <= t_k < 1000:
                            acc += inp[ic * 1000 + t_k] * w1[oc * 84 + ic * 7 + k]
                cq = conv_quant(acc, b1[oc], C1_PRODUCT_M, C1_BIAS_M)
                rq = rescale8(cq, R1_M) if cq > 0 else 0
                p_max = max(p_max, rq)
            pool1[oc, t] = p_max

    # L2
    pool2 = np.zeros((32, 250), dtype=np.int64)
    for oc in range(32):
        for t in range(250):
            p_max = -128
            for sub in range(2):
                t_in = 2 * t + sub
                acc = 0
                for ic in range(16):
                    for k in range(7):
                        t_k = t_in + k - 3
                        if 0 <= t_k < 500:
                            acc += pool1[ic, t_k] * w2[oc * 112 + ic * 7 + k]
                cq = conv_quant(acc, b2[oc], C2_PRODUCT_M, C2_BIAS_M)
                rq = rescale8(cq, R2_M) if cq > 0 else 0
                p_max = max(p_max, rq)
            pool2[oc, t] = p_max

    # L3
    relu3 = np.zeros((32, 250), dtype=np.int64)
    for oc in range(32):
        for t in range(250):
            acc = 0
            for ic in range(32):
                for k in range(5):
                    t_k = t + k - 2
                    if 0 <= t_k < 250:
                        acc += pool2[ic, t_k] * w3[oc * 160 + ic * 5 + k]
            cq = conv_quant(acc, b3[oc], C3_PRODUCT_M, C3_BIAS_M)
            rq = rescale8(cq, R3_M) if cq > 0 else 0
            relu3[oc, t] = rq

    # L4: GAP
    gap = np.zeros(32, dtype=np.int64)
    for ch in range(32):
        s = np.sum(relu3[ch, :])
        num = s * GAP_M_EFF
        if num < 0:
            rnd = (-num) + (1 << (QSHIFT - 1))
            sc = -(rnd >> QSHIFT)
        else:
            rnd = num + (1 << (QSHIFT - 1))
            sc = rnd >> QSHIFT
        gap[ch] = np.clip(sc, -128, 127)

    # L5: Head
    logits = np.zeros(5, dtype=np.int64)
    for oc in range(5):
        acc = np.sum(gap * wh[oc*32 : (oc+1)*32])
        logits[oc] = conv_quant(acc, bh[oc], H_PRODUCT_M, H_BIAS_M)

    print("GAP output (first 10):", gap[:10])
    print("Logits (dec):", logits)
    print("Logits (hex):", [f"{x & 0xFF:02X}" for x in logits])

print("--- With Golden Input ---")
trace_forward(input_data)
print("\n--- With All-Zero Input ---")
trace_forward(np.zeros(12000, dtype=np.int64))