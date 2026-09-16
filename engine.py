"""
Quantum Risk Assessment & Prioritisation Engine
Implements the scoring model from the Quantum Risk Assessment &
Prioritisation Framework (v2.0) technical specification.

Risk = Impact x Likelihood
Impact in [0.0, 1.0], Likelihood multiplier configurable (default 1.0 / 1.3)

Every weight, score, multiplier, and priority-band threshold used by the
model lives in a single CONFIG dict (see DEFAULT_CONFIG below) rather than
being hardcoded, so the whole model can be tuned from the UI or from a
saved JSON file without touching this file.
"""

import copy
from dataclasses import dataclass, field
from typing import Dict, List, Optional

# ---------------------------------------------------------------------------
# Static structure (which fields exist / how they're labelled) — this does
# NOT change with configuration; only the *weights* attached to it do.
# ---------------------------------------------------------------------------

CIA_VECTORS = ["confidentiality", "integrity", "availability"]

RATING_ORDER = ["Minor", "Moderate", "Major", "Extreme"]

# (field_id, variable_name, intake question label)
IMPACTED_SYSTEMS_FIELDS = [
    ("IS-01", "provides_authentication",
     "Does this service provide authentication services to other downstream services?"),
    ("IS-02", "impacts_critical_services",
     "Does this service have the ability to impact the Confidentiality, Integrity, or "
     "Availability of other Major or Extreme BIA systems?"),
    ("IS-03", "has_privileged_access",
     "Does this service have, or allow staff, privileged access to other services or IT assets?"),
    ("IS-04", "can_modify_other_services",
     "Does this service have the ability to deploy, modify, or execute code on other services, "
     "make configuration changes, or modify remote data?"),
]

# (variable_name, label)
DATA_SENSITIVITY_FIELDS = [
    ("is_highly_restricted_present", "Highly Restricted data present?"),
    ("is_sensitive_personal_data_present", "Sensitive Personal Data present?"),
    ("is_personal_data_present", "Personal Data present?"),
]

BAND_PALETTE = ["#C0392B", "#E67E22", "#F1C40F", "#27AE60", "#2E86C1", "#8E44AD", "#7F8C8D"]

# ---------------------------------------------------------------------------
# Default configuration — mirrors the framework document exactly.
# All weight groups are fractions that should sum to 1.0 within their group.
# ---------------------------------------------------------------------------

DEFAULT_CONFIG = {
    # Section 2: top-level AHP category weights (must sum to 1.0)
    "category_weights": {
        "Loss of Trust": 0.23,
        "Impacted Systems": 0.21,
        "Data Sensitivity": 0.21,
        "Financial Loss": 0.19,
        "Regulatory Censure": 0.16,
    },
    # Section 3: CIA split applied within every CIA-scored category (must sum to 1.0)
    "cia_split": {
        "confidentiality": 0.42,
        "integrity": 0.42,
        "availability": 0.16,
    },
    # Section 3: Loss of Trust splits into these two sub-components (must sum to 1.0)
    "loss_of_trust_split": {
        "customer_detriment": 0.50,
        "reputational_loss": 0.50,
    },
    # Section 5: Impacted Systems local weights (must sum to 1.0)
    "impacted_systems_weights": {
        "provides_authentication": 0.33,
        "impacts_critical_services": 0.27,
        "has_privileged_access": 0.20,
        "can_modify_other_services": 0.20,
    },
    # Section 3: Data Sensitivity local weights (must sum to 1.0)
    "data_sensitivity_weights": {
        "is_highly_restricted_present": 0.55,
        "is_sensitive_personal_data_present": 0.27,
        "is_personal_data_present": 0.18,
    },
    # Section 4.1: ordinal qualitative scale
    "rating_scores": {
        "Minor": 0.00,
        "Moderate": 0.33,
        "Major": 0.67,
        "Extreme": 1.00,
    },
    # Section 4.3: likelihood / threat exposure multipliers
    "threat_multipliers": {
        "public_facing": 1.30,
        "internal": 1.00,
    },
    # Section 7: priority tier thresholds, evaluated highest-threshold-first
    "priority_bands": [
        {"threshold": 0.85, "label": "Wave 1 - Immediate Migration (Critical)"},
        {"threshold": 0.55, "label": "Wave 2 - Medium Term Migration (High)"},
        {"threshold": 0.30, "label": "Wave 3 - Standard Migration (Medium)"},
        {"threshold": 0.00, "label": "Wave 4 - Low Priority / Decommission (Low)"},
    ],
}


def default_config() -> dict:
    return copy.deepcopy(DEFAULT_CONFIG)


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

WEIGHT_GROUPS = [
    ("category_weights", "Category (AHP) Weights"),
    ("cia_split", "CIA Split"),
    ("loss_of_trust_split", "Loss of Trust Sub-Split"),
    ("impacted_systems_weights", "Impacted Systems Local Weights"),
    ("data_sensitivity_weights", "Data Sensitivity Local Weights"),
]


def group_sum(config: dict, group_key: str) -> float:
    return sum(config[group_key].values())


def normalize_group(config: dict, group_key: str) -> dict:
    """Return a copy of config with the given weight group rescaled to sum to 1.0."""
    config = copy.deepcopy(config)
    d = config[group_key]
    total = sum(d.values())
    if total > 0:
        config[group_key] = {k: v / total for k, v in d.items()}
    return config


def validate_config(config: dict) -> List[str]:
    """Return a list of human-readable warnings for anything that doesn't sum to 100%
    or is otherwise inconsistent. An empty list means the config is fully valid."""
    warnings = []
    for key, label in WEIGHT_GROUPS:
        total = group_sum(config, key)
        if abs(total - 1.0) > 0.005:
            warnings.append(f"{label} sum to {total * 100:.1f}%, not 100%.")
    thresholds = [b["threshold"] for b in config["priority_bands"]]
    if thresholds != sorted(thresholds, reverse=True):
        warnings.append("Priority band thresholds should be in descending order.")
    return warnings


def derive_leaf_weights(config: dict) -> Dict[str, Dict[str, float]]:
    """Multiply out the AHP hierarchy into flat leaf-level global weights,
    grouped by top-level category — the direct analogue of Section 3's table."""
    cat = config["category_weights"]
    cia = config["cia_split"]
    lot_split = config["loss_of_trust_split"]

    leaf: Dict[str, Dict[str, float]] = {name: {} for name in cat}

    for comp, comp_w in lot_split.items():
        for v, vw in cia.items():
            leaf["Loss of Trust"][f"{comp}_{v}"] = cat["Loss of Trust"] * comp_w * vw

    for k, w in config["impacted_systems_weights"].items():
        leaf["Impacted Systems"][k] = cat["Impacted Systems"] * w

    for k, w in config["data_sensitivity_weights"].items():
        leaf["Data Sensitivity"][k] = cat["Data Sensitivity"] * w

    for v, vw in cia.items():
        leaf["Financial Loss"][f"financial_loss_{v}"] = cat["Financial Loss"] * vw
        leaf["Regulatory Censure"][f"regulatory_censure_{v}"] = cat["Regulatory Censure"] * vw

    return leaf


def priority_band(score: float, bands: List[dict]) -> str:
    sorted_bands = sorted(bands, key=lambda b: b["threshold"], reverse=True)
    for b in sorted_bands:
        if score >= b["threshold"]:
            return b["label"]
    return sorted_bands[-1]["label"] if sorted_bands else "Unclassified"


def band_color(label: str, bands: List[dict]) -> str:
    sorted_bands = sorted(bands, key=lambda b: b["threshold"], reverse=True)
    for i, b in enumerate(sorted_bands):
        if b["label"] == label:
            return BAND_PALETTE[i % len(BAND_PALETTE)]
    return "#7F8C8D"


def band_color_map(bands: List[dict]) -> Dict[str, str]:
    sorted_bands = sorted(bands, key=lambda b: b["threshold"], reverse=True)
    return {b["label"]: BAND_PALETTE[i % len(BAND_PALETTE)] for i, b in enumerate(sorted_bands)}


# ---------------------------------------------------------------------------
# Application profile
# ---------------------------------------------------------------------------

@dataclass
class ApplicationRiskProfile:
    service_id: str
    service_name: str
    application_tier: str = "Tier 1"
    is_public_facing: bool = False

    # CIA ordinal ratings ('Minor'|'Moderate'|'Major'|'Extreme')
    customer_detriment: Dict[str, str] = field(default_factory=lambda: {v: "Minor" for v in CIA_VECTORS})
    reputational_loss: Dict[str, str] = field(default_factory=lambda: {v: "Minor" for v in CIA_VECTORS})
    financial_loss: Dict[str, str] = field(default_factory=lambda: {v: "Minor" for v in CIA_VECTORS})
    regulatory_censure: Dict[str, str] = field(default_factory=lambda: {v: "Minor" for v in CIA_VECTORS})

    # Impacted Systems booleans
    provides_authentication: bool = False
    impacts_critical_services: bool = False
    has_privileged_access: bool = False
    can_modify_other_services: bool = False

    # Data Sensitivity booleans
    is_highly_restricted_present: bool = False
    is_sensitive_personal_data_present: bool = False
    is_personal_data_present: bool = False


def calculate_risk(app: ApplicationRiskProfile, config: Optional[dict] = None) -> dict:
    """Deterministic scoring per Section 7 of the specification, driven entirely
    by the supplied config (falls back to the framework's own defaults)."""
    config = config or DEFAULT_CONFIG
    leaf = derive_leaf_weights(config)
    rs = config["rating_scores"]

    cd_score = sum(
        rs[app.customer_detriment[v]] * leaf["Loss of Trust"][f"customer_detriment_{v}"] for v in CIA_VECTORS
    )
    rep_score = sum(
        rs[app.reputational_loss[v]] * leaf["Loss of Trust"][f"reputational_loss_{v}"] for v in CIA_VECTORS
    )
    loss_of_trust = cd_score + rep_score

    w = leaf["Impacted Systems"]
    impacted_systems = (
        float(app.provides_authentication) * w["provides_authentication"]
        + float(app.impacts_critical_services) * w["impacts_critical_services"]
        + float(app.has_privileged_access) * w["has_privileged_access"]
        + float(app.can_modify_other_services) * w["can_modify_other_services"]
    )

    w = leaf["Data Sensitivity"]
    data_sensitivity = (
        float(app.is_highly_restricted_present) * w["is_highly_restricted_present"]
        + float(app.is_sensitive_personal_data_present) * w["is_sensitive_personal_data_present"]
        + float(app.is_personal_data_present) * w["is_personal_data_present"]
    )

    financial_loss = sum(
        rs[app.financial_loss[v]] * leaf["Financial Loss"][f"financial_loss_{v}"] for v in CIA_VECTORS
    )
    reg_censure = sum(
        rs[app.regulatory_censure[v]] * leaf["Regulatory Censure"][f"regulatory_censure_{v}"] for v in CIA_VECTORS
    )

    total_impact = loss_of_trust + impacted_systems + data_sensitivity + financial_loss + reg_censure
    tm = config["threat_multipliers"]
    threat_multiplier = tm["public_facing"] if app.is_public_facing else tm["internal"]
    quantum_risk_score = round(total_impact * threat_multiplier, 4)
    band = priority_band(quantum_risk_score, config["priority_bands"])

    return {
        "service_id": app.service_id,
        "service_name": app.service_name,
        "application_tier": app.application_tier,
        "is_public_facing": app.is_public_facing,
        "loss_of_trust": round(loss_of_trust, 4),
        "impacted_systems": round(impacted_systems, 4),
        "data_sensitivity": round(data_sensitivity, 4),
        "financial_loss": round(financial_loss, 4),
        "regulatory_censure": round(reg_censure, 4),
        "raw_impact_score": round(total_impact, 4),
        "threat_multiplier": threat_multiplier,
        "quantum_risk_score": quantum_risk_score,
        "priority_band": band,
    }


# ---------------------------------------------------------------------------
# Self-test against Section 8 reference test case (Payments Orchestration Service)
# using the framework's own default weights.
# ---------------------------------------------------------------------------
def _reference_test_case() -> ApplicationRiskProfile:
    return ApplicationRiskProfile(
        service_id="SVC-TEST-001",
        service_name="Payments Orchestration Service",
        application_tier="Tier 0",
        is_public_facing=False,
        customer_detriment={"confidentiality": "Major", "integrity": "Extreme", "availability": "Moderate"},
        reputational_loss={"confidentiality": "Major", "integrity": "Extreme", "availability": "Moderate"},
        provides_authentication=True,
        impacts_critical_services=True,
        has_privileged_access=True,
        can_modify_other_services=False,
        is_highly_restricted_present=False,
        is_sensitive_personal_data_present=False,
        is_personal_data_present=True,
        financial_loss={"confidentiality": "Moderate", "integrity": "Extreme", "availability": "Major"},
        regulatory_censure={"confidentiality": "Major", "integrity": "Extreme", "availability": "Moderate"},
    )


if __name__ == "__main__":
    result = calculate_risk(_reference_test_case(), default_config())
    assert abs(result["raw_impact_score"] - 0.6265) < 0.001, result
    assert abs(result["quantum_risk_score"] - 0.6265) < 0.001, result
    assert result["priority_band"] == "Wave 2 - Medium Term Migration (High)", result
    assert not validate_config(default_config()), validate_config(default_config())
    print("Reference test case PASSED:", result)
