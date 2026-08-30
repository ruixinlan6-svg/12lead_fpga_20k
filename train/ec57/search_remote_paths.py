import os
import sys

ptbxl_root = r"C:\Users\Administrator\Desktop\LRX\12lead_fpga_20k_m1\data\ptb-xl\1.0.3"
for d in ["records100", "records500"]:
    p = os.path.join(ptbxl_root, d)
    print(f"{d} exists: {os.path.exists(p)}")
