import os
import sys
import json
import argparse
import copy
from pathlib import Path
from typing import Dict

# Ensure project root is in sys.path
_cur_dir = os.path.dirname(os.path.abspath(__file__))
_proj_root = os.path.abspath(os.path.join(_cur_dir, "..", ".."))
if _proj_root not in sys.path:
    sys.path.insert(0, _proj_root)

import numpy as np
import torch

from train.ec57.train_nv import train_single_run
from train.ec57.cache_provenance import validate_m2_cache_split, validate_patient_disjoint_splits


def apply_smoke_overrides(config: dict) -> dict:
    """Return an explicitly labelled one-epoch pipeline-smoke configuration."""
    smoke = copy.deepcopy(config)
    smoke["run_mode"] = "one_epoch_pipeline_smoke"
    smoke["training"]["max_epochs"] = 1
    smoke["threshold_search"]["min_veb_plus_p"] = 0.0
    smoke["threshold_search"]["max_veb_fpr"] = 1.0
    return smoke


def format_split_summary(name: str, data: dict | None) -> str:
    if data is None:
        return f"{name}: not loaded (validation-only isolation)"
    labels = np.asarray(data["labels"])
    return f"{name}: {len(labels)} samples (VEB: {int(np.sum(labels == 1))})"


def load_native_cache_splits(
    cache_dir: str | os.PathLike[str], *, include_internal_test: bool = True
) -> Dict[str, Dict[str, np.ndarray]]:
    """Load the frozen train/validation/internal-test split and fail closed on provenance."""
    root = Path(cache_dir).resolve()
    splits: Dict[str, Dict[str, np.ndarray]] = {}
    split_names = ["train", "validation"]
    if include_internal_test:
        split_names.append("internal_test")
    for split in split_names:
        path = root / f"{split}_beats.npz"
        if not path.is_file():
            raise FileNotFoundError(f"required native cache split is missing: {path.name}")
        with np.load(path, allow_pickle=False) as archive:
            arrays = {key: np.asarray(archive[key]) for key in archive.files}
        validate_m2_cache_split(arrays, split_name=split)
        splits[split] = arrays
    validate_patient_disjoint_splits(splits)
    return splits


def main():
    parser = argparse.ArgumentParser(description="Train TinyECGCNN_NV candidate on remote GPU")
    parser.add_argument("--config", type=str, required=True, help="Path to candidate config json")
    parser.add_argument("--cache-dir", type=str, default=r"C:\Users\Administrator\Desktop\LRX\ecg_ti_pipeline_3\cache_ec57_beats_v1", help="Path to beat cache directory")
    parser.add_argument("--output-dir", type=str, required=True, help="Run output directory")
    parser.add_argument("--seed", type=int, default=17, help="Random seed (17, 29, 43)")
    parser.add_argument("--device", type=str, default="cuda:0", help="Torch device string")
    parser.add_argument(
        "--validation-only",
        action="store_true",
        help="Select A/B/C on validation without evaluating internal_test",
    )
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="Run one epoch with non-gating threshold search to validate the pipeline only",
    )
    args = parser.parse_args()

    with open(args.config, "r", encoding="utf-8") as f:
        config = json.load(f)
    if args.smoke:
        config = apply_smoke_overrides(config)

    print("==================================================")
    print(f"Candidate: {config.get('candidate_name')}")
    print(f"Seed:      {args.seed}")
    print(f"Device:    {args.device}")
    print(f"Output:    {args.output_dir}")
    print("==================================================")

    # 1. Load the already frozen patient-level splits. Never derive internal_test from validation.
    print(f"Loading native Icentia11k cache from {args.cache_dir}...")
    evaluate_internal_test = not (args.validation_only or args.smoke)
    splits = load_native_cache_splits(
        args.cache_dir, include_internal_test=evaluate_internal_test
    )
    train_data = splits["train"]
    val_data = splits["validation"]
    test_data = splits.get("internal_test")
    normalization_path = Path(args.cache_dir) / "normalization.json"
    if not normalization_path.is_file():
        raise FileNotFoundError(f"required train-only normalization is missing: {normalization_path}")
    with normalization_path.open("r", encoding="utf-8") as handle:
        normalization = json.load(handle)

    print(format_split_summary("Train", train_data))
    print(format_split_summary("Validation", val_data))
    print(format_split_summary("Internal test", test_data))

    # 2. Run training
    results = train_single_run(
        config=config,
        train_data=train_data,
        val_data=val_data,
        test_data=test_data,
        normalization=normalization,
        output_dir=args.output_dir,
        seed=args.seed,
        device_str=args.device,
        evaluate_internal_test=evaluate_internal_test,
    )

    print("==================================================")
    print("Training finished successfully!")
    print(f"Optimal Threshold: {results['optimal_threshold']}")
    if "test_metrics" in results:
        rates = results["test_metrics"]["gross_rates"]
        print(f"Test VEB Se:   {rates['veb_se_percent']:.3f}%" if rates['veb_se_percent'] is not None else "N/A")
        print(f"Test VEB +P:   {rates['veb_plus_p_percent']:.3f}%" if rates['veb_plus_p_percent'] is not None else "N/A")
        print(f"Test VEB FPR:  {rates['veb_fpr_percent']:.3f}%" if rates['veb_fpr_percent'] is not None else "N/A")
    else:
        print("Evaluation scope: validation only (internal_test not evaluated)")
    print(f"Model SHA-256: {results['model_sha256']}")
    print("==================================================")


if __name__ == "__main__":
    main()
