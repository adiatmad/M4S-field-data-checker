"""
M4S Seagrass QA — Streamlit front end
======================================
Thin UI wrapper around m4s_seagrass_qa.py. All the actual QA logic
still lives in that file and is untouched — this just gives you a
point-and-click way to run it after a field day instead of the
terminal.

Run locally:
    pip install streamlit pandas numpy rapidfuzz openpyxl tabulate
    streamlit run streamlit_app.py

Then open the URL it prints (usually http://localhost:8501).
"""

import io
import pandas as pd
import streamlit as st

from m4s_seagrass_qa import (
    load_data, standardize, validate, correct, generate_qa_report,
)

st.set_page_config(page_title="M4S Seagrass QA", layout="wide")
st.title("M4S Seagrass QA — Metinaro")
st.caption("Upload the raw Kobo export (.xlsx). Nothing is saved to a server — "
           "everything happens in this session and outputs are yours to download.")

uploaded = st.file_uploader("Raw Kobo export (.xlsx)", type=["xlsx"])

if uploaded is None:
    st.info("Upload a file to run the pipeline.")
    st.stop()

# ---- run the pipeline (same stages as the CLI version) ----
try:
    raw_df, df = load_data(uploaded)
except ValueError as e:
    st.error(str(e))
    st.stop()

df = standardize(df)
issues = validate(df)
clean_df, correction_log = correct(df)

# ---- summary metrics ----
total = len(clean_df)
flagged = issues.row_index.nunique() if len(issues) else 0
errors = (issues.severity == "error").sum() if len(issues) else 0
warnings = (issues.severity == "warning").sum() if len(issues) else 0

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Total records", total)
c2.metric("Clean records", total - flagged)
c3.metric("Errors", int(errors))
c4.metric("Warnings", int(warnings))
c5.metric("Safe corrections applied", len(correction_log))

st.divider()

tab_report, tab_issues, tab_corrections, tab_clean = st.tabs(
    ["QA report", "Issue list", "Correction log", "Clean dataset"]
)

with tab_report:
    # build the same markdown report the CLI writes, but keep it in memory
    buf = io.StringIO()
    import tempfile, pathlib
    with tempfile.NamedTemporaryFile(suffix=".md", delete=False) as tmp:
        generate_qa_report(clean_df, issues, correction_log, tmp.name)
        report_text = pathlib.Path(tmp.name).read_text(encoding="utf-8")
    st.markdown(report_text)
    st.download_button("Download qa_report.md", report_text,
                        file_name="qa_report.md")

with tab_issues:
    st.dataframe(issues, use_container_width=True)
    st.download_button("Download qa_issues.csv", issues.to_csv(index=False),
                        file_name="qa_issues.csv")

with tab_corrections:
    st.dataframe(correction_log, use_container_width=True)
    st.download_button("Download correction_log.csv", correction_log.to_csv(index=False),
                        file_name="correction_log.csv")

with tab_clean:
    st.dataframe(clean_df, use_container_width=True)
    st.download_button("Download clean_dataset.csv", clean_df.to_csv(index=False),
                        file_name="clean_dataset.csv")
    st.download_button("Download raw_preserved.csv", raw_df.to_csv(index=False),
                        file_name="raw_preserved.csv")
