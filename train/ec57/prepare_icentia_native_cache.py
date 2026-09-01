"""Build a patient-isolated M2 cache from native Icentia11k beat symbols."""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping, Sequence

import numpy as np

from beat_dataset import (
    extract_beat_window,
    normalize_scalar_features_int8,
    normalize_waveform_int8,
    round_half_away_from_zero,
)
from cache_provenance import validate_m2_cache_split, validate_patient_disjoint_splits
from sqi import continuous_sqi_score_q15_fixed


LABEL_BY_SYMBOL = {"N": 0, "S": 0, "V": 1}
PN_DIR = "icentia11k-continuous-ecg/1.0"
WFDB_DOWNLOAD_DB = "icentia11k-continuous-ecg"

FEATURE_NAMES_BY_COUNT = {
    4: [
        "previous_rr_over_recent_8_rr_median",
        "qrs_width_ms",
        "peak_over_recent_8_peak_median",
        "main_lead_sqi",
    ],
    5: [
        "previous_rr_over_recent_8_rr_median",
        "next_rr_over_recent_8_rr_median",
        "qrs_width_ms",
        "peak_over_recent_8_peak_median",
        "main_lead_sqi",
    ],
    6: [
        "previous_rr_over_recent_8_rr_median",
        "next_rr_over_recent_8_rr_median",
        "rr_pair_over_twice_recent_8_rr_median",
        "qrs_width_ms",
        "peak_over_recent_8_peak_median",
        "main_lead_sqi",
    ],
    8: [
        "previous_rr_over_recent_8_rr_median",
        "next_rr_over_recent_8_rr_median",
        "rr_pair_over_twice_recent_8_rr_median",
        "ectopic_coupling",
        "next_minus_previous_rr_ratio",
        "qrs_width_ms",
        "peak_over_recent_8_peak_median",
        "main_lead_sqi",
    ],
}
LOOKAHEAD_CONTRACT_ID = "qn88-ec57-hybrid-io-lookahead-v2"
CAUSAL4_CONTRACT_ID = "qn88-ec57-hybrid-io-v1"


@dataclass(frozen=True, order=True)
class NativeBeat:
    patient_id: str
    record_id: str
    sample_index: int
    native_symbol: str
    source_file_sha256: str

    @property
    def key(self) -> str:
        return f"{self.patient_id}|{self.record_id}|{self.sample_index}|{self.native_symbol}"


def _digest_key(beat: NativeBeat) -> tuple[str, str]:
    return hashlib.sha256(beat.key.encode("utf-8")).hexdigest(), beat.key


def source_relative_files(patient_id: str, record_id: str) -> list[str]:
    prefix = patient_id[:3]
    return [f"{prefix}/{patient_id}/{record_id}.{extension}" for extension in ("atr", "dat", "hea")]


def ensure_source_files(
    source_root: str | Path,
    relative_files: Sequence[str],
    *,
    downloader,
) -> dict[str, object]:
    """Avoid remote acquisition only when the complete local source set exists."""
    source = Path(source_root).resolve()
    ordered = list(relative_files)
    missing = [relative for relative in ordered if not (source / Path(relative)).is_file()]
    if not missing:
        return {"mode": "existing_verified_later", "missing_before": []}
    downloader(
        WFDB_DOWNLOAD_DB,
        str(source),
        ordered,
        keep_subdirs=True,
        overwrite=False,
    )
    return {"mode": "download_requested", "missing_before": missing}


def combined_record_sha256(file_hashes: Mapping[str, str]) -> str:
    payload = json.dumps(dict(sorted(file_hashes.items())), separators=(",", ":"), sort_keys=True).encode("ascii")
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def select_training_beats(
    beats: Iterable[NativeBeat], *, max_negative_per_positive: int
) -> list[NativeBeat]:
    if max_negative_per_positive <= 0:
        raise ValueError("max_negative_per_positive must be positive")
    accepted = [beat for beat in beats if beat.native_symbol in LABEL_BY_SYMBOL]
    positives = sorted((beat for beat in accepted if beat.native_symbol == "V"), key=_digest_key)
    supraventricular = sorted((beat for beat in accepted if beat.native_symbol == "S"), key=_digest_key)
    normal = sorted((beat for beat in accepted if beat.native_symbol == "N"), key=_digest_key)
    normal_budget = max(0, max_negative_per_positive * len(positives) - len(supraventricular))
    selected = positives + supraventricular + normal[:normal_budget]
    return sorted(selected)


def compute_train_waveform_scale(raw_windows: np.ndarray) -> float:
    windows = np.asarray(raw_windows)
    if windows.ndim != 2 or windows.shape[1] != 160 or len(windows) == 0:
        raise ValueError("raw train windows must have shape [N,160]")
    medians = np.median(windows.astype(np.float64), axis=1, keepdims=True)
    deviations = np.abs(windows.astype(np.float64) - medians)
    return max(20.0, float(np.percentile(deviations, 99.5)))


def _complete_sqi_window(signal: np.ndarray, beat_sample: int) -> np.ndarray:
    stop = beat_sample + 96
    start = stop - 500
    actual_start = max(0, start)
    actual_stop = min(len(signal), stop)
    window = np.asarray(signal[actual_start:actual_stop], dtype=np.int16)
    pad_left = max(0, -start)
    pad_right = 500 - pad_left - len(window)
    return np.pad(window, (pad_left, max(0, pad_right)), mode="constant")[-500:]


def normalize_native_beats_for_features(beats: Iterable[NativeBeat]) -> list[NativeBeat]:
    """Collapse exact Q-only duplicates while rejecting trainable-label ambiguity."""
    ordered = sorted(beats, key=lambda beat: (beat.sample_index, beat.native_symbol))
    normalized: list[NativeBeat] = []
    position = 0
    while position < len(ordered):
        sample = int(ordered[position].sample_index)
        stop = position + 1
        while stop < len(ordered) and int(ordered[stop].sample_index) == sample:
            stop += 1
        group = ordered[position:stop]
        if len(group) > 1:
            symbols = [beat.native_symbol for beat in group]
            if set(symbols) != {"Q"}:
                identity = f"{group[0].patient_id}|{group[0].record_id}|{sample}"
                raise ValueError(f"ambiguous native beat annotations at {identity}: {symbols}")
            normalized.append(group[0])
        else:
            normalized.append(group[0])
        position = stop
    return normalized


def count_lookahead_context_exclusions(
    beats: Iterable[NativeBeat], *, selected_keys: set[str]
) -> dict[str, int]:
    """Count selected trainable beats that lack real previous/next annotation context."""
    ordered = normalize_native_beats_for_features(beats)
    counts = {"missing_previous": 0, "missing_next": 0, "missing_either": 0}
    for index, beat in enumerate(ordered):
        if beat.key not in selected_keys or beat.native_symbol not in LABEL_BY_SYMBOL:
            continue
        missing_previous = index == 0
        missing_next = index + 1 == len(ordered)
        counts["missing_previous"] += int(missing_previous)
        counts["missing_next"] += int(missing_next)
        counts["missing_either"] += int(missing_previous or missing_next)
    return counts


def build_record_examples(
    signal_lsb: np.ndarray,
    beats: Iterable[NativeBeat],
    *,
    selected_keys: set[str],
    num_features: int = 4,
) -> list[dict[str, object]]:
    signal = np.asarray(signal_lsb)
    if signal.ndim != 1:
        raise ValueError("Icentia signal must be one-dimensional")
    if num_features not in FEATURE_NAMES_BY_COUNT:
        raise ValueError(f"unsupported feature count: {num_features}")
    ordered = normalize_native_beats_for_features(beats)
    rr_history: list[int] = []
    amplitude_history: list[float] = []
    examples: list[dict[str, object]] = []
    for i, beat in enumerate(ordered):
        sample = int(beat.sample_index)
        if sample < 0 or sample >= len(signal):
            raise ValueError(f"native annotation outside signal: {beat.key}")
        has_previous_context = i > 0
        has_next_context = i + 1 < len(ordered)
        if i == 0:
            pre_rr = 250
            pre_rr_ratio = 1.0
        else:
            prev_sample = int(ordered[i - 1].sample_index)
            pre_rr = sample - prev_sample
            if pre_rr <= 0:
                raise ValueError(f"non-increasing native beat annotation: {beat.key}")
            rr_history.append(pre_rr)
            rr_history = rr_history[-8:]
            median_rr = float(np.median(rr_history))
            pre_rr_ratio = pre_rr / median_rr

        median_rr = float(np.median(rr_history)) if rr_history else 250.0

        if i + 1 < len(ordered):
            next_sample = int(ordered[i + 1].sample_index)
            post_rr = next_sample - sample
            if post_rr <= 0:
                raise ValueError(f"non-increasing native beat annotation: {beat.key}")
            post_rr_ratio = post_rr / median_rr
        else:
            post_rr = 0
            post_rr_ratio = 0.0

        comp_ratio = (pre_rr + post_rr) / (2.0 * median_rr)

        if sample < 64 or sample >= len(signal) - 96:
            continue
        full_window = extract_beat_window(signal, r_index=sample)
        centered = full_window.astype(np.float64) - np.median(full_window)
        peak = float(np.max(np.abs(centered)))
        amplitude_history.append(peak)
        amplitude_history = amplitude_history[-8:]
        median_amplitude = float(np.median(amplitude_history))
        amplitude_ratio = peak / median_amplitude if median_amplitude > 0 else 1.0

        if beat.key not in selected_keys or beat.native_symbol not in LABEL_BY_SYMBOL:
            continue
        # A post-RR decision is emitted only after a real previous and next QRS
        # exist. Never fabricate context at finite-record boundaries.
        if num_features > 4 and (not has_previous_context or not has_next_context):
            continue
        qrs_region = np.abs(centered[44:85])
        width_threshold = 0.3 * float(np.max(qrs_region)) if len(qrs_region) else 0.0
        qrs_width_ms = float(np.count_nonzero(qrs_region >= width_threshold) * 4) if width_threshold > 0 else 0.0
        sqi_window = _complete_sqi_window(signal, sample)
        sqi_score = continuous_sqi_score_q15_fixed([int(value) for value in sqi_window]) / 32767.0

        if num_features == 8:
            ectopic_coupling = float(max(0.0, 1.0 - pre_rr_ratio) * max(0.0, post_rr_ratio - 1.0))
            rr_diff = float(post_rr_ratio - pre_rr_ratio)
            raw_feat = [
                pre_rr_ratio,
                post_rr_ratio,
                comp_ratio,
                ectopic_coupling,
                rr_diff,
                qrs_width_ms,
                amplitude_ratio,
                sqi_score,
            ]
        elif num_features == 6:
            raw_feat = [pre_rr_ratio, post_rr_ratio, comp_ratio, qrs_width_ms, amplitude_ratio, sqi_score]
        elif num_features == 5:
            raw_feat = [pre_rr_ratio, post_rr_ratio, qrs_width_ms, amplitude_ratio, sqi_score]
        else:
            raw_feat = [pre_rr_ratio, qrs_width_ms, amplitude_ratio, sqi_score]

        examples.append(
            {
                "patient_id": beat.patient_id,
                "record_id": beat.record_id,
                "sample_index": sample,
                "native_symbol": beat.native_symbol,
                "source_file_sha256": beat.source_file_sha256,
                "label": LABEL_BY_SYMBOL[beat.native_symbol],
                "waveform": np.asarray(full_window, dtype=np.int16),
                "raw_features": np.asarray(raw_feat, dtype=np.float32),
                "previous_context_sample_index": int(ordered[i - 1].sample_index) if has_previous_context else -1,
                "next_context_sample_index": int(ordered[i + 1].sample_index) if has_next_context else -1,
            }
        )
    return examples


def finalize_split_arrays(
    examples_by_split: dict[str, list[dict[str, object]]]
) -> tuple[dict[str, dict[str, np.ndarray]], dict[str, object]]:
    required_splits = {"train", "validation", "internal_test"}
    if set(examples_by_split) != required_splits:
        raise ValueError(f"cache requires exactly {sorted(required_splits)}")
    if any(not examples_by_split[split] for split in required_splits):
        raise ValueError("every M2 cache split must contain examples")

    feature_widths = {
        int(np.asarray(row["raw_features"]).shape[0])
        for rows in examples_by_split.values()
        for row in rows
    }
    if len(feature_widths) != 1:
        raise ValueError(f"all cache splits must use one feature schema, got {sorted(feature_widths)}")
    num_features = feature_widths.pop()
    if num_features not in FEATURE_NAMES_BY_COUNT:
        raise ValueError(f"unsupported feature count: {num_features}")
    feature_names = FEATURE_NAMES_BY_COUNT[num_features]
    feature_contract_id = LOOKAHEAD_CONTRACT_ID if num_features > 4 else CAUSAL4_CONTRACT_ID
    latency_mode = "next_valid_qrs" if num_features > 4 else "fixed_post_window"

    train_windows = np.stack([np.asarray(row["waveform"]) for row in examples_by_split["train"]])
    train_features = np.stack(
        [np.asarray(row["raw_features"], dtype=np.float64) for row in examples_by_split["train"]]
    )
    waveform_scale = compute_train_waveform_scale(train_windows)
    feature_medians = np.median(train_features, axis=0)
    feature_q25 = np.percentile(train_features, 25, axis=0)
    feature_q75 = np.percentile(train_features, 75, axis=0)
    feature_iqrs = feature_q75 - feature_q25
    if np.any(feature_iqrs <= 0):
        raise ValueError(f"train-only feature IQR is zero at indices {np.where(feature_iqrs <= 0)[0].tolist()}")

    arrays_by_split: dict[str, dict[str, np.ndarray]] = {}
    for split, examples in examples_by_split.items():
        arrays_by_split[split] = {
            "waveforms": np.stack(
                [normalize_waveform_int8(np.asarray(row["waveform"]), waveform_scale) for row in examples]
            ),
            "features": np.stack(
                [
                    normalize_scalar_features_int8(
                        np.asarray(row["raw_features"]), feature_medians, feature_iqrs
                    )
                    for row in examples
                ]
            ),
            "labels": np.asarray([int(row["label"]) for row in examples], dtype=np.int64),
            "patient_ids": np.asarray([str(row["patient_id"]) for row in examples]),
            "database": np.asarray(["Icentia11k"] * len(examples)),
            "database_version": np.asarray(["1.0"] * len(examples)),
            "record_ids": np.asarray([str(row["record_id"]) for row in examples]),
            "sample_indices": np.asarray([int(row["sample_index"]) for row in examples], dtype=np.int64),
            "native_symbols": np.asarray([str(row["native_symbol"]) for row in examples]),
            "source_file_sha256": np.asarray([str(row["source_file_sha256"]) for row in examples]),
            "feature_names": np.asarray(feature_names),
            "feature_contract_id": np.asarray(feature_contract_id),
            "decision_latency_mode": np.asarray(latency_mode),
            "context_sample_indices": np.asarray(
                [
                    [
                        int(row.get("previous_context_sample_index", -1)),
                        int(row.get("next_context_sample_index", -1)),
                    ]
                    for row in examples
                ],
                dtype=np.int64,
            ),
        }
    normalization = {
        "statistics_source": "Icentia11k train split only",
        "waveform_scale_statistic": "abs_deviation_99_5_percentile",
        "waveform_scale_ref_lsb": waveform_scale,
        "microvolts_per_lsb": 5,
        "feature_medians": feature_medians.tolist(),
        "feature_iqrs": feature_iqrs.tolist(),
        "feature_names": feature_names,
        "feature_contract_id": feature_contract_id,
        "decision_latency_mode": latency_mode,
    }
    return arrays_by_split, normalization


def download_and_build_cache(
    audit_path: str | Path,
    source_root: str | Path,
    output_dir: str | Path,
    *,
    run_id: str,
    num_features: int = 4,
) -> dict[str, object]:
    import wfdb

    audit_file = Path(audit_path).resolve()
    source = Path(source_root).resolve()
    output = Path(output_dir).resolve()
    source.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)
    audit = json.loads(audit_file.read_text(encoding="utf-8"))
    if audit.get("database") != "Icentia11k" or audit.get("database_version") != "1.0":
        raise ValueError("annotation audit is not Icentia11k 1.0")
    if int(audit.get("error_count", -1)) != 0 or not audit.get("records"):
        raise ValueError("annotation audit is incomplete or contains errors")

    record_rows = sorted(
        audit["records"], key=lambda row: (str(row["split"]), str(row["patient_id"]), str(row["record_id"]))
    )
    relative_files = sorted(
        {
            relative
            for row in record_rows
            for relative in source_relative_files(str(row["patient_id"]), str(row["record_id"]))
        }
    )
    ensure_source_files(source, relative_files, downloader=wfdb.dl_files)

    inventory: list[dict[str, object]] = []
    hash_by_relative: dict[str, str] = {}
    for relative in relative_files:
        path = source / Path(relative)
        if not path.is_file():
            raise FileNotFoundError(f"downloaded source file is missing: {relative}")
        digest = _sha256_file(path)
        hash_by_relative[relative] = digest
        inventory.append({"relative_path": relative, "size_bytes": path.stat().st_size, "sha256": digest})

    beats_by_split: dict[str, list[NativeBeat]] = {"train": [], "validation": [], "internal_test": []}
    beats_by_record: dict[tuple[str, str], list[NativeBeat]] = {}
    q_excluded_by_split = {"train": 0, "validation": 0, "internal_test": 0}
    record_digest: dict[tuple[str, str], str] = {}
    for row in record_rows:
        split = str(row["split"])
        patient_id = str(row["patient_id"])
        record_id = str(row["record_id"])
        if split not in beats_by_split:
            raise ValueError(f"unexpected split in audit: {split}")
        relative = source_relative_files(patient_id, record_id)
        digest = combined_record_sha256({name: hash_by_relative[name] for name in relative})
        record_digest[(patient_id, record_id)] = digest
        record_base = source / patient_id[:3] / patient_id / record_id
        annotation = wfdb.rdann(str(record_base), "atr")
        native_beats = [
            NativeBeat(patient_id, record_id, int(sample), str(symbol), digest)
            for sample, symbol in zip(annotation.sample, annotation.symbol)
            if str(symbol) in {"N", "S", "V", "Q"}
        ]
        q_excluded_by_split[split] += sum(beat.native_symbol == "Q" for beat in native_beats)
        beats_by_split[split].extend(native_beats)
        beats_by_record[(patient_id, record_id)] = native_beats

    selected_by_split = {
        "train": select_training_beats(beats_by_split["train"], max_negative_per_positive=4),
        "validation": sorted(beat for beat in beats_by_split["validation"] if beat.native_symbol in LABEL_BY_SYMBOL),
        "internal_test": sorted(
            beat for beat in beats_by_split["internal_test"] if beat.native_symbol in LABEL_BY_SYMBOL
        ),
    }
    selected_keys = {split: {beat.key for beat in beats} for split, beats in selected_by_split.items()}
    examples_by_split: dict[str, list[dict[str, object]]] = {
        "train": [],
        "validation": [],
        "internal_test": [],
    }
    processed_by_split = {"train": 0, "validation": 0, "internal_test": 0}
    lookahead_excluded_by_split = {
        split: {"missing_previous": 0, "missing_next": 0, "missing_either": 0}
        for split in examples_by_split
    }
    for position, row in enumerate(record_rows, start=1):
        split = str(row["split"])
        patient_id = str(row["patient_id"])
        record_id = str(row["record_id"])
        record_base = source / patient_id[:3] / patient_id / record_id
        record = wfdb.rdrecord(str(record_base), physical=True)
        if float(record.fs) != 250.0 or int(record.n_sig) != 1:
            raise ValueError(f"unexpected Icentia signal contract for {record_id}: fs={record.fs}, n_sig={record.n_sig}")
        signal_mv = np.asarray(record.p_signal[:, 0], dtype=np.float64)
        if not np.isfinite(signal_mv).all():
            raise ValueError(f"non-finite signal samples in {record_id}")
        signal_lsb = np.clip(round_half_away_from_zero(signal_mv * 200.0), -32768, 32767).astype(np.int16)
        if num_features > 4:
            exclusion_counts = count_lookahead_context_exclusions(
                beats_by_record[(patient_id, record_id)], selected_keys=selected_keys[split]
            )
            for key, value in exclusion_counts.items():
                lookahead_excluded_by_split[split][key] += value
        examples = build_record_examples(
            signal_lsb,
            beats_by_record[(patient_id, record_id)],
            selected_keys=selected_keys[split],
            num_features=num_features,
        )
        examples_by_split[split].extend(examples)
        processed_by_split[split] += 1
        print(
            f"ICENTIA_CACHE {position}/{len(record_rows)} split={split} examples={len(examples_by_split[split])}",
            flush=True,
        )

    arrays_by_split, normalization = finalize_split_arrays(examples_by_split)
    split_summaries: dict[str, object] = {}
    for split, arrays in arrays_by_split.items():
        validation = validate_m2_cache_split(arrays, split_name=split)
        split_summaries[split] = {
            **validation,
            "q_excluded_count": q_excluded_by_split[split],
            "selected_before_boundary_check": len(selected_by_split[split]),
            "boundary_excluded_count": len(selected_by_split[split]) - len(arrays["labels"]),
            "lookahead_context_excluded": lookahead_excluded_by_split[split],
        }
        np.savez_compressed(output / f"{split}_beats.npz", **arrays)
    patient_counts = validate_patient_disjoint_splits(arrays_by_split)

    normalization_path = output / "normalization.json"
    normalization_path.write_text(json.dumps(normalization, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest: dict[str, object] = {
        "run_id": run_id,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "database": "Icentia11k",
        "database_version": "1.0",
        "source": PN_DIR,
        "annotation_audit_sha256": _sha256_file(audit_file),
        "record_count": len(record_rows),
        "source_file_count": len(inventory),
        "source_files": inventory,
        "splits": split_summaries,
        "patient_counts": patient_counts,
        "locked_databases_accessed": False,
        "label_source": "native WFDB atr symbols only; no feature-derived targets",
    }
    manifest_path = output / "dataset_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    config = {
        "run_id": run_id,
        "database": "Icentia11k 1.0",
        "sample_rate_hz": 250,
        "window_length": 160,
        "r_peak_index": 64,
        "num_features": num_features,
        "feature_names": FEATURE_NAMES_BY_COUNT[num_features],
        "feature_contract_id": LOOKAHEAD_CONTRACT_ID if num_features > 4 else CAUSAL4_CONTRACT_ID,
        "decision_latency_mode": "next_valid_qrs" if num_features > 4 else "fixed_post_window",
        "boundary_policy": (
            "first and final annotated beats are excluded and counted because real previous/next context is unavailable"
            if num_features > 4
            else "v1 fixed post-window policy"
        ),
        "train_negative_per_positive_max": 4,
        "validation_and_internal_test_prevalence": "natural within frozen cohort",
        "normalization_statistics": "train split only",
    }
    (output / "config.json").write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    output_hashes = []
    for path in sorted(output.iterdir(), key=lambda item: item.name):
        if path.is_file() and path.name != "sha256_manifest.txt":
            output_hashes.append(f"{_sha256_file(path)}  {path.name}")
    (output / "sha256_manifest.txt").write_text("\n".join(output_hashes) + "\n", encoding="ascii")
    return manifest


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a native-label Icentia11k M2 beat cache")
    parser.add_argument("--annotation-audit", required=True, type=Path)
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--num-features", type=int, default=4, choices=[4, 5, 6, 8])
    args = parser.parse_args(argv)
    manifest = download_and_build_cache(
        args.annotation_audit,
        args.source_root,
        args.output_dir,
        run_id=args.run_id,
        num_features=args.num_features,
    )
    print(json.dumps({key: value for key, value in manifest.items() if key != "source_files"}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
