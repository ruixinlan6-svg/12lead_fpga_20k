"""Strict LUDB 1.0.1 loading, annotation construction, and inventory helpers."""

from __future__ import annotations

import hashlib
import math
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

from resample import resample_signal


CANONICAL_LEADS = ("I", "II", "III", "aVR", "aVL", "aVF", "V1", "V2", "V3", "V4", "V5", "V6")
LEAD_ANNOTATION_EXTENSIONS = {
    "I": "i",
    "II": "ii",
    "III": "iii",
    "aVR": "avr",
    "aVL": "avl",
    "aVF": "avf",
    "V1": "v1",
    "V2": "v2",
    "V3": "v3",
    "V4": "v4",
    "V5": "v5",
    "V6": "v6",
}
LUDB_VERSION = "1.0.1"
LUDB_SOURCE_URL = "https://physionet.org/files/ludb/1.0.1/"
LUDB_LICENSE = "Open Data Commons Attribution License v1.0"
SOURCE_RATE_HZ = 500
TARGET_RATE_HZ = 250
EXPECTED_SAMPLE_COUNT = 5000


class LUDBRecordError(ValueError):
    """Raised when LUDB bytes or metadata violate the frozen M1 contract."""


@dataclass(frozen=True)
class ReferenceQRS:
    source_sample_median: float
    source_time_s: float
    target_sample_index: int
    target_time_s: float
    mapping_error_ms: float
    contributing_leads: tuple[str, ...]


@dataclass(frozen=True)
class LoadedLUDBRecord:
    record_id: str
    signals_lsb_250: dict[str, list[float]]
    reference_qrs: tuple[ReferenceQRS, ...]
    annotation_counts_by_lead: dict[str, int]


def _round_half_away_from_zero(value: float) -> int:
    if value < 0:
        return -math.floor(abs(value) + 0.5)
    return math.floor(value + 0.5)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _normalize_lead(name: str) -> str:
    normalized = str(name).strip().lower()
    mapping = {lead.lower(): lead for lead in CANONICAL_LEADS}
    if normalized not in mapping:
        raise LUDBRecordError(f"unknown LUDB lead name: {name!r}")
    return mapping[normalized]


def physical_mv_to_interface_lsb(values_mv: Sequence[float]) -> list[int]:
    """Convert WFDB physical millivolts to signed int16 at 5 microvolts/LSB."""
    converted: list[int] = []
    for raw in values_mv:
        value = float(raw)
        if not math.isfinite(value):
            raise LUDBRecordError("LUDB signal contains a non-finite physical sample")
        quantized = _round_half_away_from_zero(value * 1000.0 / 5.0)
        converted.append(min(max(quantized, -32768), 32767))
    return converted


def validate_ludb_record(
    *,
    sample_rate_hz: float,
    sample_count: int,
    signal_names: Sequence[str],
    annotation_peaks_by_lead: Mapping[str, Sequence[int]],
) -> None:
    if float(sample_rate_hz) != SOURCE_RATE_HZ:
        raise LUDBRecordError(f"LUDB source sampling rate must be {SOURCE_RATE_HZ} Hz")
    if int(sample_count) != EXPECTED_SAMPLE_COUNT:
        raise LUDBRecordError(f"LUDB record must contain exactly {EXPECTED_SAMPLE_COUNT} samples")
    normalized = [_normalize_lead(name) for name in signal_names]
    if len(normalized) != len(set(normalized)) or set(normalized) != set(CANONICAL_LEADS):
        raise LUDBRecordError("LUDB record must contain each canonical lead exactly once")
    if set(annotation_peaks_by_lead) != set(CANONICAL_LEADS):
        raise LUDBRecordError("LUDB record must contain all 12 lead-specific annotation streams")
    for lead, peaks in annotation_peaks_by_lead.items():
        previous = -1
        for peak in peaks:
            if not isinstance(peak, int) or peak < 0 or peak >= EXPECTED_SAMPLE_COUNT:
                raise LUDBRecordError(f"invalid QRS annotation sample for {lead}: {peak!r}")
            if peak <= previous:
                raise LUDBRecordError(f"QRS annotations for {lead} are not strictly increasing")
            previous = peak


def cluster_reference_qrs(
    peaks_by_lead: Mapping[str, Sequence[int]],
    *,
    source_rate_hz: int = SOURCE_RATE_HZ,
    target_rate_hz: int = TARGET_RATE_HZ,
    max_span_ms: float = 150.0,
) -> list[ReferenceQRS]:
    """Cluster independent per-lead manual QRS peaks and take their median time."""
    if source_rate_hz <= 0 or target_rate_hz <= 0 or max_span_ms <= 0:
        raise LUDBRecordError("invalid reference clustering configuration")
    max_span_samples = max_span_ms * source_rate_hz / 1000.0
    flat: list[tuple[int, str]] = []
    for raw_lead, raw_peaks in peaks_by_lead.items():
        lead = _normalize_lead(raw_lead)
        peaks = list(raw_peaks)
        if any(not isinstance(peak, int) or peak < 0 for peak in peaks):
            raise LUDBRecordError(f"invalid QRS peak for lead {lead}")
        if peaks != sorted(set(peaks)):
            raise LUDBRecordError(f"QRS peaks for lead {lead} must be unique and ordered")
        if any(right - left <= max_span_samples for left, right in zip(peaks, peaks[1:])):
            raise LUDBRecordError(f"lead {lead} has two QRS peaks inside one 150 ms cluster")
        flat.extend((peak, lead) for peak in peaks)
    flat.sort(key=lambda item: (item[0], CANONICAL_LEADS.index(item[1])))
    groups: list[list[tuple[int, str]]] = []
    for peak, lead in flat:
        if not groups:
            groups.append([(peak, lead)])
            continue
        current = groups[-1]
        current_leads = {item[1] for item in current}
        if peak - current[0][0] <= max_span_samples and lead not in current_leads:
            current.append((peak, lead))
        else:
            groups.append([(peak, lead)])
    references: list[ReferenceQRS] = []
    for group in groups:
        source_median = float(statistics.median(item[0] for item in group))
        source_time = source_median / source_rate_hz
        target_index = _round_half_away_from_zero(source_time * target_rate_hz)
        target_time = target_index / target_rate_hz
        error_ms = abs(target_time - source_time) * 1000.0
        if error_ms > 2.0 + 1e-12:
            raise LUDBRecordError(f"annotation mapping error {error_ms:.6f} ms exceeds 2 ms")
        references.append(
            ReferenceQRS(
                source_sample_median=source_median,
                source_time_s=source_time,
                target_sample_index=target_index,
                target_time_s=target_time,
                mapping_error_ms=error_ms,
                contributing_leads=tuple(sorted((item[1] for item in group), key=CANONICAL_LEADS.index)),
            )
        )
    return references


def discover_ludb_records(root: str | Path, *, expected_count: int = 200) -> list[str]:
    root = Path(root).resolve()
    records_path = root / "RECORDS"
    if not records_path.is_file():
        raise LUDBRecordError("LUDB RECORDS file is missing")
    records = [line.strip().replace("\\", "/") for line in records_path.read_text(encoding="ascii").splitlines() if line.strip()]
    if len(records) != expected_count or len(records) != len(set(records)):
        raise LUDBRecordError(f"LUDB RECORDS must list exactly {expected_count} unique records")
    for record_id in records:
        candidate = (root / f"{record_id}.hea").resolve()
        if not candidate.is_relative_to(root) or not candidate.is_file():
            raise LUDBRecordError(f"unsafe or missing LUDB record header: {record_id}")
    return records


def build_sha256_inventory(root: str | Path) -> list[dict[str, object]]:
    root = Path(root).resolve()
    if not root.is_dir():
        raise LUDBRecordError("LUDB inventory root is not a directory")
    inventory: list[dict[str, object]] = []
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        if path.is_symlink():
            raise LUDBRecordError(f"symlink is forbidden in LUDB root: {path.relative_to(root).as_posix()}")
        if not path.is_file():
            continue
        inventory.append(
            {
                "relative_path": path.relative_to(root).as_posix(),
                "size_bytes": path.stat().st_size,
                "sha256": _sha256_file(path),
            }
        )
    if not inventory:
        raise LUDBRecordError("LUDB inventory is empty")
    return inventory


def verify_published_sha256s(root: str | Path) -> dict[str, object]:
    root = Path(root).resolve()
    sums_path = root / "SHA256SUMS.txt"
    if not sums_path.is_file():
        raise LUDBRecordError("official SHA256SUMS.txt is missing")
    verified = 0
    for line_number, raw_line in enumerate(sums_path.read_text(encoding="ascii").splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        parts = line.split(maxsplit=1)
        if len(parts) != 2 or len(parts[0]) != 64:
            raise LUDBRecordError(f"invalid SHA256SUMS.txt line {line_number}")
        expected, relative_text = parts
        relative_text = relative_text.lstrip("*").replace("\\", "/")
        path = (root / relative_text).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise LUDBRecordError(f"unsafe or missing published file: {relative_text}")
        actual = _sha256_file(path)
        if actual.lower() != expected.lower():
            raise LUDBRecordError(f"published SHA-256 mismatch: {relative_text}")
        verified += 1
    if verified == 0:
        raise LUDBRecordError("official SHA256SUMS.txt has no verifiable entries")
    return {
        "sha256s_file": "SHA256SUMS.txt",
        "sha256s_file_sha256": _sha256_file(sums_path),
        "verified_file_count": verified,
    }


def load_ludb_record(root: str | Path, record_id: str) -> LoadedLUDBRecord:
    """Load one verified WFDB record. Imports third-party dependencies lazily."""
    try:
        import wfdb  # type: ignore
    except ImportError as exc:  # pragma: no cover - exercised in the remote integration environment
        raise LUDBRecordError("wfdb is required for real LUDB parsing") from exc

    root = Path(root).resolve()
    record_base = (root / record_id).resolve()
    if not record_base.is_relative_to(root) or not record_base.with_suffix(".hea").is_file():
        raise LUDBRecordError(f"unsafe or missing LUDB record: {record_id}")
    record = wfdb.rdrecord(str(record_base), physical=True)
    if record.p_signal is None:
        raise LUDBRecordError(f"record {record_id} has no physical signal")
    signal_names = [_normalize_lead(name) for name in record.sig_name]
    peaks_by_lead: dict[str, list[int]] = {}
    for lead, extension in LEAD_ANNOTATION_EXTENSIONS.items():
        annotation = wfdb.rdann(str(record_base), extension)
        peaks_by_lead[lead] = [int(sample) for sample, symbol in zip(annotation.sample, annotation.symbol) if symbol == "N"]
    validate_ludb_record(
        sample_rate_hz=record.fs,
        sample_count=record.sig_len,
        signal_names=signal_names,
        annotation_peaks_by_lead=peaks_by_lead,
    )
    signals: dict[str, list[float]] = {}
    for column, lead in enumerate(signal_names):
        source_lsb = physical_mv_to_interface_lsb(record.p_signal[:, column].tolist())
        target = resample_signal(source_lsb, SOURCE_RATE_HZ, TARGET_RATE_HZ)
        if len(target) != EXPECTED_SAMPLE_COUNT // 2:
            raise LUDBRecordError(f"record {record_id} resampled to an unexpected length")
        signals[lead] = target
    references = cluster_reference_qrs(peaks_by_lead)
    return LoadedLUDBRecord(
        record_id=record_id,
        signals_lsb_250=signals,
        reference_qrs=tuple(references),
        annotation_counts_by_lead={lead: len(peaks) for lead, peaks in peaks_by_lead.items()},
    )


if __name__ == "__main__":
    raise SystemExit("Use evaluate_ludb.py; this module never downloads data implicitly.")
