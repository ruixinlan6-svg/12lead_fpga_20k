"""Read-only audit of an M2 NPZ cache against native beat provenance rules."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Sequence

import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[2]
TRAIN_EC57 = PROJECT_ROOT / "train" / "ec57"
if str(TRAIN_EC57) not in sys.path:
    sys.path.insert(0, str(TRAIN_EC57))

from cache_provenance import CacheProvenanceError, validate_m2_cache_split


def audit_npz(path: str | Path, *, split_name: str) -> dict[str, object]:
    cache_path = Path(path).resolve()
    with np.load(cache_path, allow_pickle=False) as loaded:
        arrays = {key: loaded[key] for key in loaded.files}
    report: dict[str, object] = {
        "path": str(cache_path),
        "split": split_name,
        "keys": sorted(arrays),
        "shapes": {key: list(value.shape) for key, value in sorted(arrays.items())},
        "source_counts": dict(
            sorted(Counter(str(value) for value in arrays.get("sources", np.array([], dtype=str))).items())
        ),
    }
    try:
        report["validation"] = validate_m2_cache_split(arrays, split_name=split_name)
        report["accepted"] = True
        report["error"] = None
    except CacheProvenanceError as exc:
        report["accepted"] = False
        report["error"] = str(exc)
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit an M2 NPZ cache without modifying it")
    parser.add_argument("--npz", required=True, type=Path)
    parser.add_argument("--split", required=True)
    args = parser.parse_args(argv)
    print(json.dumps(audit_npz(args.npz, split_name=args.split), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
