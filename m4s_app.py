"""
M4S Field Data QA Checker — Streamlit front end
================================================
Enhanced version with QA columns for easy filtering of issues.
"""

import io
import pandas as pd
import streamlit as st
from datetime import datetime
import tempfile
import pathlib
import uuid

from m4s_seagrass_qa import (
    load_data, standardize, validate, correct, generate_qa_report,
    add_qa_columns,
    SPECIES_LIST, CANONICAL_ADMIN_POST, CANONICAL_VILLAGE
)

st.set_page_config(page_title="M4S Field Data QA Checker", layout="wide")
st.title("🌿 M4S Field Data QA Checker")
st.caption("Upload the raw Kobo export (.xlsx). Nothing is saved to a server — "
           "everything happens in this session and outputs are yours to download.")

uploaded = st.file_uploader("Raw Kobo export (.xlsx)", type=["xlsx"])

if uploaded is None:
    st.info("📤 Upload a file to run the pipeline.")
    st.stop()

# ---- run the pipeline ----
with st.spinner("Running QA pipeline..."):
    try:
        raw_df, df = load_data(uploaded)
    except ValueError as e:
        st.error(f"❌ Error loading data: {str(e)}")
        st.stop()

    df = standardize(df)
    issues = validate(df)
    
    # Add QA columns to the raw data
    raw_with_qa = add_qa_columns(raw_df, issues)
    
    clean_df, correction_log = correct(df)

# ---- summary metrics ----
total = len(clean_df)
flagged = issues.row_index.nunique() if len(issues) else 0
errors = (issues.severity == "error").sum() if len(issues) else 0
warnings = (issues.severity == "warning").sum() if len(issues) else 0

st.divider()
col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("📊 Total records", total)
col2.metric("✅ Clean records", total - flagged)
col3.metric("❌ Errors", int(errors), help="Must be fixed before analysis")
col4.metric("⚠️ Warnings", int(warnings), help="Review and decide if action needed")
col5.metric("🔧 Corrections applied", len(correction_log))

st.divider()

# ---- QA COLUMNS OVERVIEW ----
st.subheader("🔍 QA Columns — Quick Issue Identification")
st.markdown("""
The raw data now includes QA flag columns and a Message column. Each flag column indicates if a row has a specific type of issue.
The Message column provides detailed descriptions of all issues for each row.
**Filter by any column to find rows that need fixing!**
""")

# Show QA columns summary
qa_cols = ['qa_species_typo', 'qa_gps_precision_0', 'qa_missing_coordinates', 
           'qa_outside_boundary', 'qa_duplicate_uuid', 'qa_species_logic',
           'qa_geography_mismatch', 'qa_coverage_mismatch']

qa_summary = {}
for col in qa_cols:
    if col in raw_with_qa.columns:
        count = (raw_with_qa[col] == 'Yes').sum()
        # Also check for "Yes" with additional info (coverage mismatch)
        if col == 'qa_coverage_mismatch':
            count = raw_with_qa[col].str.startswith('Yes', na=False).sum()
        qa_summary[col.replace('qa_', '').replace('_', ' ').title()] = count

if sum(qa_summary.values()) > 0:
    cols = st.columns(len(qa_summary))
    for i, (name, count) in enumerate(qa_summary.items()):
        if count > 0:
            cols[i].metric(f"⚠️ {name}", count, delta=None)
        else:
            cols[i].metric(f"✅ {name}", 0, delta=None)
else:
    st.success("🎉 No QA flags triggered! All data looks clean.")

st.divider()

# ---- FILTERABLE DATA VIEW ----
st.subheader("📊 Filter Raw Data by QA Flags")

# Show the raw data with QA columns
display_df = raw_with_qa.copy()

# Add filter options
filter_cols = st.columns(4)
with filter_cols[0]:
    show_only_with_issues = st.checkbox("Show only rows with issues", value=False)
with filter_cols[1]:
    if show_only_with_issues:
        qa_cols_for_filter = st.multiselect(
            "Filter by QA Flag",
            options=qa_cols,
            default=qa_cols
        )
with filter_cols[2]:
    if not show_only_with_issues:
        search = st.text_input("Search in data", placeholder="Search any column...")
with filter_cols[3]:
    show_message_only = st.checkbox("Show only rows with Message", value=False)

# Apply filters
if show_only_with_issues:
    # Show only rows with any QA flag
    mask = pd.Series(False, index=display_df.index)
    for col in qa_cols_for_filter:
        if col in display_df.columns:
            if col == 'qa_coverage_mismatch':
                mask = mask | display_df[col].str.startswith('Yes', na=False)
            else:
                mask = mask | (display_df[col] == 'Yes')
    display_df = display_df[mask]
elif show_message_only:
    display_df = display_df[display_df['Message'] != '']
elif search:
    # Simple search across all columns
    mask = pd.Series(False, index=display_df.index)
    for col in display_df.select_dtypes(include=['object', 'string']).columns:
        mask = mask | display_df[col].astype(str).str.contains(search, case=False, na=False)
    display_df = display_df[mask]

# Show count
st.caption(f"Showing {len(display_df)} rows")

# Display the data - highlight QA columns and Message
st.dataframe(
    display_df,
    width='stretch',
    column_config={
        col: st.column_config.Column(
            col,
            help=f"QA flag: 'Yes' indicates this row has the issue",
            width='small'
        ) for col in qa_cols if col in display_df.columns
    }
)

# ---- DOWNLOAD BUTTONS ----
st.divider()
col1, col2, col3 = st.columns(3)
with col1:
    st.download_button(
        "📥 Download Raw Data with QA Flags & Messages",
        raw_with_qa.to_csv(index=False),
        file_name="raw_with_qa_flags.csv"
    )
with col2:
    st.download_button(
        "📥 Download QA Issues List",
        issues.to_csv(index=False),
        file_name="qa_issues.csv"
    )
with col3:
    st.download_button(
        "📥 Download Filtered View",
        display_df.to_csv(index=False),
        file_name=f"filtered_data_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
    )

st.divider()

# ---- ORIGINAL TABS ----
tab_report, tab_issues, tab_corrections, tab_clean = st.tabs(
    ["📋 QA Report", "📊 Issue List", "🔧 Correction Log", "✨ Clean Dataset"]
)

with tab_report:
    with tempfile.NamedTemporaryFile(suffix=".md", delete=False) as tmp:
        generate_qa_report(clean_df, issues, correction_log, tmp.name)
        report_text = pathlib.Path(tmp.name).read_text(encoding="utf-8")
    st.markdown(report_text)
    st.download_button("📥 Download qa_report.md", report_text, file_name="qa_report.md")

with tab_issues:
    st.dataframe(issues, width='stretch')
    st.download_button(
        "📥 Download qa_issues.csv",
        issues.to_csv(index=False),
        file_name="qa_issues.csv"
    )

with tab_corrections:
    st.dataframe(correction_log, width='stretch')
    st.download_button(
        "📥 Download correction_log.csv",
        correction_log.to_csv(index=False),
        file_name="correction_log.csv"
    )

with tab_clean:
    st.dataframe(clean_df, width='stretch')
    st.download_button(
        "📥 Download clean_dataset.csv",
        clean_df.to_csv(index=False),
        file_name="clean_dataset.csv"
    )

# ---- QUICK REFERENCE ----
with st.expander("📖 QA Column Reference"):
    st.markdown("""
    ### QA Flag Columns Explained
    
    | Column | Description | When triggered |
    |--------|-------------|----------------|
    | **qa_species_typo** | Species name typo | Species name doesn't match `SPECIES_LIST` |
    | **qa_gps_precision_0** | GPS precision is 0.0 | Recorded precision is 0.0 (likely no GPS fix) |
    | **qa_missing_coordinates** | Missing GPS coordinates | No lat/long recorded |
    | **qa_outside_boundary** | Outside survey area | GPS point >500m from site centroid |
    | **qa_duplicate_uuid** | Duplicate submission | Same UUID appears more than once |
    | **qa_species_logic** | Species logic error | Species marked present but 0% cover, or vice versa |
    | **qa_geography_mismatch** | Geography mismatch | Admin Post/Village doesn't match project area |
    | **qa_coverage_mismatch** | Coverage mismatch | Individual species % don't sum to total cover |
    
    ### Message Column
    The `Message` column provides detailed descriptions of all issues for each row.
    Multiple issues are separated by semicolons (;).
    
    ### How to Use This Tool
    1. **Review the summary** to understand what issues exist
    2. **Filter by QA columns** to find all rows with specific issues
    3. **Check the Message column** for detailed error descriptions
    4. **Download raw_with_qa_flags.csv** to fix issues in Excel
    5. **Fix issues in the raw data** and re-upload
    6. **Use the Message column** as a checklist during data cleaning
    """)

st.caption(f"📁 Dataset: {uploaded.name} | 📊 Records: {total} | ⚠️ Issues: {len(issues)} | 🔧 Corrections: {len(correction_log)}")
