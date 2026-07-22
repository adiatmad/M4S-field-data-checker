"""
M4S Seagrass QA — Streamlit front end
======================================
Enhanced version with:
- Multi-language support (English, Tetum, Indonesian)
- Advanced species typo detection
- Guided spot-checking workflow
"""

import io
import re
import pandas as pd
import streamlit as st
import plotly.express as px
from datetime import datetime
from rapidfuzz import fuzz

# Import the core QA functions
from m4s_seagrass_qa import (
    load_data as original_load_data,
    standardize as original_standardize,
    validate as original_validate,
    correct as original_correct,
    generate_qa_report as original_generate_qa_report,
    SPECIES_LIST, CANONICAL_ADMIN_POST, CANONICAL_VILLAGE
)

st.set_page_config(page_title="M4S Seagrass QA", layout="wide")
st.title("M4S Seagrass QA — Metinaro")
st.caption("Upload the raw Kobo export (.xlsx). Nothing is saved to a server — "
           "everything happens in this session and outputs are yours to download.")

# ============================================================================
# LANGUAGE MAPPING - UPDATED WITH ACTUAL COLUMN NAMES
# ============================================================================

# Column name mappings for different languages
# Based on actual column names from the exports
COLUMN_MAPPINGS = {
    'English': {
        'start': 'start',
        'end': 'end',
        'collector': 'Collector Name',
        'phone': 'Phone number',
        'date': 'Date and time',
        'admin_post': 'Administration Post',
        'village': 'Village',
        'site_code': 'Local/Site Code',
        'gps_lat': '_Local GPS_latitude',
        'gps_lon': '_Local GPS_longitude',
        'gps_alt': '_Local GPS_altitude',
        'gps_precision': '_Local GPS_precision',
        'transect': 'Transect Number',
        'quadrat': 'Quadrat Number',
        'photo': 'Quadrat Photo',
        'photo_url': 'Quadrat Photo_URL',
        'uuid': '_uuid',
        'submission_time': '_submission_time',
    },
    'Tetum': {
        'start': 'start',
        'end': 'end',
        'collector': 'Naran Koletor',  # From Tetum data
        'phone': 'Nomor Telemovel',    # From Tetum data
        'date': 'Data no Horas',       # From Tetum data
        'admin_post': 'Postu Administrativu',  # From Tetum data
        'village': 'Suku',             # From Tetum data
        'site_code': 'Lokal/Site Kode',  # From Tetum data
        'gps_lat': '_GPS Lokal_latitude',  # From Tetum data
        'gps_lon': '_GPS Lokal_longitude',  # From Tetum data
        'gps_alt': '_GPS Lokal_altitude',  # From Tetum data
        'gps_precision': '_GPS Lokal_precision',  # From Tetum data
        'transect': 'Numeru Tranjektu',  # From Tetum data
        'quadrat': 'Numeru Quadrante',   # From Tetum data
        'photo': 'Foto Quadrante',       # From Tetum data
        'photo_url': 'Foto Quadrante_URL',  # From Tetum data
        'uuid': '_uuid',                 # Same in all versions
        'submission_time': '_submission_time',  # Same in all versions
    },
    'Indonesian': {
        'start': 'start',
        'end': 'end',
        'collector': 'Nama Kolektor',    # From Indonesian data
        'phone': 'Nomor Telepon',        # From Indonesian data
        'date': 'Tabgal dan Waktu',      # From Indonesian data (note: typo in original)
        'admin_post': 'Pos Administratif',  # From Indonesian data
        'village': 'Desa',               # From Indonesian data
        'site_code': 'Kode Lokal/Situs',  # From Indonesian data
        'gps_lat': '_GPS lokal_latitude',  # From Indonesian data
        'gps_lon': '_GPS lokal_longitude',  # From Indonesian data
        'gps_alt': '_GPS lokal_altitude',  # From Indonesian data
        'gps_precision': '_GPS lokal_precision',  # From Indonesian data
        'transect': 'Nomor Tranjekt',    # From Indonesian data
        'quadrat': 'Nomor Quadrant',     # From Indonesian data
        'photo': 'Foto Quadrant',        # From Indonesian data
        'photo_url': 'Foto Quadrant_URL',  # From Indonesian data
        'uuid': '_uuid',                 # Same in all versions
        'submission_time': '_submission_time',  # Same in all versions
    }
}

# ============================================================================
# DETECT LANGUAGE AND MAP COLUMNS
# ============================================================================

def detect_language(df):
    """Detect the language of the dataset based on column names."""
    # Check each language's required columns with more flexibility
    for lang, mapping in COLUMN_MAPPINGS.items():
        # Get the English column names we expect
        required_eng_cols = [
            'collector', 'date', 'admin_post', 'village', 
            'gps_lat', 'gps_lon', 'gps_precision', 'uuid'
        ]
        
        # Get the actual column names for this language
        lang_cols = [mapping[col] for col in required_eng_cols]
        
        # Check how many match
        found = sum(1 for col in lang_cols if col in df.columns)
        
        # Also check for partial matches (sometimes there are slight variations)
        if found < 5:
            # Try case-insensitive matching
            df_cols_lower = [c.lower() for c in df.columns]
            lang_cols_lower = [c.lower() for c in lang_cols]
            found = sum(1 for col in lang_cols_lower if col in df_cols_lower)
        
        # If we found at least 5 of 7, it's likely this language
        if found >= 5:
            return lang
    
    # If no language detected, try to infer from content
    sample_text = ' '.join(df.iloc[:3].astype(str).values.flatten())
    
    tetum_words = ['Numeru', 'Tranjektu', 'Quadrante', 'Suku', 'Postu', 'Koletor']
    if any(word in sample_text for word in tetum_words):
        return 'Tetum'
    
    indo_words = ['Nomor', 'Tranjekt', 'Quadrant', 'Desa', 'Pos', 'Kolektor']
    if any(word in sample_text for word in indo_words):
        return 'Indonesian'
    
    # Default to English
    return 'English'

def find_column_alternatives(df, target_col):
    """Find alternative column names that might match."""
    # Common variations
    variations = {
        'Collector Name': ['Collector Name', 'Naran Koletor', 'Nama Kolektor', 'Koletor', 'Kolektor'],
        'Date and time': ['Date and time', 'Data no Horas', 'Tabgal dan Waktu', 'Data', 'Date'],
        'Administration Post': ['Administration Post', 'Postu Administrativu', 'Pos Administratif', 'Postu', 'Pos'],
        'Village': ['Village', 'Suku', 'Desa'],
        '_Local GPS_latitude': ['_Local GPS_latitude', '_GPS Lokal_latitude', '_GPS lokal_latitude', '_GPS_latitude'],
        '_Local GPS_longitude': ['_Local GPS_longitude', '_GPS Lokal_longitude', '_GPS lokal_longitude', '_GPS_longitude'],
        '_Local GPS_precision': ['_Local GPS_precision', '_GPS Lokal_precision', '_GPS lokal_precision', '_GPS_precision'],
        '_uuid': ['_uuid', 'UUID', 'uuid'],
    }
    
    if target_col in variations:
        for alt in variations[target_col]:
            if alt in df.columns:
                return alt
    
    # Try case-insensitive search
    for col in df.columns:
        if col.lower() == target_col.lower():
            return col
    
    return target_col

def map_columns(df, lang):
    """Rename columns to English equivalents for processing."""
    if lang not in COLUMN_MAPPINGS:
        return df
    
    mapping = COLUMN_MAPPINGS[lang]
    
    # Create rename dictionary
    rename_dict = {}
    for eng_col, lang_col in mapping.items():
        # Skip if they're the same
        if eng_col == lang_col:
            continue
        
        # Check if the language column exists
        if lang_col in df.columns:
            rename_dict[lang_col] = eng_col
        else:
            # Try to find alternative
            alt_col = find_column_alternatives(df, lang_col)
            if alt_col in df.columns and alt_col != eng_col:
                rename_dict[alt_col] = eng_col
    
    # Apply renaming
    if rename_dict:
        df = df.rename(columns=rename_dict)
    
    # Also ensure we have the _uuid column
    if '_uuid' not in df.columns:
        # Try to find it
        uuid_col = find_column_alternatives(df, '_uuid')
        if uuid_col in df.columns and uuid_col != '_uuid':
            df = df.rename(columns={uuid_col: '_uuid'})
    
    return df

# ============================================================================
# ENHANCED LOAD FUNCTION WITH LANGUAGE SUPPORT
# ============================================================================

def load_data_with_language(file):
    """Load data with automatic language detection and column mapping."""
    raw = pd.read_excel(file)
    
    # Show first few columns for debugging
    st.write("**First 5 columns in the file:**")
    st.write(list(raw.columns[:10]))
    
    # Detect language
    lang = detect_language(raw)
    
    # If still English but we see Tetum columns, force Tetum
    if lang == 'English':
        # Check for Tetum column names
        tetum_cols = ['Naran Koletor', 'Data no Horas', 'Postu Administrativu', 'Suku']
        if any(col in raw.columns for col in tetum_cols):
            lang = 'Tetum'
        
        # Check for Indonesian column names
        indo_cols = ['Nama Kolektor', 'Tabgal dan Waktu', 'Pos Administratif', 'Desa']
        if any(col in raw.columns for col in indo_cols):
            lang = 'Indonesian'
    
    st.info(f"🌐 Detected language: {lang}")
    
    # Map columns to English
    df = map_columns(raw, lang)
    
    # Verify required columns exist after mapping
    required = [
        "Collector Name", "Date and time", "Administration Post", 
        "Village", "_Local GPS_latitude", "_Local GPS_longitude", 
        "_Local GPS_precision", "_uuid"
    ]
    
    # Check which columns are missing
    missing = [c for c in required if c not in df.columns]
    
    if missing:
        # Try to map missing columns manually
        for col in missing:
            alt = find_column_alternatives(df, col)
            if alt in df.columns and alt != col:
                df = df.rename(columns={alt: col})
        
        # Check again
        missing = [c for c in required if c not in df.columns]
        
        if missing:
            st.error(f"❌ Missing required columns: {missing}")
            st.write("**Available columns in the file:**")
            st.write(list(df.columns))
            st.stop()
    
    return raw, df, lang

# ============================================================================
# ADVANCED SPECIES TYPO DETECTION
# ============================================================================

def find_species_typos(df, lang='English'):
    """Find potential species typos using fuzzy matching."""
    # Get species columns - handle different languages
    species_keywords = ['Seagrass species', 'du\'ut tasi', 'rumput laut', 'spesies', 'lamun']
    species_cols = []
    
    for col in df.columns:
        # Check if it's a species column
        is_species_col = False
        for keyword in species_keywords:
            if keyword in col:
                is_species_col = True
                break
        
        if is_species_col:
            # Check if it contains a species name
            for sp in SPECIES_LIST:
                if sp in col or sp.replace(' ', '') in col.replace(' ', ''):
                    species_cols.append(col)
                    break
    
    # Also check percent columns for species names
    pct_cols = []
    for col in df.columns:
        if any(sp in col for sp in ['Halophila', 'Halodule', 'Enhalus', 'Thalassia', 
                                     'Cymodocea', 'Syringodium', 'Ruppia', 'Thalassodendron']):
            if ' (%)' in col or 'Persentajen' in col or 'Percent' in col:
                pct_cols.append(col)
    
    # Combine all species-related columns
    all_species_cols = list(set(species_cols + pct_cols))
    
    # Find values that might be typos
    typos = []
    for col in species_cols:
        unique_vals = df[col].dropna().unique()
        for val in unique_vals:
            if isinstance(val, str) and len(val) > 2:
                # Check if it's a species name (or close to one)
                for sp in SPECIES_LIST:
                    # Skip if it's exactly the species name or a 0/1
                    if val.lower() == sp.lower() or val in ['0', '1', 0, 1]:
                        continue
                    # Check similarity
                    score = fuzz.token_sort_ratio(val.lower(), sp.lower())
                    if score > 80:  # Threshold for "likely typo"
                        typos.append({
                            'column': col,
                            'original_value': val,
                            'suspected_correct': sp,
                            'similarity': score
                        })
                        break
    
    # Also check values in text columns that might contain species names
    text_cols = df.select_dtypes(include=['object']).columns
    for col in text_cols:
        if col in all_species_cols:
            continue
        unique_vals = df[col].dropna().unique()
        for val in unique_vals:
            if isinstance(val, str) and len(val) > 3:
                for sp in SPECIES_LIST:
                    if sp.lower() in val.lower() or val.lower() in sp.lower():
                        if val.lower() != sp.lower():
                            score = fuzz.token_sort_ratio(val.lower(), sp.lower())
                            if 70 < score < 100:
                                typos.append({
                                    'column': col,
                                    'original_value': val,
                                    'suspected_correct': sp,
                                    'similarity': score
                                })
    
    # Remove duplicates
    seen = set()
    unique_typos = []
    for t in typos:
        key = (t['original_value'], t['suspected_correct'])
        if key not in seen:
            seen.add(key)
            unique_typos.append(t)
    
    return pd.DataFrame(unique_typos)

# ============================================================================
# ENHANCED SPECIES CORRECTION
# ============================================================================

def correct_species_typos(df, typos_df, corrections):
    """Apply corrections to species typos."""
    df_corrected = df.copy()
    log_entries = []
    
    for _, row in typos_df.iterrows():
        if row['original_value'] in corrections:
            correct_name = corrections[row['original_value']]
            col = row['column']
            
            # Find rows with this typo
            mask = df_corrected[col] == row['original_value']
            if mask.any():
                df_corrected.loc[mask, col] = correct_name
                for idx in df_corrected.index[mask]:
                    log_entries.append({
                        'row_index': idx,
                        'field': col,
                        'before': row['original_value'],
                        'after': correct_name,
                        'rule': 'species_typo_correction'
                    })
    
    return df_corrected, pd.DataFrame(log_entries)

# ============================================================================
# STREAMLIT APP
# ============================================================================

# Initialize session state
if 'reviewed_issues' not in st.session_state:
    st.session_state.reviewed_issues = set()
if 'issue_notes' not in st.session_state:
    st.session_state.issue_notes = {}
if 'review_status' not in st.session_state:
    st.session_state.review_status = {}
if 'lang' not in st.session_state:
    st.session_state.lang = 'English'

uploaded = st.file_uploader("Raw Kobo export (.xlsx)", type=["xlsx"])

if uploaded is None:
    st.info("Upload a file to run the pipeline.")
    st.stop()

# ---- Load data with language detection ----
try:
    raw_df, df, lang = load_data_with_language(uploaded)
    st.session_state.lang = lang
    st.success(f"✅ Successfully loaded {lang} version with {len(df)} records")
except Exception as e:
    st.error(f"Error loading data: {str(e)}")
    st.stop()

# ---- Run the pipeline ----
df = original_standardize(df)
issues = original_validate(df)
clean_df, correction_log = original_correct(df)

# ---- Check for species typos ----
typos_df = find_species_typos(df, lang)

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
        issue_summary = issues.groupby(['category', 'severity']).size().reset_index(name='count')
        issue_pivot = issue_summary.pivot(index='category', columns='severity', values='count').fillna(0)
        issue_pivot['total'] = issue_pivot.sum(axis=1)
        
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
        - **duplicate**: Review for data entry errors
        - **geography**: Verify admin post/village
        - **logic**: Check mandatory fields & logic
        """)
else:
    st.success("🎉 No issues found! Dataset is clean.")

st.divider()

# Step 2: Species Typo Checker (Enhanced)
st.markdown("### Step 2: Check Species Typos")

# Display the species list
with st.expander("📋 Canonical Species List"):
    st.markdown(f"**{len(SPECIES_LIST)} species in the form:**")
    cols = st.columns(3)
    for i, sp in enumerate(SPECIES_LIST):
        cols[i % 3].write(f"- {sp}")

# Show detected typos
if len(typos_df) > 0:
    st.warning(f"⚠️ Found {len(typos_df)} potential species typos!")
    
    # Group by similarity for better visualization
    col1, col2 = st.columns([2, 1])
    with col1:
        st.dataframe(
            typos_df.sort_values('similarity', ascending=False),
            use_container_width=True,
            column_config={
                "column": "Column",
                "original_value": "Current Value",
                "suspected_correct": "Suspected Correct",
                "similarity": st.column_config.ProgressColumn(
                    "Similarity",
                    format="%d%%",
                    min_value=70,
                    max_value=100,
                )
            }
        )
    
    with col2:
        st.markdown("""
        **Common Typos to Watch For:**
        - `Thhalassia` → `Thalassia` (double h)
        - `Halophilaminor` → `Halophila minor` (no space)
        - `Enhalus acoriodes` → `Enhalus acoroides`
        - `Syringodium isoetifolium` → `Syringodium isoetifolium`
        - `Cymodocea serrulata` → `Cymodocea serrulata`
        """)
    
    # Allow user to correct typos
    st.markdown("#### Correct Species Typos")
    st.markdown("""
    Select which typos to correct. The corrections will be applied to the clean dataset.
    """)
    
    # Create correction options
    corrections = {}
    for _, row in typos_df.iterrows():
        col1, col2, col3 = st.columns([3, 2, 1])
        with col1:
            st.write(f"`{row['original_value']}`")
        with col2:
            corrected = st.text_input(
                "Correct to:",
                value=row['suspected_correct'],
                key=f"correction_{row['original_value']}_{row['column']}"
            )
        with col3:
            apply = st.checkbox(
                "Apply",
                key=f"apply_{row['original_value']}_{row['column']}"
            )
        if apply and corrected:
            corrections[row['original_value']] = corrected
    
    if corrections:
        if st.button("✅ Apply Species Corrections"):
            # Apply corrections to a copy of the clean dataset
            clean_df_corrected, species_correction_log = correct_species_typos(
                clean_df, typos_df, corrections
            )
            
            # Update the clean dataset
            clean_df = clean_df_corrected
            
            # Combine correction logs
            if len(species_correction_log) > 0:
                correction_log = pd.concat([correction_log, species_correction_log], ignore_index=True)
            
            st.success(f"✅ Applied {len(corrections)} species corrections!")
            st.info("The clean dataset has been updated. Download it from the 'Clean dataset' tab.")
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
status_counts = pd.DataFrame.from_dict(
    st.session_state.review_status, orient='index', columns=['status']
)['status'].value_counts() if st.session_state.review_status else pd.Series()

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
    report_lines = []
    report_lines.append(f"# M4S Seagrass Spot-Check Report")
    report_lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    report_lines.append(f"Language: {lang}")
    report_lines.append(f"Total records reviewed: {len(df)}")
    report_lines.append(f"Issues found: {len(issues)}")
    report_lines.append("")
    
    # Summary of issues by category
    report_lines.append("## Issue Summary")
    issue_summary = issues.groupby(['category', 'severity']).size().reset_index(name='count')
    report_lines.append(issue_summary.to_markdown())
    report_lines.append("")
    
    # Species typos found
    if len(typos_df) > 0:
        report_lines.append("## Species Typos Detected")
        report_lines.append(typos_df.to_markdown())
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
        file_name=f"spot_check_report_{datetime.now().strftime('%Y%m%d')}_{lang}.md",
        mime="text/markdown"
    )
    
    st.success("Report generated successfully!")

st.divider()

# ---- Original tabs (QA report, Issue list, etc.) ----
tab_report, tab_issues, tab_corrections, tab_clean = st.tabs(
    ["QA report", "Issue list", "Correction log", "Clean dataset"]
)

with tab_report:
    import tempfile, pathlib
    with tempfile.NamedTemporaryFile(suffix=".md", delete=False) as tmp:
        original_generate_qa_report(clean_df, issues, correction_log, tmp.name)
        report_text = pathlib.Path(tmp.name).read_text(encoding="utf-8")
    st.markdown(report_text)
    st.download_button("Download qa_report.md", report_text,
                        file_name=f"qa_report_{lang}.md")

with tab_issues:
    st.dataframe(issues, use_container_width=True)
    st.download_button("Download qa_issues.csv", issues.to_csv(index=False),
                        file_name=f"qa_issues_{lang}.csv")

with tab_corrections:
    st.dataframe(correction_log, use_container_width=True)
    st.download_button("Download correction_log.csv", correction_log.to_csv(index=False),
                        file_name=f"correction_log_{lang}.csv")

with tab_clean:
    st.dataframe(clean_df, use_container_width=True)
    st.download_button("Download clean_dataset.csv", clean_df.to_csv(index=False),
                        file_name=f"clean_dataset_{lang}.csv")
    st.download_button("Download raw_preserved.csv", raw_df.to_csv(index=False),
                        file_name=f"raw_preserved_{lang}.csv")

# ---- Footer ----
st.divider()
with st.expander("📖 Quick Reference: Common Errors & How to Fix Them"):
    st.markdown("""
    ### Common Errors and Their Fixes
    
    | Error Type | Example | How to Fix |
    |------------|---------|------------|
    | **Species Typos** | `Thhalassia hemprichii`, `Halophilaminor` | Use the species typo checker above to correct |
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

st.caption(f"Dataset: {uploaded.name} | Language: {lang} | Records: {total} | Issues: {len(issues)}")
