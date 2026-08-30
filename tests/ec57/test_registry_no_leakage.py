from __future__ import annotations

import csv
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "train" / "ec57"))

from build_registry import (
    RegistryError,
    assign_icentia_split,
    build_registry,
    build_file_inventory,
    load_role_registry,
    validate_dataset_configuration,
    validate_file_inventory,
    validate_icentia_splits,
    validate_locked_roots,
    validate_patient_assignments,
)


ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = ROOT / "docs" / "datasets" / "data_role_registry.csv"


class TestRegistryNoLeakage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = load_role_registry(REGISTRY_PATH)

    def test_required_roles_and_locked_contexts_are_loaded(self):
        by_name = {row["database"]: row for row in self.rows}
        self.assertEqual(by_name["Icentia11k"]["role"], "development/internal")
        self.assertEqual(by_name["LUDB"]["scope"], "QRS and delineation development")
        for name in (
            "INCART",
            "MIT-BIH Arrhythmia",
            "AHA Ventricular Arrhythmia",
            "MIT-BIH Noise Stress Test",
        ):
            self.assertEqual(by_name[name]["role"], "locked")

    def test_locked_database_name_is_rejected_in_every_forbidden_context(self):
        for context in ("train", "calibration", "ptq", "qat", "golden", "debug", "board_debug"):
            with self.subTest(context=context):
                with self.assertRaises(RegistryError):
                    validate_dataset_configuration({context: ["MIT-BIH Arrhythmia"]}, self.rows)

    def test_unknown_usage_and_context_fail_closed(self):
        for context in ("training", "threshold-selection", "", "Inventory"):
            with self.subTest(context=context):
                with self.assertRaises(RegistryError):
                    validate_dataset_configuration({context: ["Icentia11k"]}, self.rows)
                with self.assertRaises(RegistryError):
                    validate_locked_roots({context: [r"D:\ecg\development\icentia"]}, [])
        with tempfile.TemporaryDirectory() as data_dir, tempfile.TemporaryDirectory() as output_dir:
            (Path(data_dir) / "sample.dat").write_bytes(b"synthetic")
            with self.assertRaises(RegistryError):
                build_registry({"Icentia11k": data_dir}, output_dir, usage="training")

    def test_locked_root_and_descendant_are_rejected(self):
        locked_roots = [r"D:\ecg\locked\mitdb"]
        for candidate in (
            r"D:\ecg\locked\mitdb",
            r"D:\ecg\locked\mitdb\100.dat",
            r"d:\ECG\LOCKED\MITDB\nested\record.atr",
        ):
            with self.subTest(candidate=candidate):
                with self.assertRaises(RegistryError):
                    validate_locked_roots({"train": [candidate]}, locked_roots)
        validate_locked_roots({"train": [r"D:\ecg\development\icentia11k"]}, locked_roots)

    def test_locked_root_aliases_and_parent_segments_fail_closed(self):
        locked_roots = ["D:\\ECG\\locked\\mitdb\\"]
        aliases = (
            r"d:/ecg/LOCKED/mitdb/100.dat",
            r"D:\ecg\locked\other\..\mitdb\100.dat",
            r"D:\ecg\locked\mitdb\.\100.dat",
        )
        for candidate in aliases:
            with self.subTest(candidate=candidate):
                with self.assertRaises(RegistryError):
                    validate_locked_roots({"train": [candidate]}, locked_roots)
        with self.assertRaises(RegistryError):
            validate_locked_roots({"train": [r"locked\mitdb\100.dat"]}, locked_roots)

    def test_patient_split_matches_independent_sha256_mod_100_rule(self):
        for patient_id in ("patient-0", "patient-17", "patient-999"):
            bucket = int(hashlib.sha256(patient_id.encode("utf-8")).hexdigest(), 16) % 100
            expected = "train" if bucket <= 79 else "validation" if bucket <= 89 else "internal_test"
            self.assertEqual(assign_icentia_split(patient_id), expected)

    def test_icentia_explicit_split_assignment_must_match_hash_rule(self):
        patient_id = "patient-17"
        expected = assign_icentia_split(patient_id)
        validate_icentia_splits({expected: [patient_id]})
        wrong_split = next(split for split in ("train", "validation", "internal_test") if split != expected)
        with self.assertRaises(RegistryError):
            validate_icentia_splits({wrong_split: [patient_id]})

    def test_patient_cross_split_is_rejected(self):
        with self.assertRaises(RegistryError):
            validate_patient_assignments(
                {"train": ["p01", "p02"], "validation": ["p02"], "internal_test": ["p03"]}
            )
        validate_patient_assignments(
            {"train": ["p01"], "validation": ["p02"], "internal_test": ["p03"]}
        )

    def test_every_discovered_file_has_sha256_and_missing_root_fails(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            payload = root / "record.dat"
            payload.write_bytes(b"M1 synthetic metadata only")
            inventory = build_file_inventory(root)
            self.assertEqual(len(inventory), 1)
            expected = hashlib.sha256(payload.read_bytes()).hexdigest()
            self.assertEqual(inventory[0]["sha256"], expected)
            self.assertEqual(inventory[0]["relative_path"], "record.dat")
            validate_file_inventory(inventory)
            with self.assertRaises(RegistryError):
                validate_file_inventory([{"relative_path": "record.dat", "size_bytes": 1}])
        with self.assertRaises(RegistryError):
            build_file_inventory(Path(temp_dir) / "does-not-exist")

    def test_registry_emits_hashed_manifest_split_lists_and_exclusion_reason(self):
        with tempfile.TemporaryDirectory() as data_dir, tempfile.TemporaryDirectory() as output_dir:
            data_root = Path(data_dir)
            (data_root / "segment.dat").write_bytes(b"metadata-only synthetic file")
            written = build_registry({"Icentia11k": data_root}, Path(output_dir), usage="inventory")
            names = {path.name for path in written}
            self.assertIn("icentia11k_1_0_inventory_dataset_manifest.json", names)
            self.assertIn("train_patients.txt", names)
            manifest_path = Path(output_dir) / "icentia11k_1_0_inventory_dataset_manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(len(manifest["hashes"]["raw_files_sha256"]), 1)
            self.assertEqual(manifest["exclusions"][0]["counted_in_report"], True)

    @staticmethod
    def _record(record_id, patient_id, split, relative_path, payload):
        digest = hashlib.sha256(payload).hexdigest()
        return {
            "record_id": record_id,
            "patient_id": patient_id,
            "split": split,
            "duration_s": 1.0,
            "raw_files": [{"relative_path": relative_path, "size_bytes": len(payload), "sha256": digest}],
            "record_sha256": digest,
        }

    def test_locked_explicit_record_cannot_enter_a_development_split(self):
        with tempfile.TemporaryDirectory() as data_dir, tempfile.TemporaryDirectory() as output_dir:
            payload = b"locked synthetic metadata"
            (Path(data_dir) / "100.dat").write_bytes(payload)
            record = self._record("100", "patient-locked", "train", "100.dat", payload)
            with self.assertRaises(RegistryError):
                build_registry(
                    {"MIT-BIH Arrhythmia": data_dir},
                    output_dir,
                    usage="inventory",
                    records_by_database={"MIT-BIH Arrhythmia": [record]},
                )

    def test_explicit_and_supplied_patients_are_checked_together_globally(self):
        with tempfile.TemporaryDirectory() as data_dir, tempfile.TemporaryDirectory() as output_dir:
            payload = b"development synthetic metadata"
            (Path(data_dir) / "record.dat").write_bytes(payload)
            records = [
                self._record("r1", "same-patient", "train", "record.dat", payload),
                self._record("r2", "same-patient", "validation", "record.dat", payload),
            ]
            with self.assertRaises(RegistryError):
                build_registry(
                    {"LUDB": data_dir},
                    output_dir,
                    usage="qrs_development",
                    records_by_database={"LUDB": records},
                )
            with self.assertRaises(RegistryError):
                build_registry(
                    {"LUDB": data_dir},
                    output_dir,
                    usage="qrs_development",
                    records_by_database={"LUDB": [records[0]]},
                    patient_splits_by_database={"LUDB": {"validation": ["same-patient"]}},
                )

    def test_explicit_raw_file_hash_must_match_inventory(self):
        with tempfile.TemporaryDirectory() as data_dir, tempfile.TemporaryDirectory() as output_dir:
            payload = b"real bytes"
            (Path(data_dir) / "record.dat").write_bytes(payload)
            record = self._record("r1", "patient-1", "validation", "record.dat", b"different bytes")
            with self.assertRaises(RegistryError):
                build_registry(
                    {"LUDB": data_dir},
                    output_dir,
                    usage="qrs_development",
                    records_by_database={"LUDB": [record]},
                )


if __name__ == "__main__":
    unittest.main(verbosity=2)
