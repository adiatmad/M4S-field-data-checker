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

import sys
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import numpy as np
from rapidfuzz import fuzz, process

# PROJECT-SPECIFIC REFERENCE DATA

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
                                          f"GPS precision {prec:.1f} m: unusable; record location manually"))
            elif prec >= GPS_PRECISION_WARN_M:
                issues.append(_new_issue(i, uid, "gps", "_Local GPS_precision", "warning",
                                          f"GPS precision {prec:.1f} m: below recommended accuracy"))
        dist = _haversine_m(*SITE_CENTROID, lat, lon)
        if dist > SITE_RADIUS_M:
            issues.append(_new_issue(
                i, uid, "gps", "_Local GPS", "warning",
                f"{dist:.0f} m from the configured site centroid; exceeds the {SITE_RADIUS_M} m "
                "centroid-distance threshold. Verify coordinates, CRS, and site assignment; "
                "this check does not test polygon containment."
            ))
    coord_cols = ["_Local GPS_latitude", "_Local GPS_longitude"]
    dup_mask = df.duplicated(subset=coord_cols, keep=False) & df[coord_cols].notna().all(axis=1)
    for i, r in df[dup_mask].iterrows():
        issues.append(_new_issue(i, r["_uuid"], "gps", "_Local GPS", "warning",
                                  "Coordinates are identical to another record; check whether GPS was refreshed between quadrats."))
    return issues


def _species_is_selected(value):
    if pd.isna(value):
        return False
    return str(value).strip().casefold() in {"1", "1.0", "true", "yes", "sim"}


def validate_species_logic(df):
    issues = []
    selection_columns = [f"Seagrass species present in the Quadrat/{sp}" for sp in SPECIES_LIST]
    available_selection_columns = [col for col in selection_columns if col in df.columns]
    if not available_selection_columns:
        return [_new_issue(None, None, "schema", "Seagrass species", "error",
                           "Required seagrass species-selection fields are missing from the export.")]
    for i, r in df.iterrows():
        uid = r.get("_uuid")
        for sp in SPECIES_LIST:
            sel_col = f"Seagrass species present in the Quadrat/{sp}"
            pct_col = f"Percent {sp} (%)"
            if sel_col not in df.columns:
                continue
            selected = _species_is_selected(r[sel_col])
            if pct_col not in df.columns:
                if selected:
                    issues.append(_new_issue(i, uid, "species", pct_col, "error",
                                              f"{sp} marked present but its percentage-cover column is missing from the export"))
                continue
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
        any_species = any(_species_is_selected(r.get(col)) for col in selection_columns if col in df.columns)
        if presence == "No" and any_species:
            issues.append(_new_issue(i, uid, "species", "Presence of Seagrass", "error",
                                      "Presence of Seagrass = No but species were recorded"))
        if presence == "Yes" and not any_species:
            issues.append(_new_issue(i, uid, "species", "Seagrass species", "error",
                                      "Missing seagrass species: Presence of Seagrass = Yes but no species selected"))
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
                 "Quadrat Number", "Presence of Seagrass", "_uuid",
                 "_Local GPS_latitude", "_Local GPS_longitude"]
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
                                      f"Survey completed in {dur:.0f} s: unusually fast; check for auto-fill."))
        elif dur > DURATION_LONG_SESSION_S:
            issues.append(_new_issue(i, r["_uuid"], "logic", "start/end", "warning",
                                      f"Session lasted {dur/3600:.1f} h: the form may have been left open or resumed later."))
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
                                  "Duplicate _uuid: the same submission may have been ingested twice."))
    logical_key = ["Collector Name", "Transect Number", "Quadrat Number", "Date and time"]
    if all(k in df.columns for k in logical_key):
        dup2 = df.duplicated(subset=logical_key, keep=False)
        for i, r in df[dup2].iterrows():
            issues.append(_new_issue(i, r["_uuid"], "duplicate", "combo", "warning",
                                      "Same collector, transect, quadrat, and date as another record: possible re-entry."))
    return issues


def validate_coverage_mismatch(df, tolerance=5):
    """Compare summed species cover with Epicover Percentage (%) within a 5-point tolerance."""
    issues = []
    pct_cols = [f"Percent {species} (%)" for species in SPECIES_LIST
                if f"Percent {species} (%)" in df.columns]
    total_col = "Epicover Percentage (%)"
    if total_col not in df.columns or not pct_cols:
        return issues
    for i, row in df.iterrows():
        total_cover = row[total_col]
        if pd.isna(total_cover):
            continue
        species_total = sum(float(row[col]) for col in pct_cols if pd.notna(row[col]))
        difference = abs(species_total - float(total_cover))
        if difference > tolerance:
            issues.append(_new_issue(
                i, row.get("_uuid"), "coverage_mismatch", total_col, "error",
                f"Individual species percentages sum to {species_total:.1f}% but Epicover Percentage is {float(total_cover):.1f}% (difference: {difference:.1f}%; allowed tolerance: {tolerance:.1f} percentage points)"
            ))
    return issues

def _general_condition_column(df):
    """Find a known general-condition field without guessing arbitrary columns."""
    candidates = ["Seagrass General Condition", "General Condition",
                  "General condition of seagrass", "Seagrass Condition",
                  "Kondisaun Jeral", "Kondisaun Geral",
                  "Kondisaun Jeral Du'ut tasi", "Kondisaun Du'ut tasi"]
    normalized = {re.sub(r"[^a-z0-9]+", " ", str(c).casefold()).strip(): c for c in df.columns}
    for candidate in candidates:
        key = re.sub(r"[^a-z0-9]+", " ", candidate.casefold()).strip()
        if key in normalized:
            return normalized[key]
    for column in df.columns:
        words = set(re.sub(r"[^a-z0-9]+", " ", str(column).casefold()).split())
        if ("general" in words and "condition" in words) or (
            "kondisaun" in words and words.intersection({"jeral", "geral", "seagrass", "duut", "tasi"})
        ):
            return column
    return None


def validate_seagrass_general_condition(df):
    """Flag a missing general-condition field or blank row values."""
    field = _general_condition_column(df)
    if field is None:
        return [_new_issue(None, None, "schema", "Seagrass General Condition", "error",
                           "Required field for seagrass general condition is missing from the export.")]
    issues = []
    for idx, row in df.iterrows():
        value = row[field]
        if pd.isna(value) or (isinstance(value, str) and not value.strip()):
            issues.append(_new_issue(idx, row.get("_uuid"), "condition", field, "error",
                                     "Missing seagrass general condition."))
    return issues


def _issue_export_frame(df, issues):
    """Enrich findings with enumerator and direct Kobo image URL for field review."""
    enriched = issues.copy()
    if "enumerator" not in enriched.columns:
        enriched["enumerator"] = ""
    if "photo_url" not in enriched.columns:
        enriched["photo_url"] = ""
    if df is None or df.empty:
        return enriched
    enumerator_col = "Collector Name" if "Collector Name" in df.columns else None
    photo_col = "Quadrat Photo_URL" if "Quadrat Photo_URL" in df.columns else None
    for issue_index, issue in enriched.iterrows():
        row_index = issue.get("row_index")
        try:
            source = df.loc[row_index]
            if isinstance(source, pd.DataFrame):
                source = source.iloc[0]
        except (KeyError, TypeError, IndexError):
            continue
        if enumerator_col:
            enriched.at[issue_index, "enumerator"] = source.get(enumerator_col, "")
        if photo_col:
            value = source.get(photo_col, "")
            enriched.at[issue_index, "photo_url"] = "" if pd.isna(value) else str(value).strip()
    return enriched


def filter_enumerator_report_issues(issues, *, include_gps_accuracy=True, include_site_distance=True):
    """Hide optional GPS-quality findings from enumerator reports without deleting internal findings."""
    visible = issues.copy()
    if not include_gps_accuracy and "field" in visible.columns:
        precision = visible["field"].astype("string").str.contains("precision", case=False, na=False)
        visible = visible.loc[~((visible["category"] == "gps") & precision)]
    if not include_site_distance and "message" in visible.columns:
        distance = visible["message"].astype("string").str.contains(
            "centroid-distance threshold", case=False, na=False
        )
        visible = visible.loc[~((visible["category"] == "gps") & distance)]
    return visible.reset_index(drop=True)


def build_enumerator_error_logs(df, issues, *, include_gps_accuracy=True, include_site_distance=True):
    """Return one enriched CSV dataframe per enumerator, sorted by enumerator name."""
    filtered = filter_enumerator_report_issues(
        issues, include_gps_accuracy=include_gps_accuracy,
        include_site_distance=include_site_distance,
    )
    enriched = _issue_export_frame(df, filtered)
    if enriched.empty:
        return {}
    enriched["enumerator"] = enriched["enumerator"].fillna("").astype(str).str.strip()
    enriched.loc[enriched["enumerator"].eq(""), "enumerator"] = "Unknown enumerator"
    logs = {}
    for name in sorted(enriched["enumerator"].unique(), key=str.casefold):
        logs[name] = enriched.loc[enriched["enumerator"] == name].sort_values(
            ["row_index", "severity"], kind="stable", na_position="last"
        ).reset_index(drop=True)
    return logs


def enumerator_error_zip(df, issues, *, include_gps_accuracy=True, include_site_distance=True):
    """Build a ZIP of individual enumerator CSV error logs."""
    import io
    import zipfile

    logs = build_enumerator_error_logs(
        df, issues, include_gps_accuracy=include_gps_accuracy,
        include_site_distance=include_site_distance,
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for index, (name, frame) in enumerate(logs.items(), start=1):
            safe = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._") or "enumerator"
            archive.writestr(f"{index:02d}_{safe}_errors.csv", frame.to_csv(index=False))
    return buffer.getvalue()


def validate(df) -> pd.DataFrame:
    all_issues = []
    for fn in (validate_gps, validate_species_logic, validate_seagrass_general_condition,
               validate_percent_fields, validate_mandatory_fields, validate_numeric_parse,
               validate_timestamps, validate_photos, validate_duplicate_submissions,
               validate_coverage_mismatch):
        all_issues.extend(fn(df))
    # Keep a stable schema even when no findings exist; report generation and CSV exports
    # must work for clean datasets too.
    columns = ["row_index", "uuid", "category", "field", "severity", "message"]
    return pd.DataFrame(all_issues, columns=columns)



def add_qa_columns(df, issues):
    """
    Add QA flag columns and a Message column to the dataframe.
    Each flag column indicates if a row has a specific type of issue.
    The Message column contains detailed descriptions of all issues for each row.
    """
    df_qa = df.copy()
    
    qa_columns = [
        'qa_gps_precision_0',
        'qa_missing_coordinates',
        'qa_outside_boundary',
        'qa_duplicate_uuid',
        'qa_species_logic',
        'qa_missing_general_condition',
        'qa_coverage_mismatch'
    ]
    
    for col in qa_columns:
        df_qa[col] = ''
    
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
                elif 'centroid-distance threshold' in message:
                    # Keep the legacy column for downstream compatibility, but do not
                    # represent a centroid-distance alert as confirmed polygon exclusion.
                    df_qa.at[row_idx, 'qa_outside_boundary'] = 'Review'
                    row_messages[row_idx].append(message)

            elif category == 'duplicate' and field == '_uuid':
                df_qa.at[row_idx, 'qa_duplicate_uuid'] = 'Yes'
                dup_count = (df['_uuid'] == df_qa.at[row_idx, '_uuid']).sum()
                row_messages[row_idx].append(f"Duplicate submission - same UUID appears {dup_count} times in the dataset.")
                
            elif category == 'species':
                # Every species rule must reach the row-level flag and Message column,
                # including missing species selections and missing percentage columns.
                df_qa.at[row_idx, 'qa_species_logic'] = 'Yes'
                row_messages[row_idx].append(f"Species logic error: {message}")

            elif category == 'condition':
                df_qa.at[row_idx, 'qa_missing_general_condition'] = 'Yes'
                row_messages[row_idx].append(message)

            elif category == 'coverage_mismatch':
                df_qa.at[row_idx, 'qa_coverage_mismatch'] = f"Yes - {message}"
                # Use the full message from the issue
                row_messages[row_idx].append(f"Coverage mismatch: {message}")
    
    # Combine all messages for each row
    for idx, messages in row_messages.items():
        if messages:
            df_qa.at[idx, 'Message'] = '; '.join(messages)
    
    return df_qa



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
        if not isinstance(v, str):
            return v
        if "_" in v:
            return v.replace("_", " ").title()
        # Normalize only uniform all-lower/all-upper names; preserve intentional mixed case.
        if v.isalpha() and (v.islower() or v.isupper()):
            return v.title()
        if v and (v.islower() or v.isupper()):
            return v.title()
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
    lines.append(f"# M4S Field Data QA Report: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
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



def export_outputs(raw_df, clean_df, issues, correction_log, out_dir):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Add QA columns to the raw data before export.
    raw_with_qa = add_qa_columns(raw_df, issues)
    raw_with_qa.to_csv(out_dir / "raw_with_qa_flags.csv", index=False)
    clean_df.to_csv(out_dir / "clean_dataset.csv", index=False)
    issues.to_csv(out_dir / "qa_issues.csv", index=False)
    correction_log.to_csv(out_dir / "correction_log.csv", index=False)
    generate_qa_report(clean_df, issues, correction_log, out_dir / "qa_report.md")

    # Give each enumerator a separate, sortable error log with direct image URLs.
    enumerator_dir = out_dir / "enumerator_errors"
    enumerator_dir.mkdir(parents=True, exist_ok=True)
    for previous_log in enumerator_dir.glob("*_errors.csv"):
        previous_log.unlink()
    logs = build_enumerator_error_logs(clean_df, issues)
    for index, (name, frame) in enumerate(logs.items(), start=1):
        safe = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._") or "enumerator"
        frame.to_csv(enumerator_dir / f"{index:02d}_{safe}_errors.csv", index=False)
    (out_dir / "enumerator_error_logs.zip").write_bytes(enumerator_error_zip(clean_df, issues))


# ENTRY POINT

def run(input_path: str, out_dir: str = "output"):
    raw_df, df = load_data(input_path)
    df = standardize(df)
    issues = validate(df)
    df, correction_log = correct(df)
    export_outputs(raw_df, df, issues, correction_log, out_dir)
    print(f"Done. {len(df)} records processed, {len(issues)} issues found, "
          f"{len(correction_log)} safe corrections applied.")
    print(f"Outputs written to: {Path(out_dir).resolve()}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 m4s_seagrass_qa.py <raw_kobo_export.xlsx> [output_dir]")
        sys.exit(1)
    run(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "output")
