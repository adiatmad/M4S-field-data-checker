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
import tempfile
import pathlib

from m4s_seagrass_qa import (
    load_data, standardize, validate, correct, generate_qa_report,
    SPECIES_LIST, CANONICAL_ADMIN_POST, CANONICAL_VILLAGE
)

st.set_page_config(page_title="M4S Seagrass QA", layout="wide")
st.title("🌿 M4S Seagrass QA — Metinaro")
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
    st.info("📤 Upload a file to run the pipeline.")
    st.stop()

# ---- run the pipeline (same stages as the CLI version) ----
with st.spinner("Running QA pipeline..."):
    try:
        raw_df, df = load_data(uploaded)
    except ValueError as e:
        st.error(f"❌ Error loading data: {str(e)}")
        st.stop()

    df = standardize(df)
    issues = validate(df)
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

# ---- GUIDED SPOT-CHECKING WORKFLOW ----
st.subheader("🔍 Step-by-Step Spot-Checking Workflow")

# ============================================
# STEP 1: Issue Summary
# ============================================
st.markdown("### Step 1: 📋 Understand Your Data Quality")

if len(issues) == 0:
    st.success("🎉 No issues found! Dataset is clean and ready for analysis.")
    st.balloons()
else:
    # Category summary
    col1, col2 = st.columns([2, 1])
    with col1:
        issue_summary = issues.groupby(['category', 'severity']).size().reset_index(name='count')
        issue_pivot = issue_summary.pivot(index='category', columns='severity', values='count').fillna(0)
        issue_pivot['total'] = issue_pivot.sum(axis=1)
        issue_pivot = issue_pivot.sort_values('total', ascending=False)
        
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
        st.info("""
        **Quick Reference:**
        - **gps**: Check precision & location
        - **species**: Verify species names & logic
        - **species_typo**: Misspelled species names
        - **duplicate**: Review for data entry errors
        - **geography**: Verify admin post/village
        - **logic**: Check mandatory fields & logic
        """)

st.divider()

# ============================================
# STEP 2: Species Typo Checker
# ============================================
st.markdown("### Step 2: 🧬 Check Species Typos")
st.markdown(f"**Canonical species list ({len(SPECIES_LIST)} species):**")
st.markdown(f"`{', '.join(SPECIES_LIST)}`")

# Check column headers for typos
species_presence_cols = [col for col in df.columns if col.startswith("Seagrass species present in the Quadrat/")]

header_typos = []
for col in species_presence_cols:
    species_name = col.split("/")[-1]
    if species_name not in SPECIES_LIST:
        from rapidfuzz import fuzz
        best_match = None
        best_score = 0
        for canonical in SPECIES_LIST:
            score = max(
                fuzz.token_sort_ratio(species_name.lower(), canonical.lower()),
                fuzz.WRatio(species_name.lower(), canonical.lower())
            )
            if score > best_score:
                best_score = score
                best_match = canonical
        
        if best_score >= 80:
            header_typos.append({
                "Found Column": species_name,
                "Suggested Correction": best_match,
                "Confidence": f"{best_score}%",
                "Records with this species": int(df[col].sum())
            })
        else:
            header_typos.append({
                "Found Column": species_name,
                "Suggested Correction": "⚠️ UNKNOWN - Add to SPECIES_LIST",
                "Confidence": f"{best_score}%",
                "Records with this species": int(df[col].sum())
            })

# Check data values for typos
data_typos = []
if "Seagrass species present in the Quadrat" in df.columns:
    for i, r in df.iterrows():
        val = r.get("Seagrass species present in the Quadrat")
        if pd.isna(val) or val == "":
            continue
        # Split by common separators
        parts = []
        for sep in [",", "  ", " "]:
            if sep in str(val):
                parts = [p.strip() for p in str(val).split(sep) if p.strip()]
                break
        if not parts:
            parts = [str(val).strip()]
        
        for part in parts:
            if part in ["1", "0", "Yes", "No"]:
                continue
            if part not in SPECIES_LIST and part not in [t["Found Column"] for t in header_typos]:
                from rapidfuzz import fuzz
                best_match = None
                best_score = 0
                for canonical in SPECIES_LIST:
                    score = max(
                        fuzz.token_sort_ratio(part.lower(), canonical.lower()),
                        fuzz.WRatio(part.lower(), canonical.lower())
                    )
                    if score > best_score:
                        best_score = score
                        best_match = canonical
                
                if best_score >= 80:
                    data_typos.append({
                        "Row": i,
                        "Found": part,
                        "Suggested Correction": best_match,
                        "Confidence": f"{best_score}%"
                    })

# Combine results
all_typos = []
if header_typos:
    for t in header_typos:
        all_typos.append({
            "Type": "Column Header",
            "Found": t["Found Column"],
            "Suggested Correction": t["Suggested Correction"],
            "Confidence": t["Confidence"],
            "Records Affected": t["Records with this species"]
        })

if data_typos:
    # Deduplicate data typos
    seen = set()
    for t in data_typos:
        key = t["Found"]
        if key not in seen:
            seen.add(key)
            all_typos.append({
                "Type": "Data Value",
                "Found": t["Found"],
                "Suggested Correction": t["Suggested Correction"],
                "Confidence": t["Confidence"],
                "Records Affected": sum(1 for dt in data_typos if dt["Found"] == key)
            })

if all_typos:
    st.error(f"⚠️ Found {len(all_typos)} potential species typos!")
    typos_df = pd.DataFrame(all_typos)
    st.dataframe(typos_df, use_container_width=True)
    
    st.markdown("""
    **How to Fix:**
    1. **Column Header Typos**: Open the raw Excel file, find the column with the typo, rename it to the correct species name, save and re-upload.
    2. **Data Value Typos**: Open the raw Excel file, find the cells with the typo, correct the spelling, save and re-upload.
    3. **Common typos to check for**:
       - `Thhalassia hemprichii` → `Thalassia hemprichii`
       - `Thhalassia` → `Thalassia`
       - `Halophilaminor` → `Halophila minor`
       - `Halodulepinifolia` → `Halodule pinifolia`
    """)
    
    # Download correction template
    csv = typos_df.to_csv(index=False)
    st.download_button(
        "📥 Download species typo list for correction",
        csv,
        file_name=f"species_typos_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
    )
else:
    st.success("✅ No species typos detected! All species names match the canonical list.")

st.divider()

# ============================================
# STEP 3: Interactive Issue Review
# ============================================
st.markdown("### Step 3: 🔎 Interactive Issue Review")
st.markdown("""
Review each issue systematically. Use filters to focus on specific problems.
Track your review progress and add notes for documentation.
""")

# Create filters
col1, col2, col3 = st.columns(3)
with col1:
    filter_category = st.multiselect(
        "Filter by Category",
        options=sorted(issues['category'].unique()),
        default=sorted(issues['category'].unique())
    )
with col2:
    filter_severity = st.multiselect(
        "Filter by Severity",
        options=['error', 'warning'],
        default=['error', 'warning']
    )
with col3:
    filter_row = st.number_input("Jump to Row (optional)", min_value=0, max_value=len(df)-1, value=None, step=1)

# Apply filters
filtered_issues = issues[
    (issues['category'].isin(filter_category)) &
    (issues['severity'].isin(filter_severity))
]

if filter_row is not None:
    filtered_issues = filtered_issues[filtered_issues['row_index'] == filter_row]

# Add progress tracking
if len(filtered_issues) > 0:
    st.write(f"Showing **{len(filtered_issues)}** issues out of **{len(issues)}** total")
    
    # Progress bar
    reviewed = sum(1 for k in st.session_state.review_status if st.session_state.review_status[k] != "Unreviewed")
    if len(filtered_issues) > 0:
        progress = reviewed / len(filtered_issues) if len(filtered_issues) > 0 else 0
        st.progress(progress, text=f"Review progress: {reviewed}/{len(filtered_issues)} issues reviewed")
    
    # Display issues
    for idx, row in filtered_issues.iterrows():
        key = f"{row['row_index']}_{row['category']}_{row['field']}"
        
        with st.expander(f"Row {row['row_index']} | {row['category']} | {row['severity'].upper()} | {row['field']}"):
            col1, col2 = st.columns([3, 1])
            with col1:
                st.markdown(f"**Message:** {row['message']}")
                
                # Show raw data context
                if row['row_index'] in df.index:
                    st.caption("**Context (surrounding data):**")
                    context_start = max(0, row['row_index'] - 2)
                    context_end = min(len(df), row['row_index'] + 3)
                    context_cols = ['_uuid', 'Collector Name', 'Transect Number', 'Quadrat Number']
                    if row['category'] == 'gps':
                        context_cols.extend(['_Local GPS_latitude', '_Local GPS_longitude', '_Local GPS_precision'])
                    context_df = df.iloc[context_start:context_end][context_cols]
                    st.dataframe(context_df, use_container_width=True)
            
            with col2:
                # Review status
                if key not in st.session_state.review_status:
                    st.session_state.review_status[key] = "Unreviewed"
                
                status = st.selectbox(
                    "Status",
                    options=["Unreviewed", "Checked OK", "Needs Correction", "Needs Field Team Review"],
                    index=["Unreviewed", "Checked OK", "Needs Correction", "Needs Field Team Review"].index(
                        st.session_state.review_status.get(key, "Unreviewed")
                    ),
                    key=f"status_{key}"
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
                    placeholder="e.g., 'Confirmed typo - need to correct in raw data'",
                    height=68
                )
                st.session_state.issue_notes[note_key] = note

    # Review summary
    st.markdown("### 📊 Review Progress Summary")
    status_counts = pd.DataFrame.from_dict(
        st.session_state.review_status, orient='index', columns=['status']
    )['status'].value_counts()
    
    cols = st.columns(4)
    cols[0].metric("✅ Checked OK", status_counts.get("Checked OK", 0))
    cols[1].metric("⚠️ Needs Correction", status_counts.get("Needs Correction", 0))
    cols[2].metric("📋 Needs Field Review", status_counts.get("Needs Field Team Review", 0))
    cols[3].metric("⏳ Unreviewed", status_counts.get("Unreviewed", 0))
else:
    st.info("No issues match the current filters.")

st.divider()

# ============================================
# STEP 4: Generate Spot-Check Report
# ============================================
st.markdown("### Step 4: 📄 Generate Spot-Check Report")
st.markdown("""
Export a summary of your spot-checking session including:
- All reviewed issues with your notes
- Summary of what needs to be corrected
- Recommended actions for the field team
""")

if st.button("📊 Generate Spot-Check Summary Report", use_container_width=True):
    report_lines = []
    report_lines.append(f"# M4S Seagrass Spot-Check Report")
    report_lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    report_lines.append(f"Dataset: {uploaded.name}")
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
    
    # Species typos found
    if all_typos:
        report_lines.append("## Species Typos Found")
        for t in all_typos:
            report_lines.append(f"- **{t['Found']}** → should be **{t['Suggested Correction']}** (Confidence: {t['Confidence']})")
        report_lines.append("")
    
    # Detailed review log
    report_lines.append("## Detailed Review Log")
    report_lines.append("| Row | Category | Severity | Field | Message | Status | Notes |")
    report_lines.append("|-----|----------|----------|-------|---------|--------|-------|")
    
    for _, row in issues.iterrows():
        key = f"{row['row_index']}_{row['category']}_{row['field']}"
        status = st.session_state.review_status.get(key, "Unreviewed")
        note_key = f"note_{key}"
        note = st.session_state.issue_notes.get(note_key, "")[:50]
        report_lines.append(
            f"| {row['row_index']} | {row['category']} | {row['severity']} | "
            f"{row['field']} | {row['message'][:50]}... | {status} | {note} |"
        )
    
    report_text = "\n".join(report_lines)
    
    st.download_button(
        "📥 Download Spot-Check Report",
        report_text,
        file_name=f"spot_check_report_{datetime.now().strftime('%Y%m%d_%H%M')}.md",
        mime="text/markdown"
    )
    
    st.success("✅ Report generated successfully!")

st.divider()

# ============================================
# ORIGINAL TABS (QA report, Issue list, etc.)
# ============================================
tab_report, tab_issues, tab_corrections, tab_clean = st.tabs(
    ["📋 QA Report", "📊 Issue List", "🔧 Correction Log", "✨ Clean Dataset"]
)

with tab_report:
    # Build the QA report
    with tempfile.NamedTemporaryFile(suffix=".md", delete=False) as tmp:
        generate_qa_report(clean_df, issues, correction_log, tmp.name)
        report_text = pathlib.Path(tmp.name).read_text(encoding="utf-8")
    st.markdown(report_text)
    st.download_button("📥 Download qa_report.md", report_text, file_name="qa_report.md")

with tab_issues:
    st.dataframe(issues, use_container_width=True)
    st.download_button(
        "📥 Download qa_issues.csv",
        issues.to_csv(index=False),
        file_name="qa_issues.csv"
    )

with tab_corrections:
    st.dataframe(correction_log, use_container_width=True)
    st.download_button(
        "📥 Download correction_log.csv",
        correction_log.to_csv(index=False),
        file_name="correction_log.csv"
    )

with tab_clean:
    st.dataframe(clean_df, use_container_width=True)
    col1, col2 = st.columns(2)
    with col1:
        st.download_button(
            "📥 Download clean_dataset.csv",
            clean_df.to_csv(index=False),
            file_name="clean_dataset.csv"
        )
    with col2:
        st.download_button(
            "📥 Download raw_preserved.csv",
            raw_df.to_csv(index=False),
            file_name="raw_preserved.csv"
        )

# ============================================
# QUICK REFERENCE
# ============================================
with st.expander("📖 Quick Reference: Common Errors & How to Fix Them"):
    st.markdown("""
    ### Common Errors and Their Fixes
    
    | Error Type | Example | How to Fix |
    |------------|---------|------------|
    | **Species Typos** | `Thhalassia`, `Halophilaminor` | Correct in raw XLSX and re-upload, or update `SPECIES_LIST` in code |
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

st.caption(f"📁 Dataset: {uploaded.name} | 📊 Records: {total} | ⚠️ Issues: {len(issues)} | 🔧 Corrections: {len(correction_log)}")
