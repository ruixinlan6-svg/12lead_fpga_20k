import numpy as np
from pathlib import Path

def conv_quant(acc, bias, prod_m, bias_m, qshift=31):
    num = int(acc) * int(prod_m) + int(bias) * int(bias_m)
    if num < 0:
        rnd = (-num) + (1 << (qshift - 1))
        scaled = -(rnd >> qshift)
    else:
        rnd = num + (1 << (qshift - 1))
        scaled = rnd >> qshift
    return max(-128, min(127, scaled))

mem = Path('runs/20260826-1929-m2-input-quant-contract/hex')
wh = np.array([int(x, 16) if int(x, 16) < 128 else int(x, 16)-256 for x in (mem / 'head_weight.hex').read_text().split()]).reshape(5, 32)
bh = np.array([int(x, 16) if int(x, 16) < 128 else int(x, 16)-256 for x in (mem / 'head_bias.hex').read_text().split()])

print('sum(wh, axis=1):', np.sum(wh, axis=1))
for val in range(-128, 128):
    test_gap = np.full(32, val)
    logits = [conv_quant(np.dot(wh[oc], test_gap), bh[oc], 12529589, 37360384) for oc in range(5)]
    if logits[0] == -26:
        print(f'Match! gap={val}: logits={logits}, hex={[f"{(x+256)&0xFF:02X}" for x in logits]}')