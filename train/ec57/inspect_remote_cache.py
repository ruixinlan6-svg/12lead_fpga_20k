import numpy as np
import json
import os

cache_dir = r"C:\Users\Administrator\Desktop\LRX\ecg_ti_pipeline_3\cache_public_only_wfdb_v7_dev_15s_250hz"

for split in ["train", "val"]:
    npz_path = os.path.join(cache_dir, f"{split}.npz")
    if os.path.exists(npz_path):
        data = np.load(npz_path)
        print(f"=== {split}.npz ===")
        for k in data.files:
            print(f"  {k:20s}: shape={data[k].shape}, dtype={data[k].dtype}")
            if k == "labels":
                unique, counts = np.unique(data[k], return_counts=True)
                print(f"    class distribution: {dict(zip(unique.tolist(), counts.tolist()))}")
