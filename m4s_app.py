"""
M4S Seagrass QA — Streamlit front end
======================================
Enhanced version with guided spot-checking workflow.
Provides point-and-click way to run QA/QC and systematically review flagged issues.
"""

import io
import pandas as pd
import streamlit as st
import plotly.express as px
from datetime import datetime

from m4s_seagrass_qa import (
    load_data, standardize, validate, correct, generate_qa_report,
    SPECIES_LIST, CANONICAL_ADMIN_POST, CANONICAL_VILLAGE
)

st.set_page_config(page_title="M4S Seagrass QA", layout="wide")
st.title("M4S Seagrass QA — Metinaro")
st.caption("Upload the raw Kobo export (.xlsx). Nothing is saved to a server — "
           "everything happens in this session and outputs are yours to download.")

# Initialize session state for tracking reviewed issues
if 'reviewed_issues' not in st.session_state:
    st.session_state.reviewed_issues = set()
if 'issue_notes' not in st.session_state:
    st.session_state.issue_notes = {}
if 'review_status' not in st.session_state:
    st.session_state.review_status = {}

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
c5
