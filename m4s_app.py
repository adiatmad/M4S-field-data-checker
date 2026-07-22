"""
M4S Seagrass QA — Streamlit front end
======================================
Enhanced version with multi-language support (English, Tetum, Indonesian)
and advanced species typo detection.
"""

import io
import re
import pandas as pd
import streamlit as st
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
st.caption("Upload the raw Kobo export (.xlsx). Works with English, Tetum, and Indonesian versions.")

# ============================================================================
# LANGUAGE MAPPING - BASED ON ACTUAL FILE ANALYSIS
# ============================================================================

COLUMN_MAPPINGS = {
    'English': {
        'collector': 'Collector Name',
        'date': 'Date and time',
        'admin_post': 'Administration Post',
        'village': 'Village',
        'gps_lat': '_Local GPS_latitude',
        'gps_lon': '_Local GPS_longitude',
        'gps_alt': '_Local GPS_altitude',
        'gps_precision': '_Local GPS_precision',
        'transect': 'Transect Number',
        'quadrat': 'Quadrat Number',
        'uuid': '_uuid',
    },
    'Tetum': {
        'collector': 'Naran Koletor',
        'date': 'Data no Horas',
        'admin_post': 'Postu Administrativu',
        'village': 'Suku',
        'gps_lat': '_GPS Lokal_latitude',
        'gps_lon': '_GPS Lokal_longitude',
        'gps_alt': '_GPS Lokal_altitude',
        'gps_precision': '_GPS Lokal_precision',
        'transect': 'Numeru Tranjektu',
        'quadrat': 'Numeru Quadrante',
        'uuid': '_uuid',
    },
    'Indonesian': {
        'collector': 'Nama Kolektor',
        'date': 'Tabgal dan Waktu',
        'admin_post': 'Pos Administratif',
        'village': 'Desa',
        'gps_lat': '_GPS lokal_latitude',
        'gps_lon': '_GPS lokal_longitude',
        'gps_alt': '_GPS lokal_altitude',
        'gps_precision': '_GPS lokal_precision',
        'transect': 'Nomor Tranjekt',
        'quadrat': 'Nomor Quadrant',
        'uuid': '_uuid',
    }
}

# ============================================================================
# LANGUAGE DETECTION AND MAPPING
# ============================================================================

def detect_language(df):
    """Detect the language of the dataset based on column names."""
    # Check each language's required columns
    for lang, mapping in COLUMN_MAPPINGS.items():
        # Key columns that must exist
        key_cols = ['collector', 'date', 'admin_post', 'village', 'gps_lat']
        lang_cols = [mapping[col] for col in key_cols]
        
        # Count how many match
        found = sum(1 for col in lang_cols if col in df.columns)
        
        # If we found at least 4 of 5, it's this language
        if found >= 4:
            return lang
    
    # If no exact match, try case-insensitive
    df_cols_lower = [c.lower() for c in df.columns]
    for lang, mapping in COLUMN_MAPPINGS.items():
        key_cols = ['collector', 'date', 'admin_post', 'village', 'gps_lat']
        lang_cols = [mapping[col].lower() for col in key_cols]
        found = sum(1 for col in lang_cols if col in df_cols_lower)
        if found >= 4:
            return lang
    
    return 'English'  # Default

def map_columns(df, lang):
    """Rename columns to English equivalents for processing."""
    if lang not in COLUMN_MAPPINGS:
        return df
    
    mapping = COLUMN_MAPPINGS[lang]
    rename_dict = {}
    
    for eng_col, lang_col in mapping.items():
        if eng_col == lang_col:
            continue
        
        # Check exact match
        if lang_col in df.columns:
            rename_dict[lang_col] = eng_col
        else:
            # Try case-insensitive match
            for col in df.columns:
                if col.lower() == lang_col.lower():
                    rename_dict[col] = eng_col
                    break
    
    if rename_dict:
        df = df.rename(columns=rename_dict)
    
    return df

# ============================================================================
# LOAD DATA WITH LANGUAGE SUPPORT
# ============================================================================

def load_data_with_language(file):
    """Load data with automatic language detection and column mapping."""
    raw = pd.read_excel(file)
    
    # Detect language
    lang = detect_language(raw)
    
    # Map columns to English
    df = map_columns(raw, lang)
    
    # Verify required columns exist
    required = [
        "Collector Name", "Date and time", "Administration Post", 
        "Village", "_Local GPS_latitude", "_Local GPS_longitude", 
        "_Local GPS_precision", "_uuid"
    ]
    
    missing = [c for c in required if c not in df.columns]
    
    if missing:
        # Try to find alternatives for missing columns
        for col in missing:
            # Try to find similar column names
            for df_col in df.columns:
                if col.lower() in df_col.lower() or df_col.lower() in col.lower():
                    if df_col != col:
                        df = df.rename(columns={df_col: col})
                        break
        
        # Check again
        missing = [c for c in required if c not in df.columns]
        
        if missing:
            st.error(f"❌ Missing required columns: {missing}")
            st.write("**Available columns in file:**")
            st.write(list(df.columns))
            st.stop()
    
    return raw, df, lang

# ============================================================================
# SPECIES TYPO DETECTION
# ============================================================================

def find_species_typos(df):
    """Find potential species typos using fuzzy matching."""
    typos = []
    
    # Find species-related columns
    species_cols = []
    for col in df.columns:
        for sp in SPECIES_LIST:
            if sp in col or sp.replace(' ', '') in col.replace(' ', ''):
                if any(keyword in col for keyword in ['Seagrass', 'du\'ut', 'rumput', 'spesies']):
                    species_cols.append(col)
                    break
    
    # Check values in these columns
    for col in species_cols:
        unique_vals = df[col].dropna().unique()
        for val in unique_vals:
            if isinstance(val, str) and len(val) > 2 and val not in ['0', '1']:
                for sp in SPECIES_LIST:
                    if val.lower() == sp.lower():
                        continue
                    score = fuzz.token_sort_ratio(val.lower(), sp.lower())
                    if score > 80:
                        typos.append({
                            'column': col,
                            'original_value': val,
                            'suspected_correct': sp,
                            'similarity': score
                        })
                        break
    
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
# APPLY SPECIES CORRECTIONS
# ============================================================================

def correct_species_typos(df, corrections):
    """Apply corrections to species typos."""
    df_corrected = df.copy()
    log_entries = []
    
    for original, corrected in corrections.items():
        for col in df.columns:
            mask = df_corrected[col] == original
            if mask.any():
                df_corrected.loc[mask, col] = corrected
                for idx in df_corrected.index[mask]:
                    log_entries.append({
                        'row_index': idx,
                        'field': col,
                        'before': original,
                        'after': corrected,
                        'rule': 'species_typo_correction'
                    })
    
    return df_corrected, pd.DataFrame(log_entries)

# ============================================================================
# STREAMLIT APP
# ============================================================================

# Initialize session state
if 'review_status' not in st.session_state:
    st.session_state.review_status = {}
if 'issue_notes' not in st.session_state:
    st.session_state.issue_notes = {}
if 'lang' not in st.session_state:
    st.session_state.lang = 'English'

uploaded = st.file_uploader("Raw Kobo export (.xlsx)", type=["xlsx"])

if uploaded is None:
    st.info("Upload a file to run the pipeline.")
    st.stop()

# ---- Load data ----
try:
    raw_df, df, lang = load_data_with_language(uploaded)
    st.session_state.lang = lang
    st.success(f"✅ Loaded {lang} version with {len(df)} records")
except Exception as e:
    st.error(f"Error: {str(e)}")
    st.stop()

# ---- Run QA pipeline ----
df = original_standardize(df)
issues = original_validate(df)
clean_df, correction_log = original_correct(df)

# ---- Find species typos ----
typos_df = find_species_typos(df)

# ---- Summary metrics ----
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

# ---- Language info ----
st.info(f"🌐 Working with **{lang}** version of the survey")

# ---- Species Typo Checker ----
st.subheader("🔍 Species Typo Checker")

if len(typos_df) > 0:
    st.warning(f"⚠️ Found {len(typos_df)} potential species typos!")
    st.dataframe(typos_df, use_container_width=True)
    
    # Allow corrections
    st.markdown("#### Correct Typos")
    corrections = {}
    for _, row in typos_df.iterrows():
        col1, col2, col3 = st.columns([2, 2, 1])
        with col1:
            st.write(f"`{row['original_value']}`")
        with col2:
            corrected = st.text_input(
                "Correct to:",
                value=row['suspected_correct'],
                key=f"corr_{row['original_value']}"
            )
        with col3:
            apply = st.checkbox("Apply", key=f"apply_{row['original_value']}")
        if apply and corrected:
            corrections[row['original_value']] = corrected
    
    if corrections and st.button("✅ Apply Corrections"):
        clean_df, species_log = correct_species_typos(clean_df, corrections)
        if len(species_log) > 0:
            correction_log = pd.concat([correction_log, species_log], ignore_index=True)
        st.success(f"✅ Applied {len(corrections)} corrections!")
else:
    st.success("✅ No species typos detected")

st.divider()

# ---- Issue Review ----
st.subheader("📋 Issue Review")

if len(issues) > 0:
    # Filters
    col1, col2 = st.columns(2)
    with col1:
        filter_cat = st.multiselect(
            "Category",
            options=issues['category'].unique(),
            default=issues['category'].unique()
        )
    with col2:
        filter_sev = st.multiselect(
            "Severity",
            options=['error', 'warning'],
            default=['error', 'warning']
        )
    
    filtered = issues[
        (issues['category'].isin(filter_cat)) &
        (issues['severity'].isin(filter_sev))
    ]
    
    st.write(f"Showing {len(filtered)} issues")
    
    for _, row in filtered.iterrows():
        key = f"{row.row_index}_{row.category}"
        with st.expander(f"Row {row.row_index} | {row.category} | {row.severity.upper()}"):
            st.markdown(f"**Field:** `{row['field']}`")
            st.markdown(f"**Message:** {row['message']}")
            
            # Review status
            if key not in st.session_state.review_status:
                st.session_state.review_status[key] = "Unreviewed"
            
            status = st.selectbox(
                "Status",
                ["Unreviewed", "Checked OK", "Needs Correction", "Needs Field Review"],
                index=["Unreviewed", "Checked OK", "Needs Correction", "Needs Field Review"].index(
                    st.session_state.review_status.get(key, "Unreviewed")
                ),
                key=f"status_{key}"
            )
            st.session_state.review_status[key] = status
            
            # Notes
            note_key = f"note_{key}"
            note = st.text_area(
                "Notes",
                value=st.session_state.issue_notes.get(note_key, ""),
                key=f"note_{key}"
            )
            st.session_state.issue_notes[note_key] = note
    
    # Review summary
    st.markdown("### Review Progress")
    status_counts = pd.Series(st.session_state.review_status).value_counts()
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("✅ Checked OK", status_counts.get("Checked OK", 0))
    col2.metric("⚠️ Needs Correction", status_counts.get("Needs Correction", 0))
    col3.metric("📋 Needs Field Review", status_counts.get("Needs Field Review", 0))
    col4.metric("⏳ Unreviewed", status_counts.get("Unreviewed", 0))

st.divider()

# ---- Export tabs ----
tab_report, tab_issues, tab_corrections, tab_clean = st.tabs(
    ["QA Report", "Issue List", "Correction Log", "Clean Dataset"]
)

with tab_report:
    import tempfile, pathlib
    with tempfile.NamedTemporaryFile(suffix=".md", delete=False) as tmp:
        original_generate_qa_report(clean_df, issues, correction_log, tmp.name)
        report_text = pathlib.Path(tmp.name).read_text(encoding="utf-8")
    st.markdown(report_text)
    st.download_button("Download Report", report_text, file_name=f"qa_report_{lang}.md")

with tab_issues:
    st.dataframe(issues, use_container_width=True)
    st.download_button("Download Issues", issues.to_csv(index=False), file_name=f"qa_issues_{lang}.csv")

with tab_corrections:
    st.dataframe(correction_log, use_container_width=True)
    st.download_button("Download Corrections", correction_log.to_csv(index=False), 
                      file_name=f"correction_log_{lang}.csv")

with tab_clean:
    st.dataframe(clean_df, use_container_width=True)
    st.download_button("Download Clean Data", clean_df.to_csv(index=False), 
                      file_name=f"clean_dataset_{lang}.csv")
    st.download_button("Download Raw Data", raw_df.to_csv(index=False), 
                      file_name=f"raw_preserved_{lang}.csv")

st.caption(f"📁 {uploaded.name} | Language: {lang} | Records: {total} | Issues: {len(issues)}")
