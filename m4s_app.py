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

# ---- Guided Spot-Checking Workflow ----
st.subheader("🔍 Guided Spot-Checking Workflow")
st.markdown("""
Follow these steps to systematically review and correct issues in your data.
The workflow is based on the SOP to ensure consistency across field days.
""")

# Step 1: Summary by Category
st.markdown("### Step 1: Review Issue Summary")
if len(issues):
    col1, col2 = st.columns([2, 1])
    with col1:
        # Create a summary table
        issue_summary = issues.groupby(['category', 'severity']).size().reset_index(name='count')
        issue_pivot = issue_summary.pivot(index='category', columns='severity', values='count').fillna(0)
        issue_pivot['total'] = issue_pivot.sum(axis=1)
        
        # Add quick reference for common issues
        st.dataframe(
            issue_pivot,
            use_container_width=True,
            column_config={
                "category": "Issue Category",
                "error": st.column_config.NumberColumn("Errors", help="Must be fixed"),
                "warning": st.column_config.NumberColumn("Warnings", help="Needs review"),
                "total": st.column_config.NumberColumn("Total", help="Total issues in category")
            }
        )
    
    with col2:
        # Quick guidance based on categories
        st.info("""
        **Quick Reference:**
        - **gps**: Check precision & location
        - **species**: Verify species names & logic
        - **duplicate**: Review for data entry errors
        - **geography**: Verify admin post/village
        - **logic**: Check mandatory fields & logic
        """)
else:
    st.success("🎉 No issues found! Dataset is clean.")
    st.stop()

st.divider()

# Step 2: Species Typo Checker
st.markdown("### Step 2: Check Species Typos")
st.markdown(f"**Species in the form:** {', '.join(SPECIES_LIST)}")

# Find potential species typos
species_cols = [col for col in df.columns if col.startswith("Seagrass species present in the Quadrat/") or 
                col.startswith("Percent ") and " (%)" in col]
species_values = []
for col in species_cols:
    # Get unique non-null values that aren't 0/1
    if col.startswith("Percent"):
        continue
    unique_vals = df[col].dropna().unique()
    for val in unique_vals:
        if val not in [0, 1, "0", "1"]:
            species_values.append(val)

# Check against canonical list
suspected_typos = []
for val in species_values:
    if isinstance(val, str) and val not in SPECIES_LIST:
        # Check if it's close to a species name
        from rapidfuzz import fuzz
        for sp in SPECIES_LIST:
            if fuzz.token_sort_ratio(val.lower(), sp.lower()) > 85:
                suspected_typos.append({
                    "original": val,
                    "suspected_correct": sp,
                    "similarity": fuzz.token_sort_ratio(val.lower(), sp.lower())
                })
                break

if suspected_typos:
    st.warning(f"⚠️ Found {len(suspected_typos)} potential species typos!")
    typos_df = pd.DataFrame(suspected_typos)
    st.dataframe(typos_df, use_container_width=True)
    
    st.markdown("""
    **Action Required:**
    If these are genuine typos, update the species names in the raw data and re-upload.
    Common typos to check for:
    - `Thhalassia hemprichii` → `Thalassia hemprichii`
    - `Halophilaminor` → `Halophila minor`
    - `Halodulepinifolia` → `Halodule pinifolia`
    """)
    
    # Allow user to download a correction template
    csv = typos_df.to_csv(index=False)
    st.download_button(
        "📥 Download species typo list for correction",
        csv,
        file_name=f"species_typos_{datetime.now().strftime('%Y%m%d')}.csv"
    )
else:
    st.success("✅ No obvious species typos detected.")

st.divider()

# Step 3: Interactive Issue Review
st.markdown("### Step 3: Systematic Issue Review")
st.markdown("""
This interactive table helps you spot-check and document issues systematically.
Filter by category, severity, or row to focus on specific problems.
""")

# Create filters for the issues table
col1, col2, col3 = st.columns(3)
with col1:
    filter_category = st.multiselect(
        "Filter by Category",
        options=issues['category'].unique(),
        default=issues['category'].unique()
    )
with col2:
    filter_severity = st.multiselect(
        "Filter by Severity",
        options=['error', 'warning'],
        default=['error', 'warning']
    )
with col3:
    filter_field = st.text_input("Filter by Field (contains)", "")

# Apply filters
filtered_issues = issues[
    (issues['category'].isin(filter_category)) &
    (issues['severity'].isin(filter_severity))
]
if filter_field:
    filtered_issues = filtered_issues[
        filtered_issues['field'].str.contains(filter_field, case=False, na=False)
    ]

# Add review status tracking
if 'review_status' not in st.session_state:
    st.session_state.review_status = {}

# Create a unique key for each issue
filtered_issues['issue_key'] = filtered_issues.apply(
    lambda x: f"{x.row_index}_{x.category}_{x.field}", axis=1
)

# Display issues with review checkbox
st.write(f"Showing {len(filtered_issues)} issues")

for idx, row in filtered_issues.iterrows():
    key = row['issue_key']
    with st.expander(f"Row {row.row_index} | {row.category} | {row.severity.upper()}"):
        col1, col2 = st.columns([3, 1])
        with col1:
            st.markdown(f"**Field:** `{row['field']}`")
            st.markdown(f"**Message:** {row['message']}")
            
            # Show raw data for context
            if row['row_index'] in df.index:
                st.caption("**Context (surrounding data):**")
                context_start = max(0, row['row_index'] - 2)
                context_end = min(len(df), row['row_index'] + 3)
                context_df = df.iloc[context_start:context_end][
                    ['_uuid', 'Collector Name', 'Transect Number', 'Quadrat Number']
                ]
                st.dataframe(context_df)
        
        with col2:
            # Review status
            if key not in st.session_state.review_status:
                st.session_state.review_status[key] = "Unreviewed"
            
            status = st.radio(
                "Review Status",
                options=["Unreviewed", "Needs Correction", "Checked OK", "Needs Field Team Review"],
                key=f"status_{key}",
                index=0
            )
            st.session_state.review_status[key] = status
            
            # Notes
            note_key = f"note_{key}"
            if note_key not in st.session_state.issue_notes:
                st.session_state.issue_notes[note_key] = ""
            
            note = st.text_area(
                "Notes",
                value=st.session_state.issue_notes.get(note_key, ""),
                key=f"note_input_{key}",
                placeholder="e.g., 'Confirmed typo - need to correct in raw data'"
            )
            st.session_state.issue_notes[note_key] = note
            
            # For GPS issues, show the actual GPS coordinates
            if row['category'] == 'gps':
                if row['row_index'] in df.index:
                    lat = df.loc[row['row_index'], '_Local GPS_latitude']
                    lon = df.loc[row['row_index'], '_Local GPS_longitude']
                    if pd.notna(lat) and pd.notna(lon):
                        st.caption(f"📍 GPS: {lat:.6f}, {lon:.6f}")

# Summary of review status
st.markdown("### Review Progress")
review_summary = pd.DataFrame.from_dict(
    st.session_state.review_status, orient='index', columns=['status']
)
status_counts = review_summary['status'].value_counts()
col1, col2, col3, col4 = st.columns(4)
col1.metric("✅ Checked OK", status_counts.get("Checked OK", 0))
col2.metric("⚠️ Needs Correction", status_counts.get("Needs Correction", 0))
col3.metric("📋 Needs Field Review", status_counts.get("Needs Field Team Review", 0))
col4.metric("⏳ Unreviewed", status_counts.get("Unreviewed", 0))

st.divider()

# Step 4: Generate Spot-Check Report
st.markdown("### Step 4: Generate Spot-Check Report")
st.markdown("""
Export a summary of your spot-checking session including:
- All reviewed issues with your notes
- Summary of what needs to be corrected
- Recommended actions for the field team
""")

if st.button("📊 Generate Spot-Check Summary Report"):
    # Create a comprehensive report
    report_lines = []
    report_lines.append(f"# M4S Seagrass Spot-Check Report")
    report_lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    report_lines.append(f"Total records reviewed: {len(df)}")
    report_lines.append(f"Issues found: {len(issues)}")
    report_lines.append("")
    
    # Summary of issues by category
    report_lines.append("## Issue Summary")
    issue_summary = issues.groupby(['category', 'severity']).size().reset_index(name='count')
    report_lines.append(issue_summary.to_markdown())
    report_lines.append("")
    
    # Review status summary
    report_lines.append("## Review Status")
    for status, count in status_counts.items():
        report_lines.append(f"- **{status}**: {count} issues")
    report_lines.append("")
    
    # Detailed review log
    report_lines.append("## Detailed Review Log")
    report_lines.append("| Row | Category | Severity | Field | Message | Status | Notes |")
    report_lines.append("|-----|----------|----------|-------|---------|--------|-------|")
    
    for _, row in filtered_issues.iterrows():
        key = row['issue_key']
        status = st.session_state.review_status.get(key, "Unreviewed")
        note_key = f"note_{key}"
        note = st.session_state.issue_notes.get(note_key, "")
        
        report_lines.append(
            f"| {row['row_index']} | {row['category']} | {row['severity']} | "
            f"{row['field']} | {row['message'][:50]}... | {status} | {note[:50]}... |"
        )
    
    report_text = "\n".join(report_lines)
    
    st.download_button(
        "📥 Download Spot-Check Report",
        report_text,
        file_name=f"spot_check_report_{datetime.now().strftime('%Y%m%d')}.md",
        mime="text/markdown"
    )
    
    st.success("Report generated successfully!")

st.divider()

# ---- Original tabs (QA report, Issue list, etc.) ----
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

# ---- Footer with helpful tips ----
st.divider()
with st.expander("📖 Quick Reference: Common Errors & How to Fix Them"):
    st.markdown("""
    ### Common Errors and Their Fixes
    
    | Error Type | Example | How to Fix |
    |------------|---------|------------|
    | **Species Typos** | `Halophilaminor`, `Thhalassia hemprichii` | Correct in raw XLSX and re-upload, or update `SPECIES_LIST` in code |
    | **GPS Precision 0** | Precision is recorded as `0.0` | Field team must record GPS properly; flag for review |
    | **Missing Coordinates** | No lat/long recorded | Field team must record GPS; flag for review |
    | **Outside Boundary** | GPS outside Metinaro survey area | Verify point; if legitimate, extend `SITE_RADIUS_M` |
    | **Duplicate UUID** | Same submission twice | Delete duplicate in raw data before re-processing |
    | **Species Logic** | Species marked present but 0% | Verify with field notes; correct in raw data |
    | **Geography Mismatch** | `Metinaru` vs `Metinaro` | Auto-corrected if similar; review warnings |
    
    ### Quick Decisions Guide
    
    **For Errors:**
    - Can be auto-corrected? → Let the tool handle it (correction log tab)
    - Is it a data entry typo? → Correct in raw data, re-upload
    - Is it a systemic issue (same error repeated)? → Update the validation rules in code
    
    **For Warnings:**
    - GPS warnings → Usually just flag for field team review
    - Time warnings → Flag as potential data entry issues
    - Duplicate warnings → Investigate; could be legitimate or data entry error
    """)

# Show file info
st.caption(f"Dataset: {uploaded.name} | Records: {total} | Issues: {len(issues)}")
