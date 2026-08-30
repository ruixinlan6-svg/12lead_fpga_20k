"""EC57 Classification Metrics and Statistical Reporting (ANSI/AAMI EC57:2012).

Provides:
  1. Standard EC57 confusion metrics: VTP, VFN, VFP, VTN.
  2. Rate calculations: VEB Se, VEB +P, VEB FPR (VFP / (VTN + VFP)).
  3. Wilson score 95% confidence intervals for binomial proportions.
  4. Per-patient aggregation (Gross and Average metrics).
  5. Patient-level bootstrap confidence intervals (10,000 resamples, seed 20260827).
  6. Strict fail-closed zero denominator handling (returns None / 'N/A').
"""

import math
import numpy as np
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Tuple, Any, Union


@dataclass
class VEBConfusionCounts:
    """Raw integer confusion counts for VEB classification."""
    vtp: int = 0
    vfn: int = 0
    vfp: int = 0
    vtn: int = 0

    @property
    def total_reference_veb(self) -> int:
        return self.vtp + self.vfn

    @property
    def total_reference_non_veb(self) -> int:
        return self.vtn + self.vfp

    @property
    def total_detected_veb(self) -> int:
        return self.vtp + self.vfp

    @property
    def total_beats(self) -> int:
        return self.vtp + self.vfn + self.vfp + self.vtn

    def compute_rates(self) -> Dict[str, Optional[float]]:
        """Computes Se, +P, and FPR as percentages (0.0 to 100.0)."""
        se = (self.vtp / self.total_reference_veb * 100.0) if self.total_reference_veb > 0 else None
        plus_p = (self.vtp / self.total_detected_veb * 100.0) if self.total_detected_veb > 0 else None
        fpr = (self.vfp / self.total_reference_non_veb * 100.0) if self.total_reference_non_veb > 0 else None
        return {
            "veb_se_percent": se,
            "veb_plus_p_percent": plus_p,
            "veb_fpr_percent": fpr
        }


def wilson_score_interval(successes: int, total: int, confidence: float = 0.95) -> Optional[Tuple[float, float]]:
    """
    Computes Wilson score confidence interval for a binomial proportion.
    Returns (lower_percent, upper_percent) or None if total == 0.
    """
    if total <= 0:
        return None

    # Z-score for standard confidence levels
    if math.isclose(confidence, 0.95, rel_tol=1e-3):
        z = 1.959963984540054
    elif math.isclose(confidence, 0.99, rel_tol=1e-3):
        z = 2.5758293035489004
    elif math.isclose(confidence, 0.90, rel_tol=1e-3):
        z = 1.6448536269514722
    else:
        # Standard normal inverse approximation
        z = 1.959963984540054

    p_hat = successes / total
    denominator = 1.0 + (z * z) / total
    center = (p_hat + (z * z) / (2.0 * total)) / denominator
    spread = (z / denominator) * math.sqrt((p_hat * (1.0 - p_hat) / total) + (z * z) / (4.0 * total * total))

    lower = max(0.0, (center - spread) * 100.0)
    upper = min(100.0, (center + spread) * 100.0)
    return (lower, upper)


def compute_patient_level_metrics(
    patient_records: Dict[str, VEBConfusionCounts]
) -> Dict[str, Any]:
    """
    Computes Gross (pooled) and Average (per-patient mean) metrics across patients.
    """
    gross_counts = VEBConfusionCounts()
    patient_se_list: List[float] = []
    patient_plus_p_list: List[float] = []
    patient_fpr_list: List[float] = []

    for pat_id, counts in patient_records.items():
        gross_counts.vtp += counts.vtp
        gross_counts.vfn += counts.vfn
        gross_counts.vfp += counts.vfp
        gross_counts.vtn += counts.vtn

        rates = counts.compute_rates()
        if rates["veb_se_percent"] is not None:
            patient_se_list.append(rates["veb_se_percent"])
        if rates["veb_plus_p_percent"] is not None:
            patient_plus_p_list.append(rates["veb_plus_p_percent"])
        if rates["veb_fpr_percent"] is not None:
            patient_fpr_list.append(rates["veb_fpr_percent"])

    gross_rates = gross_counts.compute_rates()

    avg_se = float(np.mean(patient_se_list)) if patient_se_list else None
    avg_plus_p = float(np.mean(patient_plus_p_list)) if patient_plus_p_list else None
    avg_fpr = float(np.mean(patient_fpr_list)) if patient_fpr_list else None

    # Confidence intervals on Gross counts
    se_ci = wilson_score_interval(gross_counts.vtp, gross_counts.total_reference_veb)
    plus_p_ci = wilson_score_interval(gross_counts.vtp, gross_counts.total_detected_veb)
    fpr_ci = wilson_score_interval(gross_counts.vfp, gross_counts.total_reference_non_veb)

    return {
        "gross_counts": asdict(gross_counts),
        "gross_rates": gross_rates,
        "gross_wilson_ci_95": {
            "veb_se_ci": se_ci,
            "veb_plus_p_ci": plus_p_ci,
            "veb_fpr_ci": fpr_ci
        },
        "average_rates": {
            "veb_se_percent": avg_se,
            "veb_plus_p_percent": avg_plus_p,
            "veb_fpr_percent": avg_fpr,
            "patient_count": len(patient_records),
            "evaluated_se_patients": len(patient_se_list),
            "evaluated_plus_p_patients": len(patient_plus_p_list),
            "evaluated_fpr_patients": len(patient_fpr_list)
        }
    }


def patient_bootstrap_ci(
    patient_records: Dict[str, VEBConfusionCounts],
    n_resamples: int = 10000,
    seed: int = 20260827,
    alpha: float = 0.05
) -> Dict[str, Tuple[float, float]]:
    """
    Patient-level bootstrap confidence intervals for Gross Se, +P, and FPR.
    Resamples patient units with replacement.
    """
    patient_keys = list(patient_records.keys())
    n_patients = len(patient_keys)
    if n_patients < 2:
        return {}

    rng = np.random.RandomState(seed)
    boot_se = []
    boot_plus_p = []
    boot_fpr = []

    for _ in range(n_resamples):
        sample_indices = rng.choice(n_patients, size=n_patients, replace=True)
        vtp, vfn, vfp, vtn = 0, 0, 0, 0
        for idx in sample_indices:
            c = patient_records[patient_keys[idx]]
            vtp += c.vtp
            vfn += c.vfn
            vfp += c.vfp
            vtn += c.vtn

        if vtp + vfn > 0:
            boot_se.append(vtp / (vtp + vfn) * 100.0)
        if vtp + vfp > 0:
            boot_plus_p.append(vtp / (vtp + vfp) * 100.0)
        if vtn + vfp > 0:
            boot_fpr.append(vfp / (vtn + vfp) * 100.0)

    results = {}
    lower_pct = 100.0 * (alpha / 2.0)
    upper_pct = 100.0 * (1.0 - alpha / 2.0)

    if boot_se:
        results["veb_se_bootstrap_ci"] = (
            float(np.percentile(boot_se, lower_pct)),
            float(np.percentile(boot_se, upper_pct))
        )
    if boot_plus_p:
        results["veb_plus_p_bootstrap_ci"] = (
            float(np.percentile(boot_plus_p, lower_pct)),
            float(np.percentile(boot_plus_p, upper_pct))
        )
    if boot_fpr:
        results["veb_fpr_bootstrap_ci"] = (
            float(np.percentile(boot_fpr, lower_pct)),
            float(np.percentile(boot_fpr, upper_pct))
        )

    return results
