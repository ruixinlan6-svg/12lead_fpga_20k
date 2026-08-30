import os
import sys

base_dir = r"C:\Users\Administrator\Desktop\LRX\ecg_ti_pipeline_3"

for fname in ["beat_override.py", "wfdb_rhythm.py"]:
    p = os.path.join(base_dir, "ecgpipe", "labels", fname)
    if os.path.exists(p):
        with open(p, "r", encoding="utf-8") as f:
            print(f"=== {fname} ===")
            print(f.read()[:3000])
