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

# Embedded M4S QA pipeline: this app is a single-file Streamlit entry point.

"""
M4S Field Data QA Checker
=========================
Turns a raw KoboToolbox export into an analysis-ready dataset with QA flags.

Pipeline stages:
    1. load_data          -> read the raw .xlsx, keep an untouched copy
    2. standardize         -> parse dates, trim whitespace, fix dtypes
    3. validate             -> run every QA rule, collect issues
    4. add_qa_columns      -> add QA flag columns + Message column to raw data
    5. correct               -> apply ONLY the safe, reversible corrections
    6. generate_qa_report -> one Markdown report summarizing everything
    7. export_outputs      -> write clean dataset + correction log + raw copy with QA flags

Run directly:  python3 m4s_seagrass_qa.py raw_export.xlsx
Outputs land in ./output/
"""

import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import numpy as np
from rapidfuzz import fuzz, process

# ----------------------------------------------------------------------
# PROJECT-SPECIFIC REFERENCE DATA
# ----------------------------------------------------------------------

# Canonical seagrass species list (from the form's own choice list)
SPECIES_LIST = [
    "Halophila ovalis", "Halophila minor", "Halodule pinifolia",
    "Halodule uninervis", "Halophila decipiens", "Halophila beccarii",
    "Halophila spinulosa", "Enhalus acoroides", "Thalassia hemprichii",
    "Cymodocea rotundata", "Cymodocea serrulata", "Syringodium isoetifolium",
    "Ruppia maritima", "Thalassodendron ciliatum",
]

# Canonical admin geography
CANONICAL_ADMIN_POST = "Metinaro"
CANONICAL_VILLAGE = "Sabuli"

# GPS sanity boundary
SITE_CENTROID = (-8.51967, 125.7174723)   # (lat, lon), WGS84
SITE_RADIUS_M = 500

# Fuzzy-match thresholds
ENUMERATOR_MATCH_THRESHOLD = 85
GEO_MATCH_THRESHOLD = 80

# GPS quality thresholds
GPS_PRECISION_WARN_M = 10
GPS_PRECISION_ERROR_M = 30

# Survey duration sanity (seconds)
DURATION_TOO_FAST_S = 60
DURATION_LONG_SESSION_S = 8 * 3600


# ----------------------------------------------------------------------
# STAGE 1 — LOAD
# ----------------------------------------------------------------------

# Explicit aliases for the current Tetun-language Kobo export. These map known
# labels only; unknown headers are preserved and required fields are never guessed.
BASE_COLUMN_ALIASES = {
    "Naran Koletor": "Collector Name",
    "Data no Horas": "Date and time",
    "Postu Administrativu": "Administration Post",
    "Suku": "Village",
    "_GPS Lokal_latitude": "_Local GPS_latitude",
    "_GPS Lokal_longitude": "_Local GPS_longitude",
    "_GPS Lokal_altitude": "_Local GPS_altitude",
    "_GPS Lokal_precision": "_Local GPS_precision",
    "Numeru Tranjektu": "Transect Number",
    "Numeru Quadrante": "Quadrat Number",
    "Prezensa Du'ut tasi (Seagrass)": "Presence of Seagrass",
    "Persentajen Kober Alga (%)": "Percentage of Algal Cover (%)",
    "Persentajen Epicover (%) ": "Epicover Percentage (%)",
    "Foto Quadrante_URL": "Quadrat Photo_URL",
}

def _normalize_header(value) -> str:
    """Normalize whitespace and Unicode for alias lookup without rewriting source headers."""
    if not isinstance(value, str):
        return value
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value)).strip()


def _canonicalize_form_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Map explicitly supported Tetun Kobo labels to canonical names.

    Header normalization is used only for lookup; unknown source headers remain unchanged.
    """
    df = df.copy()
    aliases = dict(BASE_COLUMN_ALIASES)
    species_prefix = "Espesie du'ut tasi (seagrass) ne'ebe prezensa iha Quadrante/"
    for species in SPECIES_LIST:
        aliases[f"{species_prefix}{species}"] = f"Seagrass species present in the Quadrat/{species}"
    # Kobo/Excel exports can add leading, trailing, or repeated whitespace to labels.
    aliases = {_normalize_header(source): target for source, target in aliases.items()}

    # Select the first known percentage column for each species. Some exports include
    # older/typo variants as extra columns; leave those untouched rather than merging data.
    percentage_candidates = {
        "Halophila ovalis": ["Persentajen (Ho) Halophila ovalis  (%)", "Persentajen Halophila ovalis (%)"],
        "Halophila minor": ["Persentajen (Hm) Halophila minor (%)", "Persentajen Halophila minor (%)"],
        "Halodule pinifolia": ["Persentajen Halodule pinifolia (%)"],
        "Halodule uninervis": ["Persentajen (Hu) Halodule uninervis (%)", "Persentajen Halodule uninervis (%)"],
        "Halophila decipiens": ["Persentajen (Hd) Halophila decipiens (%)", "Persentajen Halophila decipiens (%)"],
        "Halophila beccarii": ["Persentajen (Hb) Halophila beccarii (%)", "Persentajen Halophila beccarii (%)"],
        "Halophila spinulosa": ["Persentajen (Hs) Halophila spinulosa (%)", "Persentajen Halophila spinulosa (%)"],
        "Enhalus acoroides": ["Persentajen (Ea) Enhalus acoroides (%)", "Persentajen Enhalus acoroides (%)"],
        "Thalassia hemprichii": ["Persentajen (Th) Thalassia hemprichii (%)", "Persentajen Thalassia hemprichii (%)", "Persentajen (Th) Thhalassia hemprichii (%)", "Persentajen Thhalassia hemprichii (%)"],
        "Cymodocea rotundata": ["Persentajen (Cr) Cymodocea rotundata (%)", "Persentajen Cymodocea rotundata (%)"],
        "Cymodocea serrulata": ["Persentajen (Cs) Cymodocea serrulata (%)", "Persentajen Cymodocea serrulata (%)"],
        "Syringodium isoetifolium": ["Persentajen (Si) Syringodium isoetifolium (%)", "Persentajen Syringodium isoetifolium (%)"],
        "Ruppia maritima": ["Persentajen (Rm) Ruppia maritima (%)", "Persentajen Ruppia maritima (%)"],
        "Thalassodendron ciliatum": ["Persentajen (Tc) Thalassodendron ciliatum (%)", "Persentajen Thalassodendron ciliatum (%)"],
    }
    for species, candidates in percentage_candidates.items():
        for candidate in candidates:
            aliases[_normalize_header(candidate)] = f"Percent {species} (%)"

    # Only rename when the canonical target is absent. If both are present, preserve
    # both columns and avoid silently overwriting one source field with another.
    rename = {}
    existing = set(df.columns)
    claimed_targets = set(existing)
    for source in df.columns:
        target = aliases.get(_normalize_header(source))
        if target and target not in claimed_targets:
            rename[source] = target
            claimed_targets.add(target)
    df = df.rename(columns=rename)

    # Tetun labels use Sim/Lae for yes/no; normalize only this known field's values.
    presence = "Presence of Seagrass"
    if presence in df.columns:
        df[presence] = df[presence].replace({"Sim": "Yes", "Lae": "No", "sim": "Yes", "lae": "No"})
    return df


def load_data(path: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Read a raw Kobo export and return (untouched raw data, canonical working copy)."""
    raw = pd.read_excel(path)
    working = _canonicalize_form_columns(raw)
    required = [
        "start", "end", "Collector Name", "Date and time",
        "Administration Post", "Village", "_Local GPS_latitude",
        "_Local GPS_longitude", "_Local GPS_precision", "_uuid",
        "Transect Number", "Quadrat Number", "Presence of Seagrass",
        "Quadrat Photo_URL",
    ]
    missing = [c for c in required if c not in working.columns]
    if missing:
        available = ", ".join(map(str, raw.columns))
        raise ValueError(
            "Unsupported Kobo form schema. Missing required fields after applying "
            f"known header aliases: {missing}. Available headers: {available}. "
            "No columns were inferred. Add a reviewed alias in "
            "BASE_COLUMN_ALIASES / _canonicalize_form_columns() if the form changed."
        )
    return raw, working


# ----------------------------------------------------------------------
# STAGE 2 — STANDARDIZE
# ----------------------------------------------------------------------

def _strip_all_strings(df: pd.DataFrame) -> pd.DataFrame:
    obj_cols = df.select_dtypes(include="object").columns
    for c in obj_cols:
        df[c] = df[c].apply(lambda v: v.strip() if isinstance(v, str) else v)
        df[c] = df[c].apply(
            lambda v: re.sub(r"\s+", " ", v) if isinstance(v, str) else v
        )
    return df


def standardize(df: pd.DataFrame) -> pd.DataFrame:
    df = _strip_all_strings(df)
    for col in ["start", "end", "Date and time", "_submission_time"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce", utc=True)
    df["_duration_seconds"] = (df["end"] - df["start"]).dt.total_seconds()
    numeric_like = [c for c in df.columns if "(%)" in c or c in (
        "Water Level (Cm)", "_Local GPS_latitude", "_Local GPS_longitude",
        "_Local GPS_altitude", "_Local GPS_precision",
    )]
    # Preserve evidence of nonblank values that failed numeric parsing before coercion.
    # This prevents strings such as "unknown" from becoming indistinguishable from blanks.
    parse_failures = []
    for c in numeric_like:
        original = df[c].copy()
        parsed = pd.to_numeric(original, errors="coerce")
        invalid = original.notna() & original.astype(str).str.strip().ne("") & parsed.isna()
        for idx in df.index[invalid]:
            parse_failures.append({
                "row_index": idx,
                "field": c,
                "value": str(original.loc[idx]),
            })
        df[c] = parsed
    df.attrs["numeric_parse_failures"] = parse_failures
    return df


# ----------------------------------------------------------------------
# STAGE 3 — VALIDATE
# ----------------------------------------------------------------------

def _new_issue(idx, uuid, category, field, severity, message):
    return dict(row_index=idx, uuid=uuid, category=category, field=field,
                severity=severity, message=message)


def _haversine_m(lat1, lon1, lat2, lon2):
    R = 6371000
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dphi = np.radians(lat2 - lat1)
    dlmb = np.radians(lon2 - lon1)
    a = np.sin(dphi / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dlmb / 2) ** 2
    return 2 * R * np.arcsin(np.sqrt(a))


def validate_gps(df):
    issues = []
    for i, r in df.iterrows():
        uid = r["_uuid"]
        lat, lon, prec = r["_Local GPS_latitude"], r["_Local GPS_longitude"], r["_Local GPS_precision"]
        if pd.isna(lat) or pd.isna(lon):
            issues.append(_new_issue(i, uid, "gps", "_Local GPS", "error",
                                      "Missing GPS coordinates"))
            continue
        if pd.notna(prec):
            if prec >= GPS_PRECISION_ERROR_M:
                issues.append(_new_issue(i, uid, "gps", "_Local GPS_precision", "error",
                                          f"GPS precision {prec:.1f}m — unusable, record location manually"))
            elif prec >= GPS_PRECISION_WARN_M:
                issues.append(_new_issue(i, uid, "gps", "_Local GPS_precision", "warning",
                                          f"GPS precision {prec:.1f}m — below recommended accuracy"))
        dist = _haversine_m(*SITE_CENTROID, lat, lon)
        if dist > SITE_RADIUS_M:
            issues.append(_new_issue(i, uid, "gps", "_Local GPS", "error",
                                      f"{dist:.0f}m from survey site centroid — outside project boundary"))
    coord_cols = ["_Local GPS_latitude", "_Local GPS_longitude"]
    dup_mask = df.duplicated(subset=coord_cols, keep=False) & df[coord_cols].notna().all(axis=1)
    for i, r in df[dup_mask].iterrows():
        issues.append(_new_issue(i, r["_uuid"], "gps", "_Local GPS", "warning",
                                  "Coordinates identical to another record — check GPS was refreshed between quadrats"))
    return issues


def validate_species_logic(df):
    issues = []
    for i, r in df.iterrows():
        uid = r["_uuid"]
        for sp in SPECIES_LIST:
            sel_col = f"Seagrass species present in the Quadrat/{sp}"
            pct_col = f"Percent {sp} (%)"
            if sel_col not in df.columns or pct_col not in df.columns:
                continue
            selected = r[sel_col] == 1
            pct = r[pct_col]
            if selected and (pd.isna(pct) or pct == 0):
                issues.append(_new_issue(i, uid, "species", pct_col, "error",
                                          f"{sp} marked present but no % cover recorded"))
            if pd.notna(pct) and pct > 0 and not selected:
                issues.append(_new_issue(i, uid, "species", pct_col, "error",
                                          f"% cover recorded for {sp} but species not marked present"))
            if pd.notna(pct) and (pct < 0 or pct > 100):
                issues.append(_new_issue(i, uid, "species", pct_col, "error",
                                          f"{sp} % cover {pct} outside 0-100 range"))
        presence = r.get("Presence of Seagrass")
        any_species = any(
            r.get(f"Seagrass species present in the Quadrat/{sp}") == 1
            for sp in SPECIES_LIST
        )
        if presence == "No" and any_species:
            issues.append(_new_issue(i, uid, "species", "Presence of Seagrass", "error",
                                      "Presence of Seagrass = No but species were recorded"))
        if presence == "Yes" and not any_species:
            issues.append(_new_issue(i, uid, "species", "Presence of Seagrass", "warning",
                                      "Presence of Seagrass = Yes but no species selected"))
    return issues


def validate_percent_fields(df):
    issues = []
    pct_cols = [c for c in ["Percentage of Algal Cover (%)", "Epicover Percentage (%)"] if c in df.columns]
    for i, r in df.iterrows():
        for c in pct_cols:
            v = r[c]
            if pd.notna(v) and (v < 0 or v > 100):
                issues.append(_new_issue(i, r["_uuid"], "logic", c, "error",
                                          f"{c} = {v}, outside 0-100 range"))
    return issues


def validate_mandatory_fields(df):
    mandatory = ["Collector Name", "Date and time", "Transect Number",
                 "Quadrat Number", "Presence of Seagrass", "_uuid"]
    issues = []
    missing_columns = [field for field in mandatory if field not in df.columns]
    for field in missing_columns:
        issues.append(_new_issue(None, None, "schema", field, "error",
                                  f"Required column '{field}' is missing"))
    present_fields = [field for field in mandatory if field in df.columns]
    for i, r in df.iterrows():
        uid = r.get("_uuid")
        for field in present_fields:
            value = r[field]
            is_blank = isinstance(value, str) and not value.strip()
            if pd.isna(value) or is_blank:
                issues.append(_new_issue(i, uid, "logic", field, "error",
                                          f"Mandatory field '{field}' is missing or blank"))
    return issues


def validate_numeric_parse(df):
    """Report nonblank numeric values that were coerced to NaN during standardization."""
    issues = []
    for failure in df.attrs.get("numeric_parse_failures", []):
        issues.append(_new_issue(
            failure["row_index"],
            df.at[failure["row_index"], "_uuid"] if "_uuid" in df.columns else None,
            "numeric",
            failure["field"],
            "error",
            f"Nonblank value {failure['value']!r} is not a valid number",
        ))
    return issues


def validate_timestamps(df):
    issues = []
    for i, r in df.iterrows():
        dur = r["_duration_seconds"]
        if pd.isna(dur):
            issues.append(_new_issue(i, r["_uuid"], "logic", "start/end", "error",
                                      "start/end timestamp missing or unparsable"))
            continue
        if dur <= 0:
            issues.append(_new_issue(i, r["_uuid"], "logic", "start/end", "error",
                                      "End time is before or equal to start time"))
        elif dur < DURATION_TOO_FAST_S:
            issues.append(_new_issue(i, r["_uuid"], "logic", "start/end", "warning",
                                      f"Survey completed in {dur:.0f}s — unusually fast, check for auto-fill"))
        elif dur > DURATION_LONG_SESSION_S:
            issues.append(_new_issue(i, r["_uuid"], "logic", "start/end", "warning",
                                      f"Session lasted {dur/3600:.1f}h — form likely left open/resumed later"))
    return issues


def validate_photos(df):
    issues = []
    field = "Quadrat Photo_URL"
    if field not in df.columns:
        return [_new_issue(None, None, "schema", field, "error",
                           "Required column 'Quadrat Photo_URL' is missing")]
    for i, r in df.iterrows():
        value = r[field]
        if pd.isna(value) or (isinstance(value, str) and not value.strip()):
            issues.append(_new_issue(i, r.get("_uuid"), "photo", field, "error",
                                      "No quadrat photo attached"))
    return issues


def validate_duplicate_submissions(df):
    issues = []
    dup = df.duplicated(subset=["_uuid"], keep=False)
    for i, r in df[dup].iterrows():
        issues.append(_new_issue(i, r["_uuid"], "duplicate", "_uuid", "error",
                                  "Duplicate _uuid — same submission ingested twice"))
    logical_key = ["Collector Name", "Transect Number", "Quadrat Number", "Date and time"]
    if all(k in df.columns for k in logical_key):
        dup2 = df.duplicated(subset=logical_key, keep=False)
        for i, r in df[dup2].iterrows():
            issues.append(_new_issue(i, r["_uuid"], "duplicate", "combo", "warning",
                                      "Same collector/transect/quadrat/date as another record — possible re-entry"))
    return issues


def validate_coverage_mismatch(df):
    """
    Check if individual species percentages add up to total epicover percentage.
    Uses "Epicover Percentage (%)" as the reference column.
    """
    issues = []
    
    # Get species percent columns
    pct_cols = [col for col in df.columns if col.startswith("Percent ") and " (%)" in col]
    # Use Epicover Percentage (%) as the reference column
    total_col = "Epicover Percentage (%)"
    
    if total_col in df.columns:
        for i, r in df.iterrows():
            total_cover = r[total_col]
            if pd.isna(total_cover):
                continue
            
            # Sum up individual species percentages
            species_total = 0
            for col in pct_cols:
                val = r[col]
                if pd.notna(val):
                    species_total += val
            
            # Check if species total is significantly different from total cover
            # Allow 5% tolerance for rounding/estimation errors
            if abs(species_total - total_cover) > 5:
                issues.append(_new_issue(
                    i, r["_uuid"], "coverage_mismatch", total_col, "error",
                    f"Individual species percentages sum to {species_total:.1f}% but Epicover Percentage is {total_cover:.1f}% (difference: {abs(species_total - total_cover):.1f}%)"
                ))
    
    return issues


def validate(df) -> pd.DataFrame:
    all_issues = []
    for fn in (validate_gps, validate_species_logic,
               validate_percent_fields, validate_mandatory_fields, validate_numeric_parse,
               validate_timestamps, validate_photos, validate_duplicate_submissions):
        all_issues.extend(fn(df))
    # Keep a stable schema even when no findings exist; report generation and CSV exports
    # must work for clean datasets too.
    columns = ["row_index", "uuid", "category", "field", "severity", "message"]
    return pd.DataFrame(all_issues, columns=columns)


# ----------------------------------------------------------------------
# STAGE 4 — ADD QA COLUMNS TO RAW DATA
# ----------------------------------------------------------------------

def add_qa_columns(df, issues):
    """
    Add QA flag columns and a Message column to the dataframe.
    Each flag column indicates if a row has a specific type of issue.
    The Message column contains detailed descriptions of all issues for each row.
    """
    df_qa = df.copy()
    
    # Initialize all QA columns with empty strings
    qa_columns = [
        'qa_gps_precision_0',
        'qa_missing_coordinates',
        'qa_outside_boundary',
        'qa_duplicate_uuid',
        'qa_species_logic',
        'qa_coverage_mismatch'
    ]
    
    for col in qa_columns:
        df_qa[col] = ''
    
    # Initialize Message column
    df_qa['Message'] = ''
    
    # Store messages for each row
    row_messages = {idx: [] for idx in df_qa.index}
    
    # Fill in the QA columns and collect messages based on issues
    if len(issues) > 0:
        for idx, row in issues.iterrows():
            row_idx = row['row_index']
            # Schema-level findings have no source row; they remain in qa_issues.csv
            # and must not be written into row-specific flags.
            if row_idx not in row_messages:
                continue
            category = row['category']
            field = row['field']
            message = row['message']
            
            # Map categories to QA columns and build messages
            if category == 'gps':
                if 'precision' in field and '0.0' in message:
                    df_qa.at[row_idx, 'qa_gps_precision_0'] = 'Yes'
                    row_messages[row_idx].append("GPS precision is 0.0 - this indicates no GPS fix was obtained. Record location manually.")
                elif 'Missing GPS coordinates' in message:
                    df_qa.at[row_idx, 'qa_missing_coordinates'] = 'Yes'
                    row_messages[row_idx].append("Missing GPS coordinates - both latitude and longitude are blank.")
                elif 'outside project boundary' in message:
                    df_qa.at[row_idx, 'qa_outside_boundary'] = 'Yes'
                    # Extract distance if available
                    import re
                    dist_match = re.search(r"(\d+)m from", message)
                    if dist_match:
                        dist = dist_match.group(1)
                        row_messages[row_idx].append(f"GPS point is {dist}m from site centroid - outside the {SITE_RADIUS_M}m project boundary.")
                    else:
                        row_messages[row_idx].append(f"GPS point outside project boundary: {message}")
                    
            elif category == 'duplicate' and field == '_uuid':
                df_qa.at[row_idx, 'qa_duplicate_uuid'] = 'Yes'
                # Count duplicates
                dup_count = (df['_uuid'] == df_qa.at[row_idx, '_uuid']).sum()
                row_messages[row_idx].append(f"Duplicate submission - same UUID appears {dup_count} times in the dataset.")
                
            elif category == 'species' and 'marked present but no % cover recorded' in message:
                df_qa.at[row_idx, 'qa_species_logic'] = 'Yes'
                # Extract species name
                import re
                species_match = re.search(r"(.*?) marked present", message)
                if species_match:
                    species = species_match.group(1)
                    row_messages[row_idx].append(f"Species logic error: {species} marked present but 0% cover recorded.")
                else:
                    row_messages[row_idx].append(f"Species logic error: {message}")
                    
            elif category == 'species' and '% cover recorded for' in message:
                df_qa.at[row_idx, 'qa_species_logic'] = 'Yes'
                import re
                species_match = re.search(r"% cover recorded for (.*?) but", message)
                if species_match:
                    species = species_match.group(1)
                    row_messages[row_idx].append(f"Species logic error: {species} has % cover recorded but species not marked present.")
                else:
                    row_messages[row_idx].append(f"Species logic error: {message}")
                    
            elif category == 'coverage_mismatch':
                df_qa.at[row_idx, 'qa_coverage_mismatch'] = f"Yes - {message}"
                # Use the full message from the issue
                row_messages[row_idx].append(f"Coverage mismatch: {message}")
    
    # Combine all messages for each row
    for idx, messages in row_messages.items():
        if messages:
            df_qa.at[idx, 'Message'] = '; '.join(messages)
    
    return df_qa


# ----------------------------------------------------------------------
# STAGE 5 — CORRECT
# ----------------------------------------------------------------------

def _fuzzy_canonicalize(series: pd.Series, threshold: int) -> tuple[pd.Series, dict]:
    values = series.dropna().unique().tolist()
    norm = {v: re.sub(r"\s+", " ", v.replace("_", " ")).strip() for v in values}
    counts = series.value_counts()

    clusters: list[list[str]] = []
    assigned = set()
    for v in values:
        if v in assigned:
            continue
        cluster = [v]
        assigned.add(v)
        for other in values:
            if other in assigned:
                continue
            if fuzz.token_sort_ratio(norm[v].lower(), norm[other].lower()) >= threshold:
                cluster.append(other)
                assigned.add(other)
        clusters.append(cluster)

    def format_quality(v: str) -> int:
        score = 0
        if "_" not in v:
            score += 2
        if v != v.lower():
            score += 1
        return score

    mapping = {}
    for cluster in clusters:
        canonical = max(cluster, key=lambda v: (format_quality(v), counts[v]))
        for v in cluster:
            mapping[v] = canonical
    corrected = series.map(lambda v: mapping.get(v, v) if pd.notna(v) else v)
    return corrected, mapping


def correct(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    df = df.copy()
    log_rows = []

    def log_change(mask, col, mapping, rule):
        for i in df.index[mask]:
            before = df.at[i, col]
            after_val = mapping.get(before, before) if isinstance(mapping, dict) else None
            log_rows.append(dict(row_index=i, uuid=df.at[i, "_uuid"], field=col,
                                  rule=rule, before=before, after=after_val,
                                  timestamp=datetime.now(timezone.utc).isoformat()))

    # Safe correction 1: enumerator name normalization
    corrected, mapping = _fuzzy_canonicalize(df["Collector Name"], ENUMERATOR_MATCH_THRESHOLD)
    changed_mask = (df["Collector Name"] != corrected) & df["Collector Name"].notna()
    log_change(changed_mask, "Collector Name", mapping, "enumerator_name_normalization")
    df["Collector Name"] = corrected

    # Reformat snake_case names
    before_fmt = df["Collector Name"].copy()

    def format_fix(v):
        if isinstance(v, str) and "_" in v:
            return v.replace("_", " ").title()
        return v

    df["Collector Name"] = df["Collector Name"].apply(format_fix)
    fmt_changed = before_fmt != df["Collector Name"]
    for i in df.index[fmt_changed]:
        log_rows.append(dict(row_index=i, uuid=df.at[i, "_uuid"], field="Collector Name",
                              rule="enumerator_name_formatting", before=before_fmt.at[i],
                              after=df.at[i, "Collector Name"],
                              timestamp=datetime.now(timezone.utc).isoformat()))

    # Safe correction 2: geography typo fix (only obvious typos)
    for field, canon in [("Administration Post", CANONICAL_ADMIN_POST),
                          ("Village", CANONICAL_VILLAGE)]:
        before_col = df[field].copy()
        def fix(v):
            if pd.isna(v) or v == canon:
                return v
            score = fuzz.token_sort_ratio(str(v).lower(), canon.lower())
            return canon if score >= ENUMERATOR_MATCH_THRESHOLD else v
        df[field] = df[field].apply(fix)
        changed_mask = before_col != df[field]
        for i in df.index[changed_mask]:
            log_rows.append(dict(row_index=i, uuid=df.at[i, "_uuid"], field=field,
                                  rule="geography_typo_fix", before=before_col.at[i],
                                  after=df.at[i, field],
                                  timestamp=datetime.now(timezone.utc).isoformat()))

    correction_log = pd.DataFrame(log_rows)
    return df, correction_log


# ----------------------------------------------------------------------
# STAGE 6 — QA REPORT
# ----------------------------------------------------------------------

def generate_qa_report(df, issues, correction_log, out_path):
    total = len(df)
    # Defensive normalization for callers that pass an empty, untyped DataFrame.
    if issues.empty and not len(issues.columns):
        issues = pd.DataFrame(columns=["row_index", "uuid", "category", "field", "severity", "message"])
    err = issues[issues.severity == "error"]
    warn = issues[issues.severity == "warning"]
    flagged_records = issues.row_index.dropna().nunique() if len(issues) else 0
    passed = total - flagged_records

    lines = []
    lines.append(f"# M4S Field Data QA Report — {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
    lines.append("## Summary\n")
    lines.append(f"- Total records: **{total}**")
    lines.append(f"- Clean (no issues): **{passed}**")
    lines.append(f"- Records with at least one issue: **{flagged_records}**")
    lines.append(f"- Errors: **{len(err)}**  |  Warnings: **{len(warn)}**")
    lines.append(f"- Safe corrections applied: **{len(correction_log)}**\n")

    lines.append("## Issues by category\n")
    if len(issues):
        by_cat = issues.groupby(["category", "severity"]).size().unstack(fill_value=0)
        lines.append(by_cat.to_markdown())
    else:
        lines.append("No issues found.")
    lines.append("")

    lines.append("## Corrections applied (by rule)\n")
    if len(correction_log):
        lines.append(correction_log.groupby("rule").size().to_markdown())
    else:
        lines.append("No corrections were applied.")
    lines.append("")

    lines.append("## Every flagged record\n")
    lines.append("| Row | UUID | Category | Field | Severity | Message |")
    lines.append("|---|---|---|---|---|---|")
    for _, r in issues.sort_values(["row_index", "severity"]).iterrows():
        lines.append(f"| {r.row_index} | {str(r.uuid)[:8]}… | {r.category} | {r.field} | "
                      f"{r.severity} | {r.message} |")

    Path(out_path).write_text("\n".join(lines), encoding="utf-8")


# ----------------------------------------------------------------------


st.set_page_config(page_title="M4S Field Data QA Checker", layout="wide")
st.title("🌿 M4S Field Data QA Checker")
st.caption("Upload the raw Kobo export (.xlsx). The file is processed by the server running this app. Use a local deployment for sensitive field data unless the host's access controls and data-protection arrangements have been reviewed.")

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
qa_cols = ['qa_gps_precision_0', 'qa_missing_coordinates', 
           'qa_outside_boundary', 'qa_duplicate_uuid', 'qa_species_logic',
           'qa_coverage_mismatch']

qa_summary = {}
for col in qa_cols:
    if col in raw_with_qa.columns:
        if col == 'qa_coverage_mismatch':
            count = raw_with_qa[col].str.startswith('Yes', na=False).sum()
        else:
            count = (raw_with_qa[col] == 'Yes').sum()
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
    # The managed temporary directory is removed automatically after the report is read.
    with tempfile.TemporaryDirectory(prefix="m4s_qa_") as temp_dir:
        report_path = pathlib.Path(temp_dir) / "qa_report.md"
        generate_qa_report(clean_df, issues, correction_log, report_path)
        report_text = report_path.read_text(encoding="utf-8")
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
    | **qa_gps_precision_0** | GPS precision is 0.0 | Recorded precision is 0.0 (likely no GPS fix) |
    | **qa_missing_coordinates** | Missing GPS coordinates | No lat/long recorded |
    | **qa_outside_boundary** | Outside survey area | GPS point >500m from site centroid |
    | **qa_duplicate_uuid** | Duplicate submission | Same UUID appears more than once |
    | **qa_species_logic** | Species logic error | Species marked present but 0% cover, or vice versa |
    | **qa_coverage_mismatch** | Coverage mismatch | Individual species % don't sum to Epicover Percentage |
    
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
