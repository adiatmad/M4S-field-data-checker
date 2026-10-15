"""Streamlit interface for local-first, generic Kobo CSV quality checks."""
from __future__ import annotations

import streamlit as st

from kobo_csv_quality import findings_summary, read_csv_bytes, structural_issues, validate_dataframe

st.set_page_config(page_title="Kobo CSV Quality Checker", page_icon="🧭", layout="wide")
st.title("🧭 Kobo CSV Quality Checker")
st.caption("Generic, local-first checks for raw KoboToolbox CSV exports. No data is uploaded to a third-party service by this app.")

with st.expander("What this checks"):
    st.markdown("""
    - **CSV structure:** malformed rows and resource-level issues (Frictionless).
    - **Missing values:** blank cells and configurable missing-value tokens.
    - **Duplicates:** exact duplicate rows.
    - **Anomalies:** optional IQR screening for numeric-looking columns.
    - **Schema stage:** Pandera dataframe validation; this generic mode does not guess survey-specific types or business rules.

    These are screening flags, not proof that a record is wrong. Review flagged values before changing source data.
    """)

uploaded = st.file_uploader("Upload a raw Kobo CSV export", type=["csv"])
missing_text = st.text_input("Missing-value tokens (comma-separated)", value=",NA,N/A,NULL,null")
check_duplicates = st.checkbox("Check exact duplicate rows", value=True)
check_outliers = st.checkbox("Screen numeric-looking columns for outliers (IQR)", value=True)

if uploaded is not None:
    data = uploaded.getvalue()
    try:
        frame = read_csv_bytes(data)
    except ValueError as exc:
        st.error(str(exc))
        st.stop()

    with st.spinner("Checking CSV structure and values…"):
        structure = structural_issues(data, uploaded.name)
        tokens = tuple(token.strip() for token in missing_text.split(","))
        findings = validate_dataframe(
            frame, missing_tokens=tokens,
            duplicate_rows=check_duplicates, outlier_checks=check_outliers,
        )
        if structure:
            import pandas as pd
            findings = pd.concat([pd.DataFrame(structure), findings], ignore_index=True)
            findings = findings[["row_number", "column", "category", "severity", "message"]]

    summary = findings_summary(findings)
    a, b, c, d = st.columns(4)
    a.metric("Rows", len(frame))
    b.metric("Columns", len(frame.columns))
    c.metric("Findings", summary["findings"])
    d.metric("Affected rows", summary["affected_rows"])

    st.subheader("Findings")
    if findings.empty:
        st.success("No findings from the enabled generic checks.")
    else:
        categories = st.multiselect("Filter categories", sorted(findings["category"].dropna().unique()))
        visible = findings[findings["category"].isin(categories)] if categories else findings
        st.dataframe(visible, use_container_width=True, hide_index=True)
        st.download_button(
            "Download findings CSV",
            data=visible.to_csv(index=False).encode("utf-8"),
            file_name="kobo_csv_findings.csv",
            mime="text/csv",
        )

    with st.expander("Preview input (first 100 rows)"):
        st.dataframe(frame.head(100), use_container_width=True)

    st.download_button(
        "Download unchanged input CSV",
        data=data,
        file_name=uploaded.name,
        mime="text/csv",
    )
else:
    st.info("Upload a CSV to begin. Your file is processed in this Streamlit session; do not deploy behind a public service without reviewing your data-protection requirements.")
