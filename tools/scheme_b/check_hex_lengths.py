from pathlib import Path

hex_dir = Path("runs/20260826-1929-m2-input-quant-contract/hex")
weight_files = [
    "features_0_weight.hex",
    "features_0_bias.hex",
    "features_3_weight.hex",
    "features_3_bias.hex",
    "features_6_weight.hex",
    "features_6_bias.hex",
    "head_weight.hex",
    "head_bias.hex"
]

total = 0
for fn in weight_files:
    lines = [x.strip() for x in (hex_dir / fn).read_text(encoding="ascii").splitlines() if x.strip()]
    print(f"{fn}: {len(lines)} lines")
    total += len(lines)
print("Total parameter bytes:", total)