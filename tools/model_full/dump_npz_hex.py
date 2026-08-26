#!/usr/bin/env python3
"""Convert private integer Golden buffers to one-byte hex files for Icarus."""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("npz", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    arrays = np.load(args.npz)
    for name in arrays.files:
        values = [f"{int(value) & 0xFF:02X}" for value in arrays[name].reshape(-1)]
        (args.output / f"{name}.hex").write_text("\n".join(values) + "\n", encoding="ascii")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
