import json

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

H_PRODUCT_M = 1664790
H_BIAS_M = 31227092
bias_h = [12, -4, 42, 28, 23] # head_bias

# What if GAP output was all 0?
logits_if_gap_zero = [conv_quant(0, b, H_PRODUCT_M, H_BIAS_M) for b in bias_h]
print("Logits if GAP == 0:", logits_if_gap_zero, "hex:", [f"{x & 0xFF:02X}" for x in logits_if_gap_zero])

# What if acc was just bias?
# Let's check:
# For [-26, -33, 16, 4, 1]:
# Notice: bias_h = [12, -4, 42, 28, 23]
# If acc was some non-zero values...