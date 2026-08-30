# EC57 Hybrid M0 Contract Boundary

This directory is reserved for the QN88 EC57-style research path. M0 freezes contracts and data governance only. It does not download databases, connect to a GPU, train a model, run PTQ/QAT, generate a golden set, modify FPGA RTL, synthesize, program a board, or write Flash/SDRAM.

## Frozen input and output contract

Use [`contracts/ec57_hybrid_io_contract.json`](../../contracts/ec57_hybrid_io_contract.json) as the machine-readable source of truth.

- Target sampling rate is **250 Hz**. Source databases are resampled on the host with a versioned rational polyphase method; event times are represented in seconds before mapping to target samples.
- The exact lead order is `I, II, III, aVR, aVL, aVF, V1, V2, V3, V4, V5, V6`. A different order is an error; do not silently permute it.
- The transport sample is signed little-endian `int16`, with `1 LSB = 5 µV`. Each sample index carries all 12 values and frame integrity/sequence checks.
- The beat waveform window is 160 samples, with the R peak at index 64 and coverage `[-256 ms, +384 ms)`. The four auxiliary features are previous RR relative to the recent-8 RR median, QRS width, peak relative to the recent-8 peak median, and main-lead SQI.
- The classifier logits and valid class output order are `[non_VEB, VEB]`. An unknown or unclassifiable beat is not silently changed to `non_VEB`; it is represented by `UNCLASSIFIED_BEAT`.
- Validity states include `FULL_12_LEAD`, `DEGRADED_ONE_LEAD`, and `SIGNAL_LOSS`. Integrity failures include lead order, sampling rate, window/R index, missing/duplicate/out-of-order samples, CRC, FIFO/window overflow, timeout, reset, and invalid configuration errors.

The research event definitions are fixed in the IO contract: bradycardia `<50 bpm` for 10 s with clear at `>=55 bpm` for 5 s; tachycardia `>100 bpm` for 10 s with clear at `<=95 bpm` for 5 s; asystole candidate after 3.0 s without a valid QRS while a lead is valid; PVC couplet at exactly two VEBs; ventricular run at three or more VEBs; VT candidate when the run median V-to-V rate is at least 100 bpm; and the specified bigeminy/trigeminy patterns. These are research events, not diagnoses or clinical alarms.

## Label mapping and role boundary

Use [`contracts/ec57_label_mapping_v1.json`](../../contracts/ec57_label_mapping_v1.json) without implicit aliases:

- Icentia `V` is the positive `VEB` class.
- Icentia `N` and `S` are explicitly named `non_VEB` source labels. `S` support and errors are always reported separately.
- Icentia `Q` is excluded from loss and performance denominators, but its count and exclusion reason are mandatory.
- Unknown/unclassifiable labels are never silently converted. Any mapping change requires a new contract version and `run_id`.

The role registry is [`docs/datasets/data_role_registry.csv`](../../docs/datasets/data_role_registry.csv). Icentia11k is `development/internal` and research-license restricted; its frozen manifests may be used for later integer Golden generation and RTL/HIL development while preserving patient split and manifest hashes. LUDB is QRS/delineation development; INCART is the complete locked twelve-lead external evaluation; MIT-BIH Arrhythmia, AHA, and NST are locked. Locked databases must not enter training, PTQ/QAT calibration, threshold tuning, golden generation, RTL/board debugging, or demonstrations. The contamination log is append-only and records any role downgrade; it must never be cleaned by deleting history.

The Icentia patient split is patient-level: `SHA-256(patient_id) mod 100` gives `0–79=train`, `80–89=validation`, and `90–99=internal_test`. A patient cannot occur in more than one split. The PTQ calibration set, when an authorized later milestone creates it, is exactly 8,192 Icentia train beats: 4,096 V and 4,096 non_VEB, selected by a frozen patient-rotating manifest. It cannot use validation, internal test, or any locked database.

## Metrics and later gates

Use [`contracts/ec57_hybrid_metrics_contract.json`](../../contracts/ec57_hybrid_metrics_contract.json). Report raw counts and per-record/database-gross/database-average/per-patient views. The five core metrics are QRS Se, QRS +P, VEB Se, VEB +P, and VEB FPR. The VEB FPR formula is `VFP/(VTN+VFP)*100`; it is not `VFP/hour`. Any zero denominator is `N/A`, never numeric zero.

The same contract freezes HR error reports, PTQ/QAT degradation, 4,096-beat bit-exact core golden, resource budgets, 27 MHz timing, and SRAM-only HIL gates. All numeric values are internal research candidate gates, not universal FDA or EC57 minimum scores. Formal AHA acquisition, authorized EC57 mapping, intended-use/predicate review, and clinical/regulatory sign-off remain open.

## M0 verification

From the repository root, run:

```text
python -m unittest discover -s tests/ec57 -p "test_contracts.py" -v
```

The tests are standard-library-only and must reject wrong lead order, non-250 Hz rate, wrong window/R index, a locked database name or locked root path in train/calibration, patient leakage, illegal metric denominators, and missing required schema fields. They do not access ECG databases or execute any hardware/model workflow.

M0 is not formally closed until the central reviewer registers its iteration record in `docs/iterations/INDEX.md`. That index is intentionally outside the M0 worker's exclusive file list.
