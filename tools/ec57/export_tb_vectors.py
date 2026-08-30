"""Exports core golden vectors into plain hex/text files for Verilog testbench simulation."""

import os
import numpy as np


def export_tb_vectors(golden_npz_path: str, output_dir: str, num_beats: int = 16):
    os.makedirs(output_dir, exist_ok=True)
    with np.load(golden_npz_path) as data:
        waves = data['input_wave'][:num_beats]
        feats = data['input_feat'][:num_beats]
        logits = data['logits'][:num_beats]
        classes = data['classes'][:num_beats]

    # 1. Export input waves: each beat is 160 bytes
    with open(os.path.join(output_dir, 'tb_waves.hex'), 'w') as f:
        for b in range(num_beats):
            for t in range(160):
                val = int(waves[b, t]) & 0xFF
                f.write(f"{val:02X}\n")

    # 2. Export input features: each beat is 4 bytes
    with open(os.path.join(output_dir, 'tb_feats.hex'), 'w') as f:
        for b in range(num_beats):
            for i in range(4):
                val = int(feats[b, i]) & 0xFF
                f.write(f"{val:02X}\n")

    # 3. Export expected logits: each beat is 2 32-bit words
    with open(os.path.join(output_dir, 'tb_logits.hex'), 'w') as f:
        for b in range(num_beats):
            l0 = int(logits[b, 0]) & 0xFFFFFFFF
            l1 = int(logits[b, 1]) & 0xFFFFFFFF
            f.write(f"{l0:08X}\n")
            f.write(f"{l1:08X}\n")

    # 4. Export expected classes: 1 byte per beat
    with open(os.path.join(output_dir, 'tb_classes.hex'), 'w') as f:
        for b in range(num_beats):
            f.write(f"{int(classes[b]):02X}\n")

    print(f"Exported {num_beats} testbench vectors to {output_dir}")


if __name__ == '__main__':
    export_tb_vectors(
        golden_npz_path='runs/golden/core_golden_v1.npz',
        output_dir='fpga/ec57_hybrid/tb/vectors',
        num_beats=16
    )
