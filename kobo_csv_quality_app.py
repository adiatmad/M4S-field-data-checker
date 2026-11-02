"""Streamlit interface for local-first, generic Kobo CSV quality checks."""
from __future__ import annotations

import json

import streamlit as st

from kobo_csv_quality import QualityCheckError, findings_summary, read_csv_bytes, run_quality_checks

st.set_page_config(page_title="Kobo CSV Quality Checker", layout="wide")
st.title("Check a KoboToolbox CSV file")
st.caption(
    "Run this app on your own computer to keep survey files on your machine. If your team hosts it, "
    "uploads are processed on that server; ask them before uploading real field data."
)

with st.expander("First time here? Read this before you start"):
    st.markdown(
        """
        1. In KoboToolbox, download your survey data and choose CSV as the format.
        2. Keep that download as your unchanged copy.
        3. Upload it below. The checks start on their own and the results appear under the upload box.
        4. Use the row number and column name to find each answer in KoboToolbox.

        A finding means "please check this row". It does not prove the answer is wrong.
        """
    )

with st.expander("What this checks and what it does not"):
    st.markdown(
        """
        **It checks** the CSV structure, blank answers and configured missing-value tokens, exact
        duplicate rows, unusual numbers, optional spelling-variant suggestions, and an optional rules
        file with required columns, allowed values, types, ranges, and unique keys.

        **It does not check** your form's skip logic, choice lists, or repeat groups, and it does not
        apply survey-specific rules. It never changes your answers.

        These are screening flags, not proof that a record is wrong. Review flagged values before
        changing source data.
        """
    )

st.subheader("Step 1: Upload your CSV file")
uploaded = st.file_uploader(
    "Choose a KoboToolbox CSV export (.csv)",
    type=["csv"],
    help="The file name usually ends in .csv. A .csv file is a plain table of answers.",
)

with st.expander("Choose what to check"):
    st.caption("These settings suit most surveys. Change them only when your team asks you to.")
    missing_text = st.text_input(
        "Treat these answers as missing (comma-separated)",
        value=",NA,N/A,NULL,null",
        help="Answers in this list are reported as missing. The leading comma means empty cells count as missing.",
    )
    check_duplicates = st.checkbox(
        "Find rows that are exact copies of another row",
        value=True,
        help="Rows with identical values in every column. Nothing is deleted or merged.",
    )
    check_outliers = st.checkbox(
        "Point out unusual numbers for review",
        value=True,
        help="Compares each number with the other values in its column. An unusual number may still be a real answer.",
    )
    check_similar_values = st.checkbox(
        "Suggest values that look like spelling variants",
        value=False,
        help="Review suggestions only. The checker never merges or rewrites values.",
    )
    contract_file = st.file_uploader(
        "Optional: team rules file (.json)",
        type=["json"],
        help="Only use a rules file supplied by the person who owns the survey.",
    )
contract = None
if contract_file is not None:
    try:
        contract = json.loads(contract_file.getvalue().decode("utf-8"))
        if not isinstance(contract, dict):
            raise ValueError("The file must contain one JSON object holding the rules.")
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        st.error(
            f"The team rules file could not be read: {exc} Remove it to run the standard checks "
            "without team rules."
        )
        st.stop()

if uploaded is None:
    st.info(
        "Choose the .csv file you downloaded from KoboToolbox. The checks start on their own and the "
        "results appear here."
    )
    st.stop()

data = uploaded.getvalue()
try:
    frame = read_csv_bytes(data)
except ValueError as exc:
    st.error(f"This file could not be read as a CSV table: {exc}")
    st.stop()

tokens = tuple(token.strip() for token in missing_text.split(","))
try:
    with st.spinner("Checking your file. Large files can take a minute."):
        findings = run_quality_checks(
            data, uploaded.name, frame,
            missing_tokens=tokens,
            duplicate_rows=check_duplicates,
            outlier_checks=check_outliers,
            similar_text_values=check_similar_values,
            contract=contract,
        )
except QualityCheckError as exc:
    st.error(
        f"The checks stopped during the {exc.stage} step, so no results are shown. "
        "Try the same file once more. If it stops again, tell your coordinator the name of that "
        "step; do not send the survey file itself."
    )
    st.stop()

summary = findings_summary(findings)
st.subheader("Step 2: Read the summary")
a, b, c, d = st.columns(4)
a.metric("Rows", len(frame), help="One row is one survey record.")
b.metric("Columns", len(frame.columns), help="One column is one question or system field.")
c.metric(
    "Findings",
    summary["findings"],
    help="One finding is one answer or row to check. A single row can have more than one.",
)
d.metric(
    "Rows with a finding",
    summary["affected_rows"],
    help="Rows where at least one enabled check reported something to review.",
)
st.caption(
    'A finding means "please check this row", not "this answer is wrong". Rows without a finding '
    "were not proven correct; they only passed the checks you switched on."
)

st.subheader("Step 3: Review the findings")
if findings.empty:
    st.success(
        "The checks you switched on did not report anything. That means these checks found nothing "
        "to review, not that every answer is correct."
    )
else:
    st.caption(
        "Row numbers count the header as row 1, so row 2 is the first survey record. Use the row and "
        "column to find the answer in KoboToolbox."
    )
    categories = st.multiselect(
        "Show only these kinds of finding", sorted(findings["category"].dropna().unique())
    )
    visible = findings[findings["category"].isin(categories)] if categories else findings
    st.caption(
        f"Showing the first {min(10, len(visible))} of {len(visible):,} findings. Download the CSV to "
        "see every one."
    )
    st.dataframe(visible.head(10), width="stretch", hide_index=True)
    st.download_button(
        "Download findings (.csv)",
        data=visible.to_csv(index=False).encode("utf-8"),
        file_name="kobo_csv_findings.csv",
        mime="text/csv",
        help="The findings shown above, ready to share with the team.",
    )

st.subheader("Step 4: Download or inspect the data")
with st.expander("Preview the file that was read (first 100 rows)"):
    st.dataframe(frame.head(100), width="stretch", hide_index=True)

st.download_button(
    "Download unchanged input CSV",
    data=data,
    file_name=uploaded.name,
    mime="text/csv",
    help="Exactly the file you uploaded, unchanged. Keep it as your source copy.",
)
st.caption(
    "Fix approved problems in your usual data process, then run these checks again on the new export."
)
