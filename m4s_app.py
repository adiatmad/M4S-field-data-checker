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
# LANGUAGE MAPPING - COMPLETE AND ACCURATE
# ============================================================================

# Complete column mappings for all languages
# These are based on the ACTUAL column names from your exported files

# First, define the English column names we want to map to
ENGLISH_COLUMNS = {
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
    'start': 'start',
    'end': 'end',
}

# Now define the mapping for each language
# IMPORTANT: These must match EXACTLY what's in the Excel file
LANGUAGE_MAPPINGS = {
    'English': {
        # English uses the same column names as ENGLISH_COLUMNS
        # So we just use the English column names directly
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
        'start': 'start',
        'end': 'end',
    },
    'Tetum': {
        'collector': 'Naran Koletor',
        'phone': 'Nomor Telemovel',
        'date': 'Data no Horas',
        'admin_post': 'Postu Administrativu',  # NOTE: ends with 'u', not 'f'
        'village': 'Suku',
        'site_code': 'Lokal/Site Kode',
        'gps_lat': '_GPS Lokal_latitude',
        'gps_lon': '_GPS Lokal_longitude',
        'gps_alt': '_GPS Lokal_altitude',
        'gps_precision': '_GPS Lokal_precision',
        'transect': 'Numeru Tranjektu',
        'quadrat': 'Numeru Quadrante',
        'photo': 'Foto Quadrante',
        'photo_url': 'Foto Quadrante_URL',
        'uuid': '_uuid',
        'submission_time': '_submission_time',
        'start': 'start',
        'end': 'end',
    },
    'Indonesian': {
        'collector': 'Nama Kolektor',
        'phone': 'Nomor Telepon',
        'date': 'Tabgal dan Waktu',
        'admin_post': 'Pos Administratif',
        'village': 'Desa',
        'site_code': 'Kode Lokal/Situs',
        'gps_lat': '_GPS lokal_latitude',
        'gps_lon': '_GPS lokal_longitude',
        'gps_alt': '_GPS lokal_altitude',
        'gps_precision': '_GPS lokal_precision',
        'transect': 'Nomor Tranjekt',
        'quadrat': 'Nomor Quadrant',
        'photo': 'Foto Quadrant',
        'photo_url': 'Foto Quadrant_URL',
        'uuid': '_uuid',
        'submission_time': '_submission_time',
        'start': 'start',
        'end': 'end',
    }
}

# ============================================================================
# LANGUAGE DETECTION
# ============================================================================

def detect_language(df):
    """
    Detect which language version this is by checking column names.
    Returns: 'English', 'Tetum', or 'Indonesian'
    """
    # Check for Tetum columns (using the actual column names)
    tetum_indicators = ['Naran Koletor', 'Data no Horas', 'Postu Administrativu', 'Suku']
    tetum_score = sum(1 for col in tetum_indicators if col in df.columns)
    
    # Check for Indonesian columns
    indo_indicators = ['Nama Kolektor', 'Tabgal dan Waktu', 'Pos Administratif', 'Desa']
    indo_score = sum(1 for col in indo_indicators if col in df.columns)
    
    # Check for English columns
    eng_indicators = ['Collector Name', 'Date and time', 'Administration Post', 'Village']
    eng_score = sum(1 for col in eng_indicators if col in df.columns)
    
    # Return the language with the highest score
    scores = {
        'English': eng_score,
        'Tetum': tetum_score,
        'Indonesian': indo_score
    }
    
    # If we found at least 2 indicators, return the best match
    best_lang = max(scores, key=scores.get)
    if scores[best_lang] >= 2:
        return best_lang
    
    # If no clear match, check for specific columns
    if '_GPS Lokal_latitude' in df.columns:
        return 'Tetum'
    if '_GPS lokal_latitude' in df.columns:
        return 'Indonesian'
    
    # Default to English
    return 'English'

# ============================================================================
# COLUMN MAPPING
# ============================================================================

def map_columns_to_english(df, lang):
    """
    Rename columns from the detected language to English equivalents.
    """
    if lang not in LANGUAGE_MAPPINGS:
        return df
    
    mapping = LANGUAGE_MAPPINGS[lang]
    rename_dict = {}
    
    # For each English column, find its language-specific counterpart
    for eng_key, lang_col in mapping.items():
        # Get the English column name
        eng_col = ENGLISH_COLUMNS[eng_key]
        
        # Skip if they're the same
        if eng_col == lang_col:
            continue
        
        # Check if the language column exists
        if lang_col in df.columns:
            rename_dict[lang_col] = eng_col
        else:
            # Try case-insensitive match
            for col in df.columns:
                if col.lower() == lang_col.lower():
                    rename_dict[col] = eng_col
                    break
    
    # Apply renaming
    if rename_dict:
        df = df.rename(columns=rename_dict)
    
    return df

# ============================================================================
# LOAD DATA WITH LANGUAGE SUPPORT
# ============================================================================

def load_data_with_language(file):
    """
    Load the Excel file, detect language, and map columns to English.
    """
    raw = pd.read_excel(file)
    
    # Show debug info
    st.write("**📋 First 10 columns in file:**")
    st.write(list(raw.columns[:10]))
    
    # Detect language
    lang = detect_language(raw)
    st.info(f"🌐 Detected language: **{lang}**")
    
    # Map columns to English
    df = map_columns_to_english(raw, lang)
    
    # Show what was mapped
    st.write("**📋 Columns after mapping (first 10):**")
    st.write(list(df.columns[:10]))
    
    # Verify required columns exist
    required = [
        "Collector Name", 
        "Date and time", 
        "Administration Post", 
        "Village", 
        "_Local GPS_latitude", 
        "_Local GPS_longitude", 
        "_Local GPS_precision", 
        "_uuid"
    ]
    
    # Check which are present
    present = [col for col in required if col in df.columns]
    missing = [col for col in required if col not in df.columns]
    
    st.write(f"**Found {len(present)} of {len(required)} required columns**")
    
    if missing:
        st.error(f"❌ Missing required columns: {missing}")
        
        # Show what columns are available that might be similar
        st.write("**🔍 Looking for alternatives...**")
        for missing_col in missing:
            # Try to find similar columns
            similar = []
            for col in df.columns:
                # Check if the English column name appears in the actual column
                if missing_col.lower() in col.lower() or col.lower() in missing_col.lower():
                    similar.append(col)
            if similar:
                st.write(f"- `{missing_col}` → found similar: {similar}")
        
        # If it's just Administration Post, try to find it
        if 'Administration Post' in missing:
            # Try to find any column that might be administration post
            for col in df.columns:
                if any(word in col.lower() for word in ['post', 'administrat', 'admin']):
                    st.write(f"💡 Found possible match: `{col}` → renaming to 'Administration Post'")
                    df = df.rename(columns={col: 'Administration Post'})
                    break
        
        # Re-check after attempts
        missing = [col for col in required if col not in df.columns]
        
        if missing:
            st.error(f"❌ Still missing: {missing}")
            st.stop()
    
    return raw, df, lang

# ============================================================================
# SPECIES TYPO DETECTION
# ============================================================================

def find_species_typos(df):
    """
    Find potential species typos using fuzzy matching.
    """
    typos = []
    
    # Find species-related columns
    species_cols = []
    for col in df.columns:
        # Check if it's a species column
        is_species = False
        for keyword in ['Seagrass species', 'du\'ut tasi', 'rumput laut', 'spesies']:
            if keyword in col:
                is_species = True
                break
        
        if is_species:
            # Check if it contains a species name
            for sp in SPECIES_LIST:
                if sp in col or sp.replace(' ', '') in col.replace(' ', ''):
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
                    # Use fuzzy matching
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
    """
    Apply corrections to species typos.
    """
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

uploaded = st.file_uploader("Raw Kobo export (.xlsx)", type=["xlsx"])

if uploaded is None:
    st.info("Upload a file to run the pipeline.")
    st.stop()

# ---- Load data ----
try:
    raw_df, df, lang = load_data_with_language(uploaded)
    st.success(f"✅ Successfully loaded {lang} version with {len(df)} records")
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
