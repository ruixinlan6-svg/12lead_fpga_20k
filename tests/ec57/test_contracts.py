"""M0 contract and data-governance regression tests.

These tests intentionally use only the Python standard library.  They validate
the frozen values and the fail-closed checks that later data/model tooling must
reuse; they do not download or open ECG databases.
"""

from __future__ import annotations

import copy
import csv
import json
import unittest
from pathlib import Path, PureWindowsPath

from train.ec57.resource_budget import (
    MODEL_DEPLOYMENT_PACKAGE_MAX_BYTES,
    MODEL_MACS_PER_BEAT_MAX,
    MODEL_MAX_ACTIVATION_BYTES,
    MODEL_PACKAGE_CONTAINER_OVERHEAD_RESERVE_BYTES,
    MODEL_PARAMETER_PAYLOAD_MAX_BYTES,
)


ROOT = Path(__file__).resolve().parents[2]
IO_PATH = ROOT / "contracts" / "ec57_hybrid_io_contract.json"
LOOKAHEAD_IO_PATH = ROOT / "contracts" / "ec57_hybrid_io_lookahead_v2.json"
METRICS_PATH = ROOT / "contracts" / "ec57_hybrid_metrics_contract.json"
LABEL_PATH = ROOT / "contracts" / "ec57_label_mapping_v1.json"
MANIFEST_SCHEMA_PATH = ROOT / "docs" / "datasets" / "ec57_dataset_manifest.schema.json"
RECEIPT_SCHEMA_PATH = ROOT / "docs" / "datasets" / "locked_run_receipt.schema.json"
REGISTRY_PATH = ROOT / "docs" / "datasets" / "data_role_registry.csv"
CONTAMINATION_PATH = ROOT / "docs" / "datasets" / "contamination_log.csv"

EXPECTED_LEADS = [
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
LOCKED_CONTEXTS = {"train", "calibration", "ptq", "qat", "tuning", "golden", "debug", "board_debug"}


class ContractError(ValueError):
    """Raised when a configuration violates an M0 contract."""


def _load_json(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def validate_io_contract(contract):
    if contract["sampling"]["rate_hz"] != 250:
        raise ContractError("sampling rate must be 250 Hz")
    leads = contract["leads"]
    if leads["count"] != 12 or leads["order"] != EXPECTED_LEADS:
        raise ContractError("lead count/order is not the frozen 12-lead contract")
    transport = contract["transport"]
    if transport["sample_dtype"] != "signed_int16" or transport["endianness"] != "little":
        raise ContractError("transport sample representation is not frozen")
    if transport["microvolts_per_lsb"] != 5:
        raise ContractError("physical scale must be 5 microvolts per LSB")
    window = contract["beat_window"]
    if window["length_samples"] != 160:
        raise ContractError("beat window must be 160 samples")
    if window["r_peak_index"] != 64:
        raise ContractError("R peak must be at sample index 64")
    if len(contract["beat_preprocessing"]["auxiliary_features"]) != 4:
        raise ContractError("exactly four auxiliary features are required")
    classifier = contract["outputs"]["beat_classifier"]
    if classifier["logit_order"] != ["non_VEB", "VEB"]:
        raise ContractError("classifier logit order is not frozen")
    required_states = {"SIGNAL_LOSS", "DEGRADED_ONE_LEAD", "UNCLASSIFIED_BEAT"}
    if not required_states.issubset(set(contract["outputs"]["status_outputs"])):
        raise ContractError("required validity states are missing")
    required_errors = {
        "INVALID_LEAD_ORDER",
        "INVALID_SAMPLING_RATE",
        "INVALID_WINDOW",
        "INVALID_R_INDEX",
        "CRC_ERROR",
        "MISSING_SAMPLE",
        "FIFO_OVERFLOW",
    }
    if not required_errors.issubset(set(contract["outputs"]["error_states"])):
        raise ContractError("required integrity error states are missing")


def validate_dataset_configuration(configuration, rows):
    by_name = {row["database"]: row for row in rows}
    for context, databases in configuration.items():
        if context not in LOCKED_CONTEXTS:
            continue
        for database in databases:
            if database not in by_name:
                raise ContractError(f"database is not registered: {database}")
            if by_name[database]["role"] == "locked":
                raise ContractError(f"locked database {database} cannot enter {context}")


def validate_dataset_root_configuration(configuration, locked_roots):
    """Reject a locked Windows root or any descendant without touching disk."""
    normalized_roots = [PureWindowsPath(root) for root in locked_roots]
    for context, configured_paths in configuration.items():
        if context not in LOCKED_CONTEXTS:
            continue
        for configured_path in configured_paths:
            candidate = PureWindowsPath(configured_path)
            for locked_root in normalized_roots:
                if candidate == locked_root or locked_root in candidate.parents:
                    raise ContractError(f"locked root {locked_root} cannot enter {context}")


def validate_patient_splits(splits):
    ownership = {}
    for split, patient_ids in splits.items():
        for patient_id in patient_ids:
            previous = ownership.setdefault(patient_id, split)
            if previous != split:
                raise ContractError(f"patient {patient_id} crosses {previous}/{split}")


def percentage(numerator, denominator, zero_denominator="N/A"):
    if numerator < 0 or denominator < 0 or numerator > denominator:
        raise ContractError("invalid metric numerator/denominator")
    if denominator == 0:
        if zero_denominator != "N/A":
            raise ContractError("zero denominator must be reported as N/A")
        return "N/A"
    return numerator / denominator * 100.0


def validate_required_fields(instance, schema, path="$", errors=None):
    """Small dependency-free required-field checker for schema regression tests."""
    errors = [] if errors is None else errors
    if schema.get("type") == "object" and isinstance(instance, dict):
        for field in schema.get("required", []):
            if field not in instance:
                errors.append(f"{path}.{field}")
        for field, child_schema in schema.get("properties", {}).items():
            if field in instance:
                validate_required_fields(instance[field], child_schema, f"{path}.{field}", errors)
    elif schema.get("type") == "array" and isinstance(instance, list):
        item_schema = schema.get("items")
        if item_schema:
            for index, item in enumerate(instance):
                validate_required_fields(item, item_schema, f"{path}[{index}]", errors)
    return errors


def minimal_manifest():
    return {
        "schema_version": "1.0.0",
        "manifest_id": "m0-empty-manifest",
        "created_at": "2026-08-27T22:06:33+08:00",
        "database": {
            "name": "Icentia11k",
            "version": "1.0",
            "license": "CC BY-NC-SA 4.0",
            "role": "development/internal",
        },
        "source": {
            "official_url": "https://physionet.org/content/icentia11k-continuous-ecg/1.0/",
            "doi": None,
            "root_uri": "not-downloaded:m0",
        },
        "role": "development/internal",
        "purpose": ["contract-only registration placeholder"],
        "sampling": {
            "native_rate_hz": 250,
            "target_rate_hz": 250,
            "resampling_required": False,
            "sample_count_policy": "record exact counts; no silent crop or pad",
        },
        "leads": {
            "native_count": 1,
            "native_order": ["single_fixed_lead"],
            "target_count": 12,
            "target_order": EXPECTED_LEADS,
            "unit": "uV",
            "microvolts_per_lsb": 5,
        },
        "patient_split": {
            "strategy": "patient_id only",
            "patient_key": "patient_id",
            "assignments": [],
            "split_hash": "0" * 64,
        },
        "records": [],
        "annotations": {
            "source_format": "Icentia beat labels",
            "mapping_contract": "contracts/ec57_label_mapping_v1.json",
            "source_labels": ["N", "S", "V", "Q"],
            "excluded_labels": ["Q"],
            "unmapped_policy": "fail closed and preserve raw label",
        },
        "hashes": {
            "raw_files_sha256": [],
            "annotation_sha256": "0" * 64,
        },
        "resampler": {
            "name": "not-run-in-m0",
            "version": "not-run-in-m0",
            "method": "rational_polyphase",
            "source_rate_hz": 250,
            "target_rate_hz": 250,
            "timestamp_tolerance_ms": 0,
        },
        "exclusions": [],
        "provenance": {
            "generated_by": "M0 contract tests",
            "generator_version": "1.0.0",
            "io_contract": "contracts/ec57_hybrid_io_contract.json",
            "label_mapping_contract": "contracts/ec57_label_mapping_v1.json",
            "created_without_download": True,
        },
    }


class TestEC57Contracts(unittest.TestCase):
    def test_lookahead_contract_versions_timing_without_replacing_v1(self):
        base = json.loads(IO_PATH.read_text(encoding="utf-8"))
        lookahead = json.loads(LOOKAHEAD_IO_PATH.read_text(encoding="utf-8"))
        self.assertEqual(base["contract_version"], "1.0.0")
        self.assertEqual(lookahead["base_contract"], "contracts/ec57_hybrid_io_contract.json@1.0.0")
        self.assertEqual(lookahead["decision_timing"]["emit_trigger"], "arrival of the next valid QRS R[i+1]")
        self.assertIn("no synthetic RR", lookahead["decision_timing"]["finite_record_boundary_policy"])
        self.assertEqual(lookahead["features"]["count"], 8)
        self.assertTrue(lookahead["compatibility"]["v1_default_unchanged"])
    @classmethod
    def setUpClass(cls):
        cls.io = _load_json(IO_PATH)
        cls.metrics = _load_json(METRICS_PATH)
        cls.labels = _load_json(LABEL_PATH)
        cls.manifest_schema = _load_json(MANIFEST_SCHEMA_PATH)
        cls.receipt_schema = _load_json(RECEIPT_SCHEMA_PATH)
        with REGISTRY_PATH.open("r", encoding="utf-8-sig", newline="") as handle:
            cls.registry = list(csv.DictReader(handle))

    def test_all_m0_json_documents_parse(self):
        for path in (IO_PATH, METRICS_PATH, LABEL_PATH, MANIFEST_SCHEMA_PATH, RECEIPT_SCHEMA_PATH):
            with self.subTest(path=path):
                self.assertTrue(path.is_file())
                self.assertIsInstance(_load_json(path), dict)

    def test_io_contract_freezes_input_and_outputs(self):
        validate_io_contract(self.io)
        self.assertEqual(self.io["sampling"]["rate_hz"], 250)
        self.assertEqual(self.io["beat_window"]["length_samples"], 160)
        self.assertEqual(self.io["beat_window"]["r_peak_index"], 64)

    def test_wrong_lead_order_is_rejected(self):
        invalid = copy.deepcopy(self.io)
        invalid["leads"]["order"][0], invalid["leads"]["order"][1] = "II", "I"
        with self.assertRaises(ContractError):
            validate_io_contract(invalid)

    def test_wrong_sampling_rate_is_rejected(self):
        invalid = copy.deepcopy(self.io)
        invalid["sampling"]["rate_hz"] = 500
        with self.assertRaises(ContractError):
            validate_io_contract(invalid)

    def test_wrong_window_or_r_index_is_rejected(self):
        for field, value in (("length_samples", 159), ("r_peak_index", 63)):
            invalid = copy.deepcopy(self.io)
            invalid["beat_window"][field] = value
            with self.subTest(field=field):
                with self.assertRaises(ContractError):
                    validate_io_contract(invalid)

    def test_metrics_contract_has_five_core_metrics_and_formulas(self):
        metrics = self.metrics["metrics"]
        expected = {
            "qrs_se": ("QRS Se", "QTP / (QTP + QFN) * 100"),
            "qrs_plus_p": ("QRS +P", "QTP / (QTP + QFP) * 100"),
            "veb_se": ("VEB Se", "VTP / (VTP + VFN) * 100"),
            "veb_plus_p": ("VEB +P", "VTP / (VTP + VFP) * 100"),
            "veb_fpr": ("VEB FPR", "VFP / (VTN + VFP) * 100"),
        }
        self.assertEqual(set(expected), set(metrics))
        for key, (name, formula) in expected.items():
            with self.subTest(metric=key):
                self.assertEqual(metrics[key]["display_name"], name)
                self.assertEqual(metrics[key]["formula"], formula)
                self.assertEqual(metrics[key]["zero_denominator"], "N/A")
        self.assertEqual(self.metrics["standard_context"]["match_window_ms"], 150)
        self.assertEqual(self.metrics["standard_context"]["learning_period_s"], 300)
        self.assertEqual(self.metrics["heart_rate"]["maximum_absolute_error_bpm"], 5)
        self.assertEqual(self.metrics["bit_exact"]["core_golden_beats"], 4096)
        self.assertEqual(self.metrics["timing"]["clock_mhz"], 27)
        self.assertEqual(self.metrics["hil"]["download_mode"], "SRAM_only")

    def test_model_resource_contract_matches_production_constants(self):
        budget = self.metrics["model_budget"]
        self.assertEqual(
            budget["complete_deployment_parameter_package_max_bytes"],
            MODEL_DEPLOYMENT_PACKAGE_MAX_BYTES,
        )
        self.assertEqual(
            budget["container_overhead_reserve_bytes"],
            MODEL_PACKAGE_CONTAINER_OVERHEAD_RESERVE_BYTES,
        )
        self.assertEqual(
            budget["parameter_payload_max_bytes"],
            MODEL_PARAMETER_PAYLOAD_MAX_BYTES,
        )
        self.assertEqual(budget["macs_per_beat_max"], MODEL_MACS_PER_BEAT_MAX)
        self.assertEqual(
            budget["max_single_layer_activation_bytes"],
            MODEL_MAX_ACTIVATION_BYTES,
        )

    def test_ludb_gate_scope_and_reference_responsibilities_are_explicit(self):
        policy = self.metrics["ludb_qrs_evaluation"]
        self.assertEqual(policy["gate_scope"], "annotation_support")
        self.assertEqual(policy["support_rule"]["tolerance_ms"], 150)
        self.assertTrue(policy["support_rule"]["inclusive"])
        self.assertEqual(policy["full_record_metrics"], "required_diagnostic")
        self.assertEqual(policy["medical_gate_reference"], "causal_pure_integer")
        self.assertEqual(policy["float_reference_role"], "independent_diagnostic")
        self.assertEqual(
            self.metrics["bit_exact"]["implementations"],
            ["integer_python_reference", "rtl_simulation", "QN88_SRAM_FPGA"],
        )

    def test_label_mapping_is_explicit_and_non_silent(self):
        training = self.labels["training_mapping"]
        self.assertEqual(training["positive"]["source_labels"], ["V"])
        self.assertEqual(training["positive"]["target_class"], "VEB")
        self.assertEqual(training["negative"]["source_labels"], ["N", "S"])
        self.assertTrue(self.labels["reporting_mapping"]["s_separate_report"])
        self.assertEqual(training["excluded"]["source_labels"], ["Q"])
        self.assertTrue(training["excluded"]["from_loss"])
        self.assertTrue(training["excluded"]["from_performance_denominators"])
        self.assertTrue(training["excluded"]["count_required"])
        self.assertTrue(self.labels["silent_conversion_forbidden"])

    def test_required_dataset_roles_are_frozen(self):
        by_name = {row["database"]: row for row in self.registry}
        self.assertEqual(by_name["Icentia11k"]["role"], "development/internal")
        self.assertEqual(by_name["LUDB"]["scope"], "QRS and delineation development")
        for database in ("INCART", "MIT-BIH Arrhythmia", "AHA Ventricular Arrhythmia", "MIT-BIH Noise Stress Test"):
            with self.subTest(database=database):
                self.assertEqual(by_name[database]["role"], "locked")
                self.assertIn("train", by_name[database]["prohibited_uses"])
                self.assertIn("calibration", by_name[database]["prohibited_uses"])
                self.assertIn("golden", by_name[database]["prohibited_uses"])

    def test_locked_database_in_train_or_calibration_is_rejected(self):
        for context in ("train", "calibration"):
            with self.subTest(context=context):
                with self.assertRaises(ContractError):
                    validate_dataset_configuration({context: ["MIT-BIH Arrhythmia"]}, self.registry)

    def test_development_database_can_be_used_for_train(self):
        validate_dataset_configuration({"train": ["Icentia11k"]}, self.registry)

    def test_development_database_can_supply_frozen_golden_and_debug(self):
        for context in ("golden", "debug", "board_debug"):
            with self.subTest(context=context):
                validate_dataset_configuration({context: ["Icentia11k"]}, self.registry)

    def test_locked_root_or_descendant_in_train_is_rejected(self):
        locked_roots = [r"D:\ecg_data\locked\mitdb"]
        for configured_path in (
            r"D:\ecg_data\locked\mitdb",
            r"D:\ecg_data\locked\mitdb\100.dat",
        ):
            with self.subTest(configured_path=configured_path):
                with self.assertRaises(ContractError):
                    validate_dataset_root_configuration({"train": [configured_path]}, locked_roots)
        validate_dataset_root_configuration(
            {"train": [r"D:\ecg_data\development\icentia11k"]},
            locked_roots,
        )

    def test_patient_cross_split_is_rejected(self):
        with self.assertRaises(ContractError):
            validate_patient_splits({"train": ["p001", "p002"], "validation": ["p002"]})
        validate_patient_splits({"train": ["p001"], "validation": ["p002"], "internal_test": ["p003"]})

    def test_illegal_metric_denominator_is_rejected_and_na_is_explicit(self):
        with self.assertRaises(ContractError):
            percentage(0, 0, zero_denominator=0)
        self.assertEqual(percentage(0, 0), "N/A")
        with self.assertRaises(ContractError):
            percentage(2, 1)

    def test_manifest_schema_missing_required_field_is_rejected(self):
        instance = minimal_manifest()
        self.assertEqual(validate_required_fields(instance, self.manifest_schema), [])
        invalid = copy.deepcopy(instance)
        del invalid["database"]
        errors = validate_required_fields(invalid, self.manifest_schema)
        self.assertIn("$.database", errors)

    def test_locked_receipt_schema_missing_required_field_is_rejected(self):
        minimal = {
            "schema_version": "1.0.0",
            "receipt_id": "receipt",
            "run_id": "run",
            "opened_at": "2026-08-27T22:06:33+08:00",
            "operator": "test",
        }
        errors = validate_required_fields(minimal, self.receipt_schema)
        self.assertIn("$.locked_databases", errors)

    def test_contamination_log_is_append_only_and_has_baseline_row(self):
        with CONTAMINATION_PATH.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            rows = list(reader)
            self.assertIn("event_id", reader.fieldnames)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["event_type"], "none_observed")
        self.assertEqual(rows[0]["status"], "clean")


if __name__ == "__main__":
    unittest.main(verbosity=2)
