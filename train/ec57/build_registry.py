"""Read-only dataset registry and leakage guards for the EC57 M1 path.

This module never downloads data.  It inventories roots supplied by the
caller, hashes files, applies the frozen role policy, and writes metadata
manifests when explicitly asked to do so.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path, PureWindowsPath
from typing import Iterable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ROLE_REGISTRY = ROOT / "docs" / "datasets" / "data_role_registry.csv"
FORBIDDEN_CONTEXTS = frozenset(
    {"train", "calibration", "ptq", "qat", "golden", "debug", "board_debug"}
)
ALLOWED_CONTEXTS = FORBIDDEN_CONTEXTS | {"inventory", "qrs_development"}
TARGET_LEADS = [
    "I",
    "II",
    "III",
    "aVR",
    "aVL",
    "aVF",
    "V1",
    "V2",
    "V3",
    "V4",
    "V5",
    "V6",
]
REQUIRED_REGISTRY_COLUMNS = {
    "database",
    "version",
    "role",
    "scope",
    "tasks",
    "allowed_uses",
    "prohibited_uses",
    "license",
    "license_restriction",
    "patient_grouping_key",
    "native_lead_count",
    "native_sampling_hz",
    "freeze_date",
    "status",
    "notes",
}


class RegistryError(ValueError):
    """Raised when a registry, path, split, or manifest operation is unsafe."""


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slug(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_").lower()
    return value or "dataset"


def load_role_registry(path: str | Path = DEFAULT_ROLE_REGISTRY) -> list[dict[str, str]]:
    path = Path(path)
    if not path.is_file():
        raise RegistryError(f"role registry is missing: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = set(reader.fieldnames or [])
        missing = REQUIRED_REGISTRY_COLUMNS - columns
        if missing:
            raise RegistryError(f"role registry columns missing: {sorted(missing)}")
        rows = list(reader)
    if not rows:
        raise RegistryError("role registry is empty")
    for row in rows:
        if not row.get("database") or not row.get("role"):
            raise RegistryError("role registry contains a row without database or role")
    return rows


def _rows_by_database(rows: Sequence[Mapping[str, str]]) -> dict[str, Mapping[str, str]]:
    result: dict[str, Mapping[str, str]] = {}
    for row in rows:
        name = str(row.get("database", ""))
        if not name or name in result:
            raise RegistryError(f"duplicate or empty database role: {name!r}")
        result[name] = row
    return result


def validate_dataset_configuration(
    configuration: Mapping[str, Iterable[str]],
    rows: Sequence[Mapping[str, str]],
) -> None:
    """Reject locked database names in all development/calibration contexts."""
    by_database = _rows_by_database(rows)
    for context, databases in configuration.items():
        if context not in ALLOWED_CONTEXTS:
            raise RegistryError(f"unknown dataset usage/context: {context!r}")
        for database in databases:
            if database not in by_database:
                raise RegistryError(f"database is not registered: {database}")
            if context in FORBIDDEN_CONTEXTS and by_database[database].get("role") == "locked":
                raise RegistryError(f"locked database {database} cannot enter {context}")


def _windows_path(value: str | Path) -> PureWindowsPath:
    """Return a case-folded absolute lexical Windows path.

    Configuration paths are validated without touching the host filesystem.
    Relative paths and parent traversal are rejected because their meaning
    depends on the caller's working directory and can bypass locked roots.
    """
    raw = str(value).replace("/", "\\")
    path = PureWindowsPath(raw)
    if not path.is_absolute():
        raise RegistryError(f"dataset path must be absolute: {value}")
    if ".." in path.parts:
        raise RegistryError(f"parent traversal is not allowed in dataset path: {value}")
    return PureWindowsPath(str(path).casefold())


def validate_locked_roots(
    configuration: Mapping[str, Iterable[str | Path]],
    locked_roots: Iterable[str | Path],
) -> None:
    """Reject each locked root and every descendant in a forbidden context.

    PureWindowsPath is used deliberately so the check is deterministic for
    configuration files even when a manifest is inspected on another host.
    """
    roots = [_windows_path(root) for root in locked_roots]
    for context, configured_paths in configuration.items():
        if context not in ALLOWED_CONTEXTS:
            raise RegistryError(f"unknown dataset usage/context: {context!r}")
        for configured_path in configured_paths:
            candidate = _windows_path(configured_path)
            if context in FORBIDDEN_CONTEXTS:
                for root in roots:
                    if candidate == root or root in candidate.parents:
                        raise RegistryError(f"locked root {root} cannot enter {context}")


def assign_icentia_split(patient_id: str) -> str:
    """Apply SHA-256(patient_id) integer modulo 100 and the frozen 80/10/10 split."""
    if not isinstance(patient_id, str) or not patient_id:
        raise RegistryError("patient_id must be a non-empty string")
    bucket = int(hashlib.sha256(patient_id.encode("utf-8")).hexdigest(), 16) % 100
    if bucket <= 79:
        return "train"
    if bucket <= 89:
        return "validation"
    return "internal_test"


def validate_icentia_splits(splits: Mapping[str, Iterable[str]]) -> dict[str, str]:
    """Validate explicit Icentia assignments against the frozen hash buckets."""
    ownership = validate_patient_assignments(splits)
    for patient_id, split in ownership.items():
        expected = assign_icentia_split(patient_id)
        if split != expected:
            raise RegistryError(f"Icentia patient {patient_id} assigned to {split}; expected {expected}")
    return ownership


def validate_patient_assignments(splits: Mapping[str, Iterable[str]]) -> dict[str, str]:
    """Return patient ownership and fail on duplicates or cross-split leakage."""
    ownership: dict[str, str] = {}
    for split, patient_ids in splits.items():
        if split not in {"train", "validation", "internal_test", "locked"}:
            raise RegistryError(f"unknown patient split: {split}")
        for patient_id in patient_ids:
            patient_id = str(patient_id)
            if not patient_id:
                raise RegistryError("empty patient_id is not allowed")
            if patient_id in ownership:
                previous = ownership[patient_id]
                raise RegistryError(f"patient {patient_id} occurs in {previous} and {split}")
            ownership[patient_id] = split
    return ownership


def sha256_file(path: str | Path, chunk_size: int = 1024 * 1024) -> str:
    path = Path(path)
    if not path.is_file():
        raise RegistryError(f"file is missing: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical_hash(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256_bytes(payload)


def build_file_inventory(root: str | Path) -> list[dict[str, str | int]]:
    """Inventory and hash all regular files under an existing root.

    Symlinks are rejected rather than followed so a manifest cannot silently
    include data outside the registered root.
    """
    root = Path(root)
    if not root.is_dir():
        raise RegistryError(f"data root is missing or not a directory: {root}")
    inventory: list[dict[str, str | int]] = []
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix().lower()):
        if path.is_symlink():
            raise RegistryError(f"symlink is not allowed in data root: {path}")
        if path.is_file():
            inventory.append(
                {
                    "relative_path": path.relative_to(root).as_posix(),
                    "size_bytes": path.stat().st_size,
                    "sha256": sha256_file(path),
                }
            )
    validate_file_inventory(inventory)
    return inventory


def validate_file_inventory(inventory: Sequence[Mapping[str, object]]) -> None:
    """Fail closed if any inventory item lacks an auditable file hash."""
    for item in inventory:
        if not isinstance(item, Mapping):
            raise RegistryError("file inventory item must be a mapping")
        relative_path = item.get("relative_path")
        digest = item.get("sha256")
        if not isinstance(relative_path, str) or not relative_path:
            raise RegistryError("file inventory item has no relative_path")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", digest):
            raise RegistryError(f"file inventory item has missing or invalid sha256: {relative_path}")


def _parse_rate(row: Mapping[str, str]) -> float:
    try:
        return float(row["native_sampling_hz"])
    except (KeyError, TypeError, ValueError) as exc:
        raise RegistryError(f"invalid native sampling rate for {row.get('database')}") from exc


def _record_metadata(record: Mapping[str, object]) -> dict[str, object]:
    required = {"record_id", "patient_id", "split", "duration_s", "raw_files", "record_sha256"}
    missing = required - set(record)
    if missing:
        raise RegistryError(f"record metadata missing fields: {sorted(missing)}")
    raw_files = record["raw_files"]
    if not isinstance(raw_files, list) or not raw_files:
        raise RegistryError(f"record {record['record_id']} must list raw files")
    if not isinstance(record["record_sha256"], str) or not re.fullmatch(r"[0-9a-fA-F]{64}", record["record_sha256"]):
        raise RegistryError(f"record {record['record_id']} has missing or invalid record_sha256")
    validate_file_inventory(raw_files)
    return dict(record)


def build_registry(
    data_roots: Mapping[str, str | Path],
    output_dir: str | Path,
    *,
    registry_path: str | Path = DEFAULT_ROLE_REGISTRY,
    usage: str = "inventory",
    records_by_database: Mapping[str, Sequence[Mapping[str, object]]] | None = None,
    patient_splits_by_database: Mapping[str, Mapping[str, Iterable[str]]] | None = None,
) -> list[Path]:
    """Build metadata manifests and split lists for caller-supplied existing roots."""
    rows = load_role_registry(registry_path)
    by_database = _rows_by_database(rows)
    data_roots = dict(data_roots)
    if not data_roots:
        raise RegistryError("at least one existing data root is required")
    unknown_databases = set(data_roots) - set(by_database)
    if unknown_databases:
        raise RegistryError(f"database is not registered: {sorted(unknown_databases)}")
    validate_dataset_configuration({usage: data_roots.keys()}, rows)
    locked_root_values = [root for name, root in data_roots.items() if by_database[name]["role"] == "locked"]
    validate_locked_roots({usage: data_roots.values()}, locked_root_values)

    records_by_database = records_by_database or {}
    patient_splits_by_database = patient_splits_by_database or {}
    unknown_record_databases = set(records_by_database) - set(data_roots)
    unknown_split_databases = set(patient_splits_by_database) - set(data_roots)
    if unknown_record_databases or unknown_split_databases:
        raise RegistryError(
            "metadata supplied for an unregistered root: "
            f"{sorted(unknown_record_databases | unknown_split_databases)}"
        )

    # Complete all read-only validation before creating an output directory.
    # This prevents a rejected configuration from leaving partial manifests.
    prepared: dict[str, dict[str, object]] = {}
    global_patient_splits: dict[str, list[str]] = {
        "train": [],
        "validation": [],
        "internal_test": [],
        "locked": [],
    }
    for database, root_value in data_roots.items():
        row = by_database[database]
        root = Path(root_value)
        inventory = build_file_inventory(root)
        inventory_by_path = {str(item["relative_path"]): item for item in inventory}
        explicit_records = [_record_metadata(item) for item in records_by_database.get(database, [])]
        supplied_splits = {
            split: [str(patient_id) for patient_id in patient_ids]
            for split, patient_ids in patient_splits_by_database.get(database, {}).items()
        }

        combined_splits: dict[str, list[str]] = {
            "train": [],
            "validation": [],
            "internal_test": [],
            "locked": [],
        }
        for split, patient_ids in supplied_splits.items():
            if split not in combined_splits:
                raise RegistryError(f"unknown patient split: {split}")
            combined_splits[split].extend(patient_ids)

        for record in explicit_records:
            split = str(record["split"])
            patient_id = str(record["patient_id"])
            if split not in combined_splits:
                raise RegistryError(f"unknown record split: {split}")
            if row["role"] == "locked" and split != "locked":
                raise RegistryError(
                    f"locked database {database} record {record['record_id']} cannot enter {split}"
                )
            combined_splits[split].append(patient_id)

            for raw_file in record["raw_files"]:
                relative_path = str(raw_file["relative_path"])
                relative = PureWindowsPath(relative_path.replace("/", "\\"))
                if relative.is_absolute() or ".." in relative.parts:
                    raise RegistryError(
                        f"record {record['record_id']} contains an unsafe raw file path: {relative_path}"
                    )
                inventory_item = inventory_by_path.get(relative_path.replace("\\", "/"))
                if inventory_item is None:
                    raise RegistryError(
                        f"record {record['record_id']} references a file outside the inventory: {relative_path}"
                    )
                if (
                    int(raw_file.get("size_bytes", -1)) != int(inventory_item["size_bytes"])
                    or str(raw_file["sha256"]).casefold() != str(inventory_item["sha256"]).casefold()
                ):
                    raise RegistryError(
                        f"record {record['record_id']} raw file hash/size does not match inventory: {relative_path}"
                    )
            if len(record["raw_files"]) == 1:
                only_hash = str(record["raw_files"][0]["sha256"])
                if str(record["record_sha256"]).casefold() != only_hash.casefold():
                    raise RegistryError(f"record {record['record_id']} record_sha256 does not match its raw file")

        if database == "Icentia11k":
            validate_icentia_splits(combined_splits)
        else:
            validate_patient_assignments(combined_splits)
        for split, patient_ids in combined_splits.items():
            global_patient_splits[split].extend(f"{database}:{patient_id}" for patient_id in patient_ids)
        prepared[database] = {
            "row": row,
            "root": root,
            "inventory": inventory,
            "explicit_records": explicit_records,
            "supplied_splits": supplied_splits,
            "combined_splits": combined_splits,
        }

    validate_patient_assignments(global_patient_splits)

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    split_lines: dict[str, list[str]] = {
        "train": [],
        "validation": [],
        "internal_test": [],
        "locked": [],
    }
    manifest_paths: list[Path] = []

    for database in data_roots:
        item = prepared[database]
        row = item["row"]
        root = item["root"]
        inventory = item["inventory"]
        explicit_records = item["explicit_records"]
        supplied_splits = item["supplied_splits"]
        assignments: list[dict[str, str]] = []
        if supplied_splits:
            for split, patient_ids in supplied_splits.items():
                for patient_id in patient_ids:
                    assignments.append({"patient_id": str(patient_id), "split": split})
                    split_lines[split].append(f"{database}\t{patient_id}")
        for record in explicit_records:
            split = str(record["split"])
            patient_id = str(record["patient_id"])
            assignments.append({"patient_id": patient_id, "split": split})
            split_lines[split].append(f"{database}\t{patient_id}")
        if row["role"] == "locked":
            split_lines["locked"].extend(f"{database}\t{record['record_id']}" for record in explicit_records)

        source_rate = _parse_rate(row)
        target_order = TARGET_LEADS if int(float(row["native_lead_count"])) == 12 else ["single_fixed_lead"]
        annotation_hash = _canonical_hash(explicit_records)
        manifest = {
            "schema_version": "1.0.0",
            "manifest_id": f"{_slug(database)}-{row['version']}-{usage}",
            "created_at": _timestamp(),
            "database": {
                "name": database,
                "version": row["version"],
                "license": row["license"],
                "role": row["role"],
                "license_restriction": row["license_restriction"],
            },
            "source": {
                "official_url": f"registry://{_slug(database)}",
                "doi": None,
                "root_uri": str(root),
            },
            "role": row["role"],
            "purpose": [item for item in row["tasks"].split(";") if item],
            "sampling": {
                "native_rate_hz": source_rate,
                "target_rate_hz": 250,
                "resampling_required": source_rate != 250,
                "resampling_method": "rational_polyphase",
                "sample_count_policy": "record exact counts; no silent crop or pad",
            },
            "leads": {
                "native_count": int(float(row["native_lead_count"])),
                "native_order": target_order,
                "target_count": 12,
                "target_order": TARGET_LEADS,
                "unit": "uV",
                "microvolts_per_lsb": 5,
            },
            "patient_split": {
                "strategy": "SHA-256(patient_id) mod 100" if database == "Icentia11k" else "registry-supplied patient grouping",
                "patient_key": row["patient_grouping_key"],
                "assignments": assignments,
                "split_hash": _canonical_hash(assignments),
            },
            "records": explicit_records,
            "annotations": {
                "source_format": "registered source annotations; format must be supplied per dataset",
                "mapping_contract": "contracts/ec57_label_mapping_v1.json" if database == "Icentia11k" else "not_applicable_to_m0",
                "source_labels": [],
                "excluded_labels": [],
                "unmapped_policy": "fail closed and preserve raw label",
            },
            "hashes": {
                "raw_files_sha256": [item["sha256"] for item in inventory],
                "annotation_sha256": annotation_hash,
            },
            "resampler": {
                "name": "ec57.rational_polyphase",
                "version": "1.0.0",
                "method": "rational_polyphase",
                "source_rate_hz": source_rate,
                "target_rate_hz": 250,
                "timestamp_tolerance_ms": 2,
            },
            "exclusions": [
                {
                    "record_id": "__UNREGISTERED_FILES__",
                    "reason": "file inventory exists but record metadata was not supplied",
                    "counted_in_report": True,
                }
            ] if inventory and not explicit_records else [],
            "provenance": {
                "generated_by": "train/ec57/build_registry.py",
                "generator_version": "1.0.0",
                "io_contract": "contracts/ec57_hybrid_io_contract.json",
                "label_mapping_contract": "contracts/ec57_label_mapping_v1.json",
                "created_without_download": True,
            },
        }
        manifest_path = output_dir / f"{_slug(database)}_{_slug(row['version'])}_{_slug(usage)}_dataset_manifest.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        manifest_paths.append(manifest_path)

    for split, lines in split_lines.items():
        path = output_dir / f"{split}_patients.txt" if split != "locked" else output_dir / "locked_records.txt"
        path.write_text("\n".join(sorted(set(lines))) + ("\n" if lines else ""), encoding="utf-8")
        written.append(path)
    written.extend(manifest_paths)
    return written


def _parse_root_argument(value: str) -> tuple[str, str]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("root must be DATABASE=PATH")
    database, root = value.split("=", 1)
    if not database or not root:
        raise argparse.ArgumentTypeError("root must be DATABASE=PATH")
    return database, root


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inventory existing ECG roots without downloading data")
    parser.add_argument("--root", action="append", required=True, type=_parse_root_argument, metavar="DATABASE=PATH")
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--registry", type=Path, default=DEFAULT_ROLE_REGISTRY)
    parser.add_argument("--usage", default="inventory", choices=sorted(ALLOWED_CONTEXTS))
    args = parser.parse_args(argv)
    build_registry(dict(args.root), args.output_dir, registry_path=args.registry, usage=args.usage)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
