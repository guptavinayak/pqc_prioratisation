# Quantum Risk Prioritisation Engine

A Streamlit app implementing the **Quantum Risk Assessment & Prioritisation
Framework (v2.0)** — scores IT applications for PQC migration prioritisation
using the AHP-weighted Impact model and threat-exposure Likelihood multiplier
from the framework document.

## Files

- `engine.py` — the scoring engine (pure Python, no Streamlit dependency).
  Validated against the framework's Section 8 reference test case
  (Payments Orchestration Service → 0.6265 → Wave 2).
- `app.py` — the Streamlit UI: single-application assessment form, bulk CSV
  upload, portfolio dashboard with wave distribution and ranked list, and a
  reference page explaining the model.
- `requirements.txt` — dependencies.

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

Then open the local URL Streamlit prints (typically http://localhost:8501).

## What it does

1. **Assess an Application** — fill in a form (CIA ordinal ratings for
   Customer Detriment, Reputational Loss, Financial Loss, Regulatory
   Censure; boolean intake questions for Impacted Systems and Data
   Sensitivity; public-facing toggle) and get an instant Quantum Risk Score,
   priority wave, and a breakdown chart of which category drove the score.
2. **Bulk Upload** — download a CSV template matching the intake schema,
   fill it in for many applications (e.g. exported from a BIA/ITSO system),
   upload it, and get every application scored and ranked at once.
3. **Portfolio Dashboard** — see the full ranked list, wave distribution,
   an impact-vs-risk scatter plot, a stacked category-contribution chart for
   the top 10 applications, and export the scored portfolio as CSV.
4. **Configure Model** — every weight, score, multiplier, and priority-band
   threshold the engine uses is editable here, nothing is hardcoded:
   - Category (AHP) weights, CIA split, Loss of Trust sub-split, Impacted
     Systems local weights, and Data Sensitivity local weights — each with
     a live sum indicator and a one-click **Normalize** to rescale back to
     100%.
   - The ordinal rating scores (Minor/Moderate/Major/Extreme).
   - The public-facing / internal threat multipliers.
   - Priority-band thresholds and labels — add, remove, or rename waves
     via an editable table.
   - **Reset to Framework Defaults**, and **download/upload the whole
     configuration as JSON** so you can save named presets (e.g. a more
     conservative model, a different bank's AHP weighting) and reload them.
   - Changes apply immediately to new assessments. Already-scored
     applications keep their original inputs, so hitting **Recalculate
     with current weights** on the Portfolio Dashboard re-scores the
     whole portfolio under the new configuration without re-entering data.
5. **About the Model** — the AHP weights, rating scales, and priority-band
   thresholds *currently in effect* (reflecting any customisation), for
   reference.

## Notes

- The engine is a direct implementation of Section 7 (`QuantumPrioritisationEngine`)
  of the framework. Every weight lives in a single `CONFIG` dict
  (`engine.default_config()`), and `calculate_risk(app, config)` derives
  the Section-3 leaf-level weights from it on the fly — so the UI, a saved
  JSON preset, or a script can all drive the same engine.
- The portfolio stores each application's *raw inputs* alongside its
  scored result, which is what makes "Recalculate with current weights"
  possible after a configuration change.
- Likelihood is currently the binary public-facing multiplier (Section 4.3),
  both values of which are configurable. The framework's roadmap item —
  Mosca's Theorem and TLS/PKI/HSM exposure metrics — is not yet
  implemented; `engine.py` is the place to extend it when that data
  becomes available.
