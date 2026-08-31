"""Audit why the M2 train-only SQI feature has zero IQR."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import wfdb


PROJECT_ROOT = Path(__file__).resolve().parents[2]
EC57_ROOT = PROJECT_ROOT / "train" / "ec57"
if str(EC57_ROOT) not in sys.path:
    sys.path.insert(0, str(EC57_ROOT))

from beat_dataset import round_half_away_from_zero
from prepare_icentia_native_cache import NativeBeat, _complete_sqi_window, select_training_beats
from sqi import continuous_sqi_score_q15_fixed, evaluate_sqi_fixed


def summarize(values: list[float]) -> dict[str, object]:
    array = np.asarray(values, dtype=np.float64)
    q0, q25, q50, q75, q100 = np.percentile(array, [0, 25, 50, 75, 100])
    return {
        "count": int(len(array)),
        "min": float(q0),
        "q25": float(q25),
        "median": float(q50),
        "q75": float(q75),
        "max": float(q100),
        "iqr": float(q75 - q25),
        "unique_count": int(len(np.unique(array))),
    }


def audit(audit_path: Path, source_root: Path) -> dict[str, object]:
    source_audit = json.loads(audit_path.read_text(encoding="utf-8"))
    rows = sorted(
        (row for row in source_audit["records"] if row["split"] == "train"),
        key=lambda row: (row["patient_id"], row["record_id"]),
    )
    beats_by_record: dict[tuple[str, str], list[NativeBeat]] = {}
    all_beats: list[NativeBeat] = []
    for row in rows:
        patient = str(row["patient_id"])
        record_id = str(row["record_id"])
        base = source_root / patient[:3] / patient / record_id
        annotation = wfdb.rdann(str(base), "atr")
        beats = [
            NativeBeat(patient, record_id, int(sample), str(symbol), "0" * 64)
            for sample, symbol in zip(annotation.sample, annotation.symbol)
            if str(symbol) in {"N", "S", "V"}
        ]
        beats_by_record[(patient, record_id)] = beats
        all_beats.extend(beats)
    selected = select_training_beats(all_beats, max_negative_per_positive=4)
    selected_keys = {beat.key for beat in selected}

    measures: dict[str, list[float]] = {
        "original_score": [],
        "continuous_score_q15": [],
        "peak_to_peak_uv": [],
        "std_uv": [],
        "std_to_peak_ratio": [],
        "differential_noise_fraction": [],
        "saturation_fraction": [],
    }
    symbol_counts: Counter[str] = Counter()
    validity_counts: Counter[str] = Counter()
    for position, row in enumerate(rows, start=1):
        patient = str(row["patient_id"])
        record_id = str(row["record_id"])
        base = source_root / patient[:3] / patient / record_id
        record = wfdb.rdrecord(str(base), physical=True)
        signal_mv = np.asarray(record.p_signal[:, 0], dtype=np.float64)
        signal_lsb = np.clip(round_half_away_from_zero(signal_mv * 200.0), -32768, 32767).astype(np.int16)
        for beat in beats_by_record[(patient, record_id)]:
            if beat.key not in selected_keys or beat.sample_index < 64 or beat.sample_index >= len(signal_lsb) - 96:
                continue
            quality = evaluate_sqi_fixed([int(value) for value in _complete_sqi_window(signal_lsb, beat.sample_index)])
            original = 0.0 if not quality.valid else max(
                0.0,
                1.0 - quality.differential_noise_fraction - quality.saturation_fraction,
            )
            measures["original_score"].append(original)
            measures["continuous_score_q15"].append(
                float(continuous_sqi_score_q15_fixed([int(value) for value in _complete_sqi_window(signal_lsb, beat.sample_index)]))
            )
            measures["peak_to_peak_uv"].append(quality.peak_to_peak_uv)
            measures["std_uv"].append(quality.std_uv)
            measures["std_to_peak_ratio"].append(quality.std_uv / max(quality.peak_to_peak_uv, 1.0))
            measures["differential_noise_fraction"].append(quality.differential_noise_fraction)
            measures["saturation_fraction"].append(quality.saturation_fraction)
            symbol_counts[beat.native_symbol] += 1
            validity_counts["valid" if quality.valid else "invalid"] += 1
        print(f"ICENTIA_SQI_AUDIT {position}/{len(rows)}", flush=True)
    return {
        "database": "Icentia11k",
        "database_version": "1.0",
        "scope": "frozen M2a train cohort and selected 1:4 native beats",
        "record_count": len(rows),
        "symbol_counts": dict(sorted(symbol_counts.items())),
        "validity_counts": dict(sorted(validity_counts.items())),
        "measures": {name: summarize(values) for name, values in measures.items()},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--annotation-audit", required=True, type=Path)
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = audit(args.annotation_audit.resolve(), args.source_root.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    args.output.write_text(payload, encoding="utf-8")
    digest = hashlib.sha256(args.output.read_bytes()).hexdigest()
    (args.output.parent / "sha256_manifest.txt").write_text(
        f"{digest}  {args.output.name}\n", encoding="ascii"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
