"""Fail-closed provenance validation for M2 native beat caches."""

from __future__ import annotations

import re
from collections import Counter
from typing import Mapping

import numpy as np


REQUIRED_FIELDS = {
    "waveforms",
    "features",
    "labels",
    "patient_ids",
    "database",
    "database_version",
    "record_ids",
    "sample_indices",
    "native_symbols",
    "source_file_sha256",
}
LABEL_BY_SYMBOL = {"N": 0, "S": 0, "V": 1}
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
LOOKAHEAD_REQUIRED_FIELDS = {
    "feature_names",
    "feature_contract_id",
    "decision_latency_mode",
    "context_sample_indices",
}


class CacheProvenanceError(ValueError):
    """Raised when an M2 cache cannot prove native beat-label provenance."""


def _as_array_map(data: Mapping[str, object]) -> dict[str, np.ndarray]:
    return {key: np.asarray(value) for key, value in data.items()}


def validate_m2_cache_split(data: Mapping[str, object], *, split_name: str) -> dict[str, object]:
    arrays = _as_array_map(data)
    missing = sorted(REQUIRED_FIELDS - set(arrays))
    if missing:
        raise CacheProvenanceError(f"{split_name}: missing required provenance fields: {missing}")

    sample_count = len(arrays["labels"])
    if sample_count == 0:
        raise CacheProvenanceError(f"{split_name}: empty cache split")
    for field in REQUIRED_FIELDS - {"waveforms", "features"}:
        if len(arrays[field]) != sample_count:
            raise CacheProvenanceError(f"{split_name}: field length mismatch for {field}")
    if arrays["waveforms"].shape != (sample_count, 160):
        raise CacheProvenanceError(f"{split_name}: waveforms must have shape [N,160]")
    if arrays["features"].ndim != 2 or arrays["features"].shape[0] != sample_count or arrays["features"].shape[1] not in {4, 5, 6, 8}:
        raise CacheProvenanceError(f"{split_name}: features must have shape [N,4], [N,5], [N,6], or [N,8]")
    feature_count = int(arrays["features"].shape[1])
    if feature_count > 4:
        missing_lookahead = sorted(LOOKAHEAD_REQUIRED_FIELDS - set(arrays))
        if missing_lookahead:
            raise CacheProvenanceError(
                f"{split_name}: lookahead cache missing schema fields: {missing_lookahead}"
            )
        feature_names = [str(value) for value in arrays["feature_names"].tolist()]
        if len(feature_names) != feature_count or len(set(feature_names)) != feature_count:
            raise CacheProvenanceError(f"{split_name}: invalid lookahead feature_names")
        if str(arrays["feature_contract_id"].item()) != "qn88-ec57-hybrid-io-lookahead-v2":
            raise CacheProvenanceError(f"{split_name}: unexpected lookahead feature contract")
        if str(arrays["decision_latency_mode"].item()) != "next_valid_qrs":
            raise CacheProvenanceError(f"{split_name}: lookahead decision must wait for next_valid_qrs")
        context = arrays["context_sample_indices"]
        if context.shape != (sample_count, 2):
            raise CacheProvenanceError(f"{split_name}: context_sample_indices must have shape [N,2]")
        current = arrays["sample_indices"].astype(np.int64)
        if np.any(context[:, 0] >= current) or np.any(context[:, 1] <= current):
            raise CacheProvenanceError(f"{split_name}: fabricated or non-causal lookahead context")

    databases = [str(value) for value in arrays["database"]]
    versions = [str(value) for value in arrays["database_version"]]
    if any(database != "Icentia11k" for database in databases) or any(version != "1.0" for version in versions):
        raise CacheProvenanceError(f"{split_name}: only Icentia11k 1.0 is allowed for M2")

    symbols = [str(value) for value in arrays["native_symbols"]]
    if "Q" in symbols:
        raise CacheProvenanceError(f"{split_name}: Q must be counted then excluded from the loss cache")
    if any(symbol not in LABEL_BY_SYMBOL for symbol in symbols):
        raise CacheProvenanceError(f"{split_name}: unsupported native symbol")
    labels = [int(value) for value in arrays["labels"]]
    if any(label != LABEL_BY_SYMBOL[symbol] for label, symbol in zip(labels, symbols)):
        raise CacheProvenanceError(f"{split_name}: native symbol mapping does not match the frozen contract")

    sample_indices = [int(value) for value in arrays["sample_indices"]]
    if any(index < 0 for index in sample_indices):
        raise CacheProvenanceError(f"{split_name}: negative native sample index")
    hashes = [str(value).lower() for value in arrays["source_file_sha256"]]
    if any(not SHA256_PATTERN.fullmatch(value) for value in hashes):
        raise CacheProvenanceError(f"{split_name}: invalid source-file SHA-256")
    if any(not str(value) for value in arrays["patient_ids"]):
        raise CacheProvenanceError(f"{split_name}: empty patient ID")
    if any(not str(value) for value in arrays["record_ids"]):
        raise CacheProvenanceError(f"{split_name}: empty record ID")

    return {
        "split": split_name,
        "sample_count": sample_count,
        "patient_count": len(set(str(value) for value in arrays["patient_ids"])),
        "native_symbol_counts": dict(sorted(Counter(symbols).items())),
        "feature_count": feature_count,
    }


def validate_patient_disjoint_splits(splits: Mapping[str, Mapping[str, object]]) -> dict[str, int]:
    patient_sets = {
        split_name: set(str(value) for value in np.asarray(data["patient_ids"]))
        for split_name, data in splits.items()
    }
    split_names = sorted(patient_sets)
    for position, left_name in enumerate(split_names):
        for right_name in split_names[position + 1 :]:
            overlap = patient_sets[left_name] & patient_sets[right_name]
            if overlap:
                raise CacheProvenanceError(
                    f"patient overlap between {left_name} and {right_name}: {sorted(overlap)[:5]}"
                )
    return {name: len(patients) for name, patients in patient_sets.items()}
