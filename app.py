import io
import json
from dataclasses import asdict

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from engine import (
    ApplicationRiskProfile,
    CIA_VECTORS,
    RATING_ORDER,
    IMPACTED_SYSTEMS_FIELDS,
    DATA_SENSITIVITY_FIELDS,
    WEIGHT_GROUPS,
    default_config,
    group_sum,
    normalize_group,
    validate_config,
    band_color_map,
    calculate_risk,
)

st.set_page_config(
    page_title="Quantum Risk Prioritisation Engine",
    page_icon="\U0001F510",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------
if "portfolio" not in st.session_state:
    st.session_state.portfolio = []  # list of {"profile": dict, "result": dict}
if "config" not in st.session_state:
    st.session_state.config = default_config()
if "cfg_nonce" not in st.session_state:
    st.session_state.cfg_nonce = 0

CSV_COLUMNS = [
    "service_id", "service_name", "application_tier", "is_public_facing",
    "customer_detriment_confidentiality", "customer_detriment_integrity", "customer_detriment_availability",
    "reputational_loss_confidentiality", "reputational_loss_integrity", "reputational_loss_availability",
    "provides_authentication", "impacts_critical_services", "has_privileged_access", "can_modify_other_services",
    "is_highly_restricted_present", "is_sensitive_personal_data_present", "is_personal_data_present",
    "financial_loss_confidentiality", "financial_loss_integrity", "financial_loss_availability",
    "regulatory_censure_confidentiality", "regulatory_censure_integrity", "regulatory_censure_availability",
]


def row_to_profile(row: dict) -> ApplicationRiskProfile:
    def b(v):
        if isinstance(v, str):
            return v.strip().lower() in ("true", "yes", "1", "y")
        return bool(v)

    return ApplicationRiskProfile(
        service_id=str(row["service_id"]),
        service_name=str(row["service_name"]),
        application_tier=str(row.get("application_tier", "Tier 1")),
        is_public_facing=b(row.get("is_public_facing", False)),
        customer_detriment={v: row[f"customer_detriment_{v}"] for v in CIA_VECTORS},
        reputational_loss={v: row[f"reputational_loss_{v}"] for v in CIA_VECTORS},
        financial_loss={v: row[f"financial_loss_{v}"] for v in CIA_VECTORS},
        regulatory_censure={v: row[f"regulatory_censure_{v}"] for v in CIA_VECTORS},
        provides_authentication=b(row.get("provides_authentication", False)),
        impacts_critical_services=b(row.get("impacts_critical_services", False)),
        has_privileged_access=b(row.get("has_privileged_access", False)),
        can_modify_other_services=b(row.get("can_modify_other_services", False)),
        is_highly_restricted_present=b(row.get("is_highly_restricted_present", False)),
        is_sensitive_personal_data_present=b(row.get("is_sensitive_personal_data_present", False)),
        is_personal_data_present=b(row.get("is_personal_data_present", False)),
    )


def add_entry(profile: ApplicationRiskProfile, result: dict):
    st.session_state.portfolio = [
        e for e in st.session_state.portfolio if e["profile"]["service_id"] != profile.service_id
    ]
    st.session_state.portfolio.append({"profile": asdict(profile), "result": result})


def recalculate_portfolio():
    config = st.session_state.config
    for entry in st.session_state.portfolio:
        profile = ApplicationRiskProfile(**entry["profile"])
        entry["result"] = calculate_risk(profile, config)


def sample_template_df() -> pd.DataFrame:
    return pd.DataFrame([{
        "service_id": "SVC-001",
        "service_name": "Payments Orchestration Service",
        "application_tier": "Tier 0",
        "is_public_facing": False,
        "customer_detriment_confidentiality": "Major",
        "customer_detriment_integrity": "Extreme",
        "customer_detriment_availability": "Moderate",
        "reputational_loss_confidentiality": "Major",
        "reputational_loss_integrity": "Extreme",
        "reputational_loss_availability": "Moderate",
        "provides_authentication": True,
        "impacts_critical_services": True,
        "has_privileged_access": True,
        "can_modify_other_services": False,
        "is_highly_restricted_present": False,
        "is_sensitive_personal_data_present": False,
        "is_personal_data_present": True,
        "financial_loss_confidentiality": "Moderate",
        "financial_loss_integrity": "Extreme",
        "financial_loss_availability": "Major",
        "regulatory_censure_confidentiality": "Major",
        "regulatory_censure_integrity": "Extreme",
        "regulatory_censure_availability": "Moderate",
    }])[CSV_COLUMNS]


GROUP_ITEM_LABELS = {
    "category_weights": {
        "Loss of Trust": "Loss of Trust", "Impacted Systems": "Impacted Systems",
        "Data Sensitivity": "Data Sensitivity", "Financial Loss": "Financial Loss",
        "Regulatory Censure": "Regulatory Censure",
    },
    "cia_split": {"confidentiality": "Confidentiality", "integrity": "Integrity", "availability": "Availability"},
    "loss_of_trust_split": {"customer_detriment": "Customer Detriment", "reputational_loss": "Reputational Loss"},
    "impacted_systems_weights": {
        "provides_authentication": "Provides Authentication (IS-01)",
        "impacts_critical_services": "Impacts Critical Services (IS-02)",
        "has_privileged_access": "Has Privileged Access (IS-03)",
        "can_modify_other_services": "Can Modify Other Services (IS-04)",
    },
    "data_sensitivity_weights": {
        "is_highly_restricted_present": "Highly Restricted Data",
        "is_sensitive_personal_data_present": "Sensitive Personal Data",
        "is_personal_data_present": "Personal Data",
    },
}


def render_weight_group(group_key: str, group_label: str):
    config = st.session_state.config
    nonce = st.session_state.cfg_nonce
    items = config[group_key]
    st.markdown(f"**{group_label}**")
    cols = st.columns(len(items))
    new_values = {}
    for col, (item_key, item_val) in zip(cols, items.items()):
        label = GROUP_ITEM_LABELS.get(group_key, {}).get(item_key, item_key)
        widget_key = f"w_{group_key}_{item_key}_{nonce}"
        new_values[item_key] = col.number_input(
            label, min_value=0.0, max_value=100.0, value=round(item_val * 100, 2),
            step=0.5, key=widget_key, format="%.2f",
        ) / 100.0
    config[group_key] = new_values
    total = sum(new_values.values())
    ok = abs(total - 1.0) <= 0.005
    c1, c2 = st.columns([3, 1])
    c1.caption(("\u2705 " if ok else "\u26A0\uFE0F ") + f"Sums to {total*100:.1f}%" + ("" if ok else " — should be 100%"))
    if c2.button("Normalize", key=f"norm_{group_key}", disabled=ok, use_container_width=True):
        st.session_state.config = normalize_group(config, group_key)
        st.session_state.cfg_nonce += 1
        st.rerun()
    st.divider()


# ---------------------------------------------------------------------------
# Sidebar navigation
# ---------------------------------------------------------------------------
st.sidebar.title("\U0001F510 Quantum Risk\nPrioritisation Engine")
st.sidebar.caption("Based on the Quantum Risk Assessment & Prioritisation Framework v2.0")
page = st.sidebar.radio(
    "Navigate",
    ["Assess an Application", "Bulk Upload", "Portfolio Dashboard", "Configure Model", "About the Model"],
)

# Placeholder — filled in at the bottom of the script, after the page body has
# had a chance to update st.session_state.config, so the indicator never lags
# a run behind edits made on the Configure Model page.
sidebar_validity_slot = st.sidebar.empty()

if st.session_state.portfolio:
    st.sidebar.divider()
    st.sidebar.metric("Applications assessed", len(st.session_state.portfolio))
    if st.sidebar.button("Clear portfolio", type="secondary"):
        st.session_state.portfolio = []
        st.rerun()

CIA_LABELS = {"confidentiality": "Confidentiality", "integrity": "Integrity", "availability": "Availability"}

# ---------------------------------------------------------------------------
# Page: Assess an Application
# ---------------------------------------------------------------------------
if page == "Assess an Application":
    st.title("Assess an Application")
    st.caption("Score a single application against the Quantum Risk Prioritisation Engine.")

    with st.form("assess_form"):
        c1, c2, c3 = st.columns(3)
        service_id = c1.text_input("Service ID*", placeholder="SVC-042")
        service_name = c2.text_input("Service Name*", placeholder="Loan Origination API")
        application_tier = c3.selectbox("Application Tier", ["Tier 0", "Tier 1", "Tier 2", "Tier 3"], index=1)
        is_public_facing = st.toggle(
            "Public Facing (internet-exposed)?",
            help="Threat exposure proxy — multiplier set on the Configure Model page.",
        )

        st.subheader("Loss of Trust — Customer Detriment")
        cd = {}
        cols = st.columns(3)
        for i, v in enumerate(CIA_VECTORS):
            cd[v] = cols[i].select_slider(f"Customer Detriment — {CIA_LABELS[v]}", RATING_ORDER, value="Minor", key=f"cd_{v}")

        st.subheader("Loss of Trust — Reputational Loss")
        rep = {}
        cols = st.columns(3)
        for i, v in enumerate(CIA_VECTORS):
            rep[v] = cols[i].select_slider(f"Reputational Loss — {CIA_LABELS[v]}", RATING_ORDER, value="Minor", key=f"rep_{v}")

        st.subheader("Impacted Systems (formerly Blast Radius)")
        is_answers = {}
        for field_id, var_name, label in IMPACTED_SYSTEMS_FIELDS:
            weight = st.session_state.config["impacted_systems_weights"][var_name]
            is_answers[var_name] = st.checkbox(f"[{field_id}] {label}  (local weight {weight:.0%})", key=f"is_{var_name}")

        st.subheader("Data Sensitivity")
        ds_answers = {}
        for var_name, label in DATA_SENSITIVITY_FIELDS:
            weight = st.session_state.config["data_sensitivity_weights"][var_name]
            ds_answers[var_name] = st.checkbox(f"{label}  (local weight {weight:.0%})", key=f"ds_{var_name}")

        st.subheader("Financial Loss")
        fin = {}
        cols = st.columns(3)
        for i, v in enumerate(CIA_VECTORS):
            fin[v] = cols[i].select_slider(f"Financial Loss — {CIA_LABELS[v]}", RATING_ORDER, value="Minor", key=f"fin_{v}")

        st.subheader("Regulatory Censure")
        reg = {}
        cols = st.columns(3)
        for i, v in enumerate(CIA_VECTORS):
            reg[v] = cols[i].select_slider(f"Regulatory Censure — {CIA_LABELS[v]}", RATING_ORDER, value="Minor", key=f"reg_{v}")

        submitted = st.form_submit_button("Calculate Quantum Risk Score", type="primary", use_container_width=True)

    if submitted:
        if not service_id or not service_name:
            st.error("Service ID and Service Name are required.")
        else:
            profile = ApplicationRiskProfile(
                service_id=service_id,
                service_name=service_name,
                application_tier=application_tier,
                is_public_facing=is_public_facing,
                customer_detriment=cd,
                reputational_loss=rep,
                financial_loss=fin,
                regulatory_censure=reg,
                **is_answers,
                **ds_answers,
            )
            result = calculate_risk(profile, st.session_state.config)
            add_entry(profile, result)

            band = result["priority_band"]
            colors = band_color_map(st.session_state.config["priority_bands"])
            color = colors.get(band, "#7F8C8D")
            st.markdown(
                f"""<div style="padding:1.2rem;border-radius:0.6rem;background-color:{color}22;
                border-left:6px solid {color};margin-top:1rem;">
                <span style="font-size:1.6rem;font-weight:700;">{result['quantum_risk_score']}</span>
                <span style="font-size:1.1rem;"> &nbsp;/&nbsp; max {max(st.session_state.config['threat_multipliers'].values()):.2f}</span><br/>
                <span style="font-size:1.15rem;font-weight:600;color:{color};">{band}</span>
                </div>""",
                unsafe_allow_html=True,
            )

            b1, b2, b3 = st.columns(3)
            b1.metric("Raw Impact Score", result["raw_impact_score"])
            b2.metric("Threat Multiplier", f"{result['threat_multiplier']}x")
            b3.metric("Quantum Risk Score", result["quantum_risk_score"])

            breakdown = {
                "Loss of Trust": result["loss_of_trust"],
                "Impacted Systems": result["impacted_systems"],
                "Data Sensitivity": result["data_sensitivity"],
                "Financial Loss": result["financial_loss"],
                "Regulatory Censure": result["regulatory_censure"],
            }
            fig = px.bar(
                x=list(breakdown.values()), y=list(breakdown.keys()), orientation="h",
                labels={"x": "Weighted contribution to Impact Score", "y": ""},
                title="Impact Score Breakdown by Category",
                text=[f"{v:.4f}" for v in breakdown.values()],
            )
            fig.update_traces(marker_color=color, textposition="outside")
            fig.update_layout(height=350, margin=dict(l=10, r=10, t=40, b=10))
            st.plotly_chart(fig, use_container_width=True)
            st.success(f"'{service_name}' added to the portfolio. See the Portfolio Dashboard tab for the full ranked list.")

# ---------------------------------------------------------------------------
# Page: Bulk Upload
# ---------------------------------------------------------------------------
elif page == "Bulk Upload":
    st.title("Bulk Upload")
    st.caption("Score many applications at once from a CSV export of your BIA / ITSO intake data.")

    template_df = sample_template_df()
    csv_buf = io.StringIO()
    template_df.to_csv(csv_buf, index=False)
    st.download_button(
        "Download CSV template", data=csv_buf.getvalue(),
        file_name="quantum_risk_intake_template.csv", mime="text/csv",
    )
    with st.expander("Column reference"):
        st.write(
            "- `is_public_facing` and all boolean columns accept True/False, Yes/No, or 1/0.\n"
            "- All ordinal columns (`*_confidentiality`, `*_integrity`, `*_availability`) accept: "
            "Minor, Moderate, Major, Extreme.\n"
            "- Scoring uses the weights currently set on the **Configure Model** page."
        )
        st.dataframe(template_df, use_container_width=True)

    uploaded = st.file_uploader("Upload completed intake CSV", type=["csv"])
    if uploaded is not None:
        try:
            df = pd.read_csv(uploaded)
            missing = [c for c in CSV_COLUMNS if c not in df.columns]
            if missing:
                st.error(f"Missing required columns: {', '.join(missing)}")
            else:
                results, errors = [], []
                for _, row in df.iterrows():
                    try:
                        profile = row_to_profile(row.to_dict())
                        result = calculate_risk(profile, st.session_state.config)
                        add_entry(profile, result)
                        results.append(result)
                    except Exception as e:
                        errors.append(f"{row.get('service_id', '?')}: {e}")

                if errors:
                    st.warning("Some rows could not be scored:\n\n" + "\n".join(errors))

                if results:
                    st.success(f"Scored {len(results)} application(s) and added them to the portfolio.")
                    res_df = pd.DataFrame(results).sort_values("quantum_risk_score", ascending=False)
                    st.dataframe(res_df, use_container_width=True, hide_index=True)
        except Exception as e:
            st.error(f"Could not read CSV: {e}")

# ---------------------------------------------------------------------------
# Page: Portfolio Dashboard
# ---------------------------------------------------------------------------
elif page == "Portfolio Dashboard":
    st.title("Portfolio Dashboard")

    if not st.session_state.portfolio:
        st.info("No applications assessed yet. Go to **Assess an Application** or **Bulk Upload** to get started.")
    else:
        top_c1, top_c2 = st.columns([3, 1])
        top_c1.caption("Scores reflect the weights currently set on the Configure Model page.")
        if top_c2.button("\U0001F504 Recalculate with current weights", use_container_width=True):
            recalculate_portfolio()
            st.rerun()

        results = [e["result"] for e in st.session_state.portfolio]
        df = pd.DataFrame(results).sort_values("quantum_risk_score", ascending=False)
        colors = band_color_map(st.session_state.config["priority_bands"])
        band_order = [b["label"] for b in sorted(st.session_state.config["priority_bands"], key=lambda b: b["threshold"], reverse=True)]

        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Total Applications", len(df))
        k2.metric(band_order[0] if len(band_order) > 0 else "-", int((df["priority_band"] == band_order[0]).sum()) if band_order else 0)
        k3.metric(band_order[1] if len(band_order) > 1 else "-", int((df["priority_band"] == band_order[1]).sum()) if len(band_order) > 1 else 0)
        k4.metric("Public Facing", int(df["is_public_facing"].sum()))

        c1, c2 = st.columns([1, 1])
        with c1:
            counts = df["priority_band"].value_counts().reindex([b for b in band_order if b in df["priority_band"].values])
            fig1 = px.bar(
                x=counts.index, y=counts.values,
                color=counts.index, color_discrete_map=colors,
                labels={"x": "", "y": "Number of Applications"},
                title="Applications by Migration Wave",
            )
            fig1.update_layout(showlegend=False, height=380)
            st.plotly_chart(fig1, use_container_width=True)
        with c2:
            fig2 = px.scatter(
                df, x="raw_impact_score", y="quantum_risk_score",
                color="priority_band", color_discrete_map=colors,
                size=[12] * len(df), hover_name="service_name",
                labels={"raw_impact_score": "Raw Impact Score", "quantum_risk_score": "Quantum Risk Score"},
                title="Impact vs. Final Risk Score (bubble = threat multiplier applied)",
            )
            fig2.update_layout(height=380)
            st.plotly_chart(fig2, use_container_width=True)

        st.subheader("Ranked Application List")
        display_df = df[[
            "service_id", "service_name", "application_tier", "is_public_facing",
            "raw_impact_score", "threat_multiplier", "quantum_risk_score", "priority_band",
        ]].reset_index(drop=True)
        max_mult = max(st.session_state.config["threat_multipliers"].values())
        st.dataframe(
            display_df, use_container_width=True, hide_index=True,
            column_config={
                "quantum_risk_score": st.column_config.ProgressColumn(
                    "Quantum Risk Score", min_value=0, max_value=max_mult, format="%.4f"
                ),
            },
        )

        out_buf = io.StringIO()
        df.to_csv(out_buf, index=False)
        st.download_button(
            "Download full results (CSV)", data=out_buf.getvalue(),
            file_name="quantum_risk_prioritisation_results.csv", mime="text/csv",
        )

        st.subheader("Category Contribution — Top 10 by Risk Score")
        top10 = df.head(10)
        cat_cols = ["loss_of_trust", "impacted_systems", "data_sensitivity", "financial_loss", "regulatory_censure"]
        fig3 = go.Figure()
        for col in cat_cols:
            fig3.add_bar(name=col.replace("_", " ").title(), x=top10["service_name"], y=top10[col])
        fig3.update_layout(barmode="stack", height=420, xaxis_title="", yaxis_title="Weighted Impact Contribution")
        st.plotly_chart(fig3, use_container_width=True)

        st.subheader("Remove an application")
        to_remove = st.selectbox("Select service to remove", ["-"] + list(df["service_id"]))
        if to_remove != "-" and st.button("Remove"):
            st.session_state.portfolio = [
                e for e in st.session_state.portfolio if e["profile"]["service_id"] != to_remove
            ]
            st.rerun()

# ---------------------------------------------------------------------------
# Page: Configure Model
# ---------------------------------------------------------------------------
elif page == "Configure Model":
    st.title("Configure Model")
    st.caption(
        "Every weight, score, multiplier, and priority-band threshold used by the engine lives here. "
        "Changes apply immediately to new assessments; use Recalculate on the Portfolio Dashboard to "
        "re-score applications you've already assessed."
    )

    top1, top2, top3 = st.columns(3)
    if top1.button("\u21BA Reset to Framework Defaults", use_container_width=True):
        st.session_state.config = default_config()
        st.session_state.cfg_nonce += 1
        st.rerun()

    cfg_json = json.dumps(st.session_state.config, indent=2)
    top2.download_button("\u2B07\uFE0F Download config (JSON)", data=cfg_json, file_name="quantum_risk_config.json",
                          mime="application/json", use_container_width=True)

    uploaded_cfg = top3.file_uploader("\u2B06\uFE0F Load config (JSON)", type=["json"], label_visibility="collapsed")
    if uploaded_cfg is not None:
        try:
            loaded = json.load(uploaded_cfg)
            required_keys = {"category_weights", "cia_split", "loss_of_trust_split", "impacted_systems_weights",
                              "data_sensitivity_weights", "rating_scores", "threat_multipliers", "priority_bands"}
            if not required_keys.issubset(loaded.keys()):
                st.error(f"Config JSON is missing required keys: {required_keys - loaded.keys()}")
            else:
                st.session_state.config = loaded
                st.session_state.cfg_nonce += 1
                st.success("Configuration loaded.")
                st.rerun()
        except Exception as e:
            st.error(f"Could not parse config JSON: {e}")

    warnings = validate_config(st.session_state.config)
    if warnings:
        st.warning("\n".join(f"- {w}" for w in warnings))
    else:
        st.success("All weight groups currently sum to 100%.")

    st.divider()
    st.subheader("Impact — Category (AHP) Weights")
    st.caption("Section 2: top-level weight of each of the five Impact parameters.")
    render_weight_group("category_weights", "Category Weights (%)")

    st.subheader("CIA Split")
    st.caption("Applied within Loss of Trust, Financial Loss, and Regulatory Censure — reflects that quantum "
               "attacks hit Confidentiality & Integrity harder than Availability.")
    render_weight_group("cia_split", "Confidentiality / Integrity / Availability (%)")

    st.subheader("Loss of Trust Sub-Split")
    st.caption("How the Loss of Trust category divides between Customer Detriment and Reputational Loss.")
    render_weight_group("loss_of_trust_split", "Customer Detriment / Reputational Loss (%)")

    st.subheader("Impacted Systems — Local Weights")
    st.caption("Section 5: relative weight of the four Impacted Systems intake questions.")
    render_weight_group("impacted_systems_weights", "IS-01 / IS-02 / IS-03 / IS-04 (%)")

    st.subheader("Data Sensitivity — Local Weights")
    st.caption("Relative weight of the three data-classification intake questions.")
    render_weight_group("data_sensitivity_weights", "Highly Restricted / Sensitive Personal / Personal (%)")

    st.subheader("Ordinal Rating Scale")
    st.caption("Score assigned to each qualitative BIA / ITSO rating (Section 4.1).")
    cols = st.columns(4)
    rs = st.session_state.config["rating_scores"]
    new_rs = {}
    for col, label in zip(cols, RATING_ORDER):
        new_rs[label] = col.number_input(label, min_value=0.0, max_value=1.0, value=float(rs[label]),
                                          step=0.01, key=f"rs_{label}_{st.session_state.cfg_nonce}")
    st.session_state.config["rating_scores"] = new_rs
    st.divider()

    st.subheader("Threat Exposure Multipliers")
    st.caption("Section 4.3: likelihood multiplier applied on top of the Impact score.")
    tm = st.session_state.config["threat_multipliers"]
    c1, c2 = st.columns(2)
    new_tm = {
        "public_facing": c1.number_input("Public Facing multiplier", min_value=0.5, max_value=5.0,
                                          value=float(tm["public_facing"]), step=0.05,
                                          key=f"tm_pub_{st.session_state.cfg_nonce}"),
        "internal": c2.number_input("Internal / restricted multiplier", min_value=0.5, max_value=5.0,
                                     value=float(tm["internal"]), step=0.05,
                                     key=f"tm_int_{st.session_state.cfg_nonce}"),
    }
    st.session_state.config["threat_multipliers"] = new_tm
    st.divider()

    st.subheader("Priority Bands")
    st.caption("Minimum Quantum Risk Score required for each migration wave. Add or remove rows as needed; "
               "thresholds should stay in descending order.")
    bands_df = pd.DataFrame(st.session_state.config["priority_bands"])
    edited_bands = st.data_editor(
        bands_df, num_rows="dynamic", use_container_width=True,
        column_config={
            "threshold": st.column_config.NumberColumn("Threshold", min_value=0.0, max_value=10.0, step=0.01),
            "label": st.column_config.TextColumn("Wave Label"),
        },
        key=f"bands_editor_{st.session_state.cfg_nonce}",
    )
    new_bands = edited_bands.dropna(subset=["threshold", "label"]).to_dict("records")
    if new_bands:
        st.session_state.config["priority_bands"] = new_bands

# ---------------------------------------------------------------------------
# Page: About the Model
# ---------------------------------------------------------------------------
else:
    st.title("About the Model")
    st.markdown(
        """
This app implements the **Quantum Risk Assessment & Prioritisation Framework (v2.0)**:
a deterministic scoring engine that computes a normalised **Quantum Risk Priority Score**
for an IT application, combining a weighted multi-attribute **Impact** score with a
**Likelihood** (threat exposure) multiplier.

**Risk = Impact × Likelihood.** Every weight, rating score, multiplier, and priority-band
threshold below is editable on the **Configure Model** page — the values shown here are
whatever is currently active.
"""
    )
    config = st.session_state.config

    st.subheader("Impact parameters (AHP weights)")
    weights_df = pd.DataFrame(
        [{"Parameter": k, "AHP Weight": f"{v*100:.1f}%"} for k, v in config["category_weights"].items()]
    )
    st.dataframe(weights_df, use_container_width=True, hide_index=True)

    st.subheader("Ordinal scale (Customer Detriment, Reputational Loss, Financial Loss, Regulatory Censure)")
    st.table(pd.DataFrame({"Rating": RATING_ORDER, "Score": [config["rating_scores"][r] for r in RATING_ORDER]}))

    st.subheader("Dichotomic scale (Impacted Systems, Data Sensitivity)")
    st.write("'No' / False → 0.0  |  'Yes' / True → 1.0")

    st.subheader("Threat Exposure Multipliers")
    st.table(pd.DataFrame({
        "Exposure": ["Public Facing", "Internal / Restricted"],
        "Multiplier": [config["threat_multipliers"]["public_facing"], config["threat_multipliers"]["internal"]],
    }))

    st.subheader("Priority Bands")
    bands_sorted = sorted(config["priority_bands"], key=lambda b: b["threshold"], reverse=True)
    st.table(pd.DataFrame({
        "Band": [b["label"] for b in bands_sorted],
        "Minimum Quantum Risk Score": [b["threshold"] for b in bands_sorted],
    }))

    st.caption(
        "Future Likelihood Roadmap (per spec): integration of Mosca's Theorem "
        "(migration time + shelf life vs. time to cryptographic compromise) and "
        "cryptographic exposure metrics (TLS/PKI density, HSM usage)."
    )

# ---------------------------------------------------------------------------
# Sidebar validity indicator — rendered last so it reflects any edits the
# current page body made to st.session_state.config in this same run.
# ---------------------------------------------------------------------------
_final_warnings = validate_config(st.session_state.config)
if _final_warnings:
    sidebar_validity_slot.warning(
        "Model configuration needs attention:\n\n" + "\n".join(f"- {w}" for w in _final_warnings)
    )
else:
    sidebar_validity_slot.success("Model configuration is valid (all weight groups = 100%).")
