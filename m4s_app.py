import io
import json
import csv
import pandas as pd
import streamlit as st
from datetime import datetime
import tempfile
import pathlib
import uuid
from io import BytesIO
from pathlib import Path
from typing import Any
import numpy as np
import re
import pandera.pandas as pa
from frictionless import validate as frictionless_validate
from rapidfuzz import fuzz, process
from correction_review import apply_approved_corrections, suggest_corrections
from dataframe_exports import dataframe_to_xlsx
from enumerator_reports import build_enumerator_error_logs, enumerator_error_workbook, enumerator_error_zip, filter_enumerator_report_issues
from enumerator_raw_exports import enumerator_raw_data_zip
from qa_message_localization import localize_qa_issue_messages
from qa_table_filters import select_rows_for_review



# Embedded M4S QA pipeline: this app is a single-file Streamlit entry point.

# M4S Streamlit entry point; see README.md for user instructions.

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
        # Tetum Sim/Lae responses may be exported with any capitalization.
        normalized_presence = df[presence].map(
            lambda value: value.strip().casefold() if isinstance(value, str) else value
        )
        df[presence] = normalized_presence.replace({"sim": "Yes", "lae": "No"})
    return df


def load_data(path: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Read a raw Kobo export and return (untouched raw data, canonical working copy)."""
    raw = pd.read_excel(path)
    working = _canonicalize_form_columns(raw)
    # Kobo exports can omit system metadata such as start/end/_uuid.
    # These fields support optional duration/duplicate checks, not core survey QA.
    required = [
        "Collector Name", "Date and time",
        "Administration Post", "Village", "_Local GPS_latitude",
        "_Local GPS_longitude", "Transect Number", "Quadrat Number",
        "Presence of Seagrass", "Quadrat Photo_URL",
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
    if "start" in df.columns and "end" in df.columns:
        df["_duration_seconds"] = (df["end"] - df["start"]).dt.total_seconds()
    else:
        # Without Kobo start/end metadata, duration cannot be evaluated.
        df["_duration_seconds"] = pd.Series(np.nan, index=df.index, dtype="float64")
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
        uid = r.get("_uuid")
        lat, lon = r["_Local GPS_latitude"], r["_Local GPS_longitude"]
        prec = r.get("_Local GPS_precision", np.nan)
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
        issues.append(_new_issue(i, r.get("_uuid"), "gps", "_Local GPS", "warning",
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



def validate_categorical_text_quality(df):
    """Warn about inconsistent capitalization in low-cardinality categorical text fields.

    This reports suggestions instead of rewriting survey answers. It skips names,
    free-text fields, identifiers, URLs, and columns with too many distinct values.
    """
    issues = []
    excluded = ("name", "naran", "collector", "uuid", "url", "photo", "comment",
                "note", "description", "address", "email", "phone", "date", "time",
                "start", "end", "id", "enumerator")
    text_columns = df.select_dtypes(include=["object", "string"]).columns
    for column in text_columns:
        label = str(column).casefold()
        if any(token in label for token in excluded):
            continue
        values = df[column]
        nonblank = values[values.notna()].map(
            lambda value: value.strip() if isinstance(value, str) else value
        )
        nonblank = nonblank[nonblank.map(
            lambda value: isinstance(value, str) and bool(value)
        )]
        distinct = list(pd.unique(nonblank))
        if len(distinct) < 2 or len(distinct) > 30:
            continue
        groups = {}
        for value in distinct:
            groups.setdefault(value.casefold(), []).append(value)
        for variants in groups.values():
            if len(variants) < 2:
                continue
            counts = {variant: int((nonblank == variant).sum()) for variant in variants}
            canonical = max(variants, key=lambda variant: (counts[variant], -variants.index(variant)))
            for idx, value in nonblank[nonblank.map(
                lambda item: item in variants and item != canonical
            )].items():
                issues.append(_new_issue(
                    idx, df.at[idx, "_uuid"] if "_uuid" in df.columns else None,
                    "text_formatting", column, "warning",
                    f"Inconsistent capitalization for {value!r}; most common form is {canonical!r}. "
                    "Review the value; the checker does not change it automatically."
                ))
        # Suggest likely spelling variants (including Tetum categorical values) without
        # asserting correctness; no authoritative Tetum vocabulary is bundled with the app.
        for left_index, left in enumerate(distinct):
            for right in distinct[left_index + 1:]:
                if left.casefold() == right.casefold():
                    continue
                similarity = fuzz.ratio(left.casefold(), right.casefold())
                if similarity < 85:
                    continue
                counts = {value: int((nonblank == value).sum()) for value in (left, right)}
                canonical = max((left, right), key=lambda value: (counts[value], -distinct.index(value)))
                variant = right if canonical == left else left
                for idx in nonblank[nonblank == variant].index:
                    issues.append(_new_issue(
                        idx, df.at[idx, "_uuid"] if "_uuid" in df.columns else None,
                        "text_formatting", column, "warning",
                        f"Possible spelling variant {variant!r}; similar observed value is {canonical!r} "
                        f"({similarity:.0f}% similarity). Verify the Tetum spelling and meaning manually."
                    ))
    return issues

def validate_percent_fields(df):
    issues = []
    pct_cols = [c for c in ["Percentage of Algal Cover (%)", "Epicover Percentage (%)"] if c in df.columns]
    for i, r in df.iterrows():
        for c in pct_cols:
            v = r[c]
            if pd.notna(v) and (v < 0 or v > 100):
                issues.append(_new_issue(i, r.get("_uuid"), "logic", c, "error",
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
    if "start" not in df.columns or "end" not in df.columns:
        return issues
    for i, r in df.iterrows():
        dur = r["_duration_seconds"]
        if pd.isna(dur):
            issues.append(_new_issue(i, r.get("_uuid"), "logic", "start/end", "error",
                                      "start/end timestamp missing or unparsable"))
            continue
        if dur <= 0:
            issues.append(_new_issue(i, r.get("_uuid"), "logic", "start/end", "error",
                                      "End time is before or equal to start time"))
        elif dur < DURATION_TOO_FAST_S:
            issues.append(_new_issue(i, r.get("_uuid"), "logic", "start/end", "warning",
                                      f"Survey completed in {dur:.0f} s: unusually fast; check for auto-fill."))
        elif dur > DURATION_LONG_SESSION_S:
            issues.append(_new_issue(i, r.get("_uuid"), "logic", "start/end", "warning",
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
    # Do not treat a missing UUID column (or blank UUID values) as duplicate submissions.
    if "_uuid" in df.columns:
        has_uuid = df["_uuid"].notna() & df["_uuid"].astype(str).str.strip().ne("")
        dup = df.loc[has_uuid].duplicated(subset=["_uuid"], keep=False)
        for i, r in df.loc[has_uuid].loc[dup].iterrows():
            issues.append(_new_issue(i, r.get("_uuid"), "duplicate", "_uuid", "error",
                                      "Duplicate _uuid: the same submission may have been ingested twice."))
    logical_key = ["Collector Name", "Transect Number", "Quadrat Number", "Date and time"]
    if all(k in df.columns for k in logical_key):
        dup2 = df.duplicated(subset=logical_key, keep=False)
        for i, r in df[dup2].iterrows():
            issues.append(_new_issue(i, r.get("_uuid"), "duplicate", "combo", "warning",
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


def validate(df) -> pd.DataFrame:
    all_issues = []
    for fn in (validate_gps, validate_species_logic, validate_seagrass_general_condition,
               validate_categorical_text_quality, validate_percent_fields, validate_mandatory_fields, validate_numeric_parse,
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


def correct(df: pd.DataFrame, *, enumerator_match_threshold: int = ENUMERATOR_MATCH_THRESHOLD,
            geography_match_threshold: int = GEO_MATCH_THRESHOLD) -> tuple[pd.DataFrame, pd.DataFrame]:
    for label, threshold in (("enumerator", enumerator_match_threshold), ("geography", geography_match_threshold)):
        if isinstance(threshold, bool) or not isinstance(threshold, int) or not 80 <= threshold <= 100:
            raise ValueError(f"{label.capitalize()} match threshold must be an integer from 80 to 100.")
    df = df.copy()
    log_rows = []

    def log_change(mask, col, mapping, rule):
        for i in df.index[mask]:
            before = df.at[i, col]
            after_val = mapping.get(before, before) if isinstance(mapping, dict) else None
            log_rows.append(dict(row_index=i, uuid=df.at[i, "_uuid"] if "_uuid" in df.columns else None, field=col,
                                  rule=rule, before=before, after=after_val,
                                  timestamp=datetime.now(timezone.utc).isoformat()))

    # Safe correction 1: enumerator name normalization
    corrected, mapping = _fuzzy_canonicalize(df["Collector Name"], enumerator_match_threshold)
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
        log_rows.append(dict(row_index=i, uuid=df.at[i, "_uuid"] if "_uuid" in df.columns else None, field="Collector Name",
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
            return canon if score >= geography_match_threshold else v
        df[field] = df[field].apply(fix)
        changed_mask = before_col != df[field]
        for i in df.index[changed_mask]:
            log_rows.append(dict(row_index=i, uuid=df.at[i, "_uuid"] if "_uuid" in df.columns else None, field=field,
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

    Path(out_path).write_text("\n".join(lines), encoding="utf-8")



# Generic CSV contract validation and reusable checks are embedded below.



import pandas as pd
import numpy as np

ISSUE_COLUMNS = ["row_number", "column", "category", "severity", "message"]


def _issue(row, column, message):
    return {"row_number": row, "column": column, "category": "contract",
            "severity": "error", "message": message}


def validate_contract(df: pd.DataFrame, contract: dict) -> pd.DataFrame:
    """Validate required columns, allowed values, simple types/ranges and unique keys.

    Example contract:
    {
      "required_columns": ["record_id"],
      "key_columns": ["record_id"],
      "columns": {
        "age": {"type": "integer", "min": 0, "max": 120},
        "consent": {"allowed_values": ["yes", "no"]},
        "visit_date": {"type": "date"}
      }
    }
    """
    if not isinstance(contract, dict):
        raise ValueError("Contract must be a JSON object.")
    unknown = set(contract) - {"required_columns", "key_columns", "columns"}
    if unknown:
        raise ValueError(f"Unsupported contract keys: {sorted(unknown)}")

    def names(key):
        value = contract.get(key, [])
        if not isinstance(value, list) or any(not isinstance(v, str) or not v.strip() for v in value):
            raise ValueError(f"'{key}' must be a list of non-empty column names.")
        if len(value) != len(set(value)):
            raise ValueError(f"'{key}' cannot contain duplicate column names.")
        return value

    required = names("required_columns")
    keys = names("key_columns")
    rules_by_column = contract.get("columns", {})
    if not isinstance(rules_by_column, dict):
        raise ValueError("'columns' must be an object keyed by column name.")

    issues = []
    for column in required:
        if column not in df.columns:
            issues.append(_issue("", column, "Required column is missing."))

    missing_keys = [column for column in keys if column not in df.columns]
    for column in missing_keys:
        issues.append(_issue("", column, "Key column is missing; uniqueness cannot be checked."))

    for column, rules in rules_by_column.items():
        if not isinstance(column, str) or not column.strip() or not isinstance(rules, dict):
            raise ValueError("Each 'columns' entry must map a non-empty name to a rule object.")
        unknown_rules = set(rules) - {"type", "allowed_values", "min", "max"}
        if unknown_rules:
            raise ValueError(f"Unsupported rules for '{column}': {sorted(unknown_rules)}")
        kind = rules.get("type")
        if kind not in (None, "string", "number", "integer", "date", "boolean"):
            raise ValueError(f"Unsupported type for '{column}': {kind}")
        allowed = rules.get("allowed_values")
        if allowed is not None and (not isinstance(allowed, list) or not allowed):
            raise ValueError(f"'allowed_values' for '{column}' must be a non-empty list.")
        for bound in ("min", "max"):
            if bound in rules and (isinstance(rules[bound], bool) or not isinstance(rules[bound], (int, float))):
                raise ValueError(f"'{bound}' for '{column}' must be numeric.")
        if "min" in rules and "max" in rules and rules["min"] > rules["max"]:
            raise ValueError(f"'min' cannot exceed 'max' for '{column}'.")
        if ({"min", "max"} & set(rules)) and kind not in ("number", "integer"):
            raise ValueError(f"Numeric bounds for '{column}' require type 'number' or 'integer'.")
        if column not in df.columns:
            continue

        values = df[column].astype("string")
        present = values.notna() & values.str.strip().ne("")
        if allowed is not None:
            allowed_strings = {str(v) for v in allowed}
            invalid = present & ~values.isin(allowed_strings)
            for pos in np.flatnonzero(invalid.to_numpy()):
                issues.append(_issue(pos + 2, column,
                    f"Value {values.iloc[pos]!r} is not in the allowed-value list."))

        parsed = None
        if kind in ("number", "integer"):
            parsed = pd.to_numeric(values.where(present), errors="coerce")
            invalid = present & parsed.isna()
            if kind == "integer":
                invalid |= present & parsed.notna() & (parsed % 1 != 0)
            for pos in np.flatnonzero(invalid.to_numpy()):
                issues.append(_issue(pos + 2, column,
                    f"Value {values.iloc[pos]!r} is not a valid {kind}."))
            if "min" in rules or "max" in rules:
                outside = pd.Series(False, index=parsed.index)
                if "min" in rules:
                    outside |= parsed < rules["min"]
                if "max" in rules:
                    outside |= parsed > rules["max"]
                outside &= parsed.notna()
                for pos in np.flatnonzero(outside.to_numpy()):
                    issues.append(_issue(pos + 2, column,
                        f"Numeric value {parsed.iloc[pos]:g} is outside the configured range."))
        elif kind == "date":
            parsed = pd.to_datetime(values.where(present), errors="coerce")
            invalid = present & parsed.isna()
            for pos in np.flatnonzero(invalid.to_numpy()):
                issues.append(_issue(pos + 2, column,
                    f"Value {values.iloc[pos]!r} is not a valid date."))
        elif kind == "boolean":
            invalid = present & ~values.str.casefold().isin({"true", "false", "0", "1", "yes", "no"})
            for pos in np.flatnonzero(invalid.to_numpy()):
                issues.append(_issue(pos + 2, column,
                    f"Value {values.iloc[pos]!r} is not a recognized boolean."))

    if keys and not missing_keys:
        key_values = df[keys].astype("string").apply(lambda col: col.str.strip())
        complete = key_values.notna().all(axis=1) & key_values.ne("").all(axis=1)
        duplicates = key_values.duplicated(keep=False) & complete
        for pos in np.flatnonzero(duplicates.to_numpy()):
            issues.append(_issue(pos + 2, ", ".join(keys),
                "Key value duplicates another record; verify before changing either row."))

    return pd.DataFrame(issues, columns=ISSUE_COLUMNS)

# Local-first, generic CSV quality checks for KoboToolbox exports.

import csv
from io import BytesIO
from pathlib import Path
import tempfile
from typing import Any

import numpy as np
import pandas as pd
import pandera.pandas as pa
from frictionless import validate as frictionless_validate


ISSUE_COLUMNS = ["row_number", "column", "category", "severity", "message"]



def similar_text_value_issues(df: pd.DataFrame, *, threshold: int = 90, max_unique_values: int = 100) -> pd.DataFrame:
    """Suggest similar categorical text values for human review; never edit source values.

    To limit false positives and quadratic work, identifier/location/time/URL-like columns,
    numeric-only columns, very short values, and columns with too many distinct values are skipped.
    """
    if isinstance(threshold, bool) or not isinstance(threshold, int) or not 80 <= threshold <= 100:
        raise ValueError("Similarity threshold must be an integer from 80 to 100.")
    excluded_name_parts = {"id", "uuid", "url", "email", "phone", "gps", "latitude", "longitude",
                           "date", "time", "timestamp", "photo", "image", "path", "code", "number"}
    missing_tokens = {"", "na", "n/a", "null", "none", "nan"}
    issues: list[dict] = []

    for column in df.columns:
        name_parts = set(re.sub(r"[^a-z0-9]+", " ", str(column).casefold()).split())
        if name_parts & excluded_name_parts:
            continue
        series = df[column].astype("string")
        positions_by_value: dict[str, list[int]] = {}
        for position, raw in enumerate(series.tolist(), start=2):
            if pd.isna(raw):
                continue
            value = str(raw)
            cleaned = value.strip()
            if cleaned.casefold() in missing_tokens or len(cleaned) < 3 or cleaned.startswith(("http://", "https://")):
                continue
            positions_by_value.setdefault(value, []).append(position)

        values = sorted(positions_by_value)
        if len(values) < 2 or len(values) > max_unique_values:
            continue
        numeric = pd.to_numeric(pd.Series(values, dtype="string"), errors="coerce")
        if numeric.notna().all():
            continue

        normalized = {value: re.sub(r"\s+", " ", value).strip().casefold() for value in values}
        for left_index, left in enumerate(values):
            for right in values[left_index + 1:]:
                score = int(round(fuzz.ratio(normalized[left], normalized[right])))
                if score < threshold:
                    continue
                message = (f"Text value {left!r} is similar to {right!r} ({score}% similarity). "
                           "Review whether they represent the same category; no value was changed.")
                for value in (left, right):
                    for row_number in positions_by_value[value]:
                        issues.append({"row_number": row_number, "column": column,
                                       "category": "value_variant", "severity": "warning",
                                       "message": message})

    return pd.DataFrame(issues, columns=ISSUE_COLUMNS)


def read_csv_bytes(data: bytes, *, encoding: str = "utf-8-sig") -> pd.DataFrame:
    """Read CSV bytes without silently converting identifier strings to numbers."""
    if not data:
        raise ValueError("The uploaded CSV is empty.")
    try:
        text = data.decode(encoding)
        header = next(csv.reader(text.splitlines()), [])
    except UnicodeDecodeError as exc:
        raise ValueError(f"Could not decode this CSV as {encoding}: {exc}") from exc
    if not header or not any(name.strip() for name in header):
        raise ValueError("The CSV has no columns.")
    if any(not name.strip() for name in header):
        raise ValueError("CSV column names cannot be blank.")
    if len(set(header)) != len(header):
        duplicates = sorted({name for name in header if header.count(name) > 1})
        raise ValueError(f"Duplicate column names: {duplicates}")
    try:
        frame = pd.read_csv(BytesIO(data), encoding=encoding, dtype="string", keep_default_na=False)
    except (UnicodeDecodeError, pd.errors.ParserError, pd.errors.EmptyDataError) as exc:
        raise ValueError(f"Could not parse this CSV: {exc}") from exc
    if len(frame.columns) == 0:
        raise ValueError("The CSV has no columns.")
    return frame


def _issue(row_number: Any, column: Any, category: str, severity: str, message: str) -> dict:
    return {"row_number": row_number, "column": column, "category": category,
            "severity": severity, "message": message}


def structural_issues(data: bytes, filename: str = "upload.csv") -> list[dict]:
    """Run Frictionless' CSV/resource checks and normalize its errors for display."""
    suffix = Path(filename).suffix or ".csv"
    with tempfile.NamedTemporaryFile(suffix=suffix, dir=Path.cwd(), delete=True) as tmp:
        tmp.write(data)
        tmp.flush()
        # Frictionless treats absolute local paths as unsafe by default; pass a cwd-relative path.
        report = frictionless_validate(Path(tmp.name).relative_to(Path.cwd()).as_posix())
    try:
        payload = report.to_dict()
    except AttributeError:
        payload = dict(report)
    issues = []
    for task in payload.get("tasks", []):
        for error in task.get("errors", []):
            issues.append(_issue(
                error.get("rowNumber", error.get("row_number", "")),
                error.get("fieldName", error.get("field_name", "")),
                "structure", "error",
                str(error.get("message") or error.get("type") or "CSV structure error"),
            ))
    for error in payload.get("errors", []):
        issues.append(_issue(
            error.get("rowNumber", error.get("row_number", "")),
            error.get("fieldName", error.get("field_name", "")),
            "structure", "error",
            str(error.get("message") or error.get("type") or "CSV structure error"),
        ))
    return issues



class QualityCheckError(RuntimeError):
    """A validation stage failed; no partial result should be presented as complete."""

    def __init__(self, stage: str):
        self.stage = stage
        super().__init__(f"Quality checks failed during {stage}.")


def run_quality_checks(
    data: bytes,
    filename: str,
    df: pd.DataFrame,
    *,
    missing_tokens: tuple[str, ...] = ("", "NA", "N/A", "NULL", "null"),
    duplicate_rows: bool = True,
    outlier_checks: bool = True,
    similar_text_values: bool = False,
    contract: dict | None = None,
) -> pd.DataFrame:
    """Run all enabled stages or raise a stage-labelled error; never return partial findings."""
    try:
        structure = structural_issues(data, filename)
    except Exception as exc:
        raise QualityCheckError("structural validation") from exc

    try:
        values = validate_dataframe(
            df,
            missing_tokens=missing_tokens,
            duplicate_rows=duplicate_rows,
            outlier_checks=outlier_checks,
            similar_text_values=similar_text_values,
        )
        if contract is not None:
            contract_findings = validate_contract(df, contract)
            values = pd.concat([values, contract_findings], ignore_index=True)[ISSUE_COLUMNS]
    except Exception as exc:
        raise QualityCheckError("value validation") from exc

    if not structure:
        return values

    structural_frame = pd.DataFrame(structure, columns=ISSUE_COLUMNS)
    return pd.concat([structural_frame, values], ignore_index=True)[ISSUE_COLUMNS]


def validate_dataframe(
    df: pd.DataFrame,
    *,
    missing_tokens: tuple[str, ...] = ("", "NA", "N/A", "NULL", "null"),
    duplicate_rows: bool = True,
    outlier_checks: bool = True,
    similar_text_values: bool = False,
) -> pd.DataFrame:
    """Apply generic checks; row_number is the 1-based CSV data row (header excluded)."""
    issues: list[dict] = []
    normalized_missing = {token.casefold() for token in missing_tokens}
    for column in df.columns:
        values = df[column].astype("string")
        missing = values.str.strip().str.casefold().isin(normalized_missing)
        for position, is_missing in enumerate(missing.tolist(), start=2):
            if is_missing:
                issues.append(_issue(position, column, "missing", "warning",
                                     "Value is blank or matches a configured missing-value token."))

    if duplicate_rows and not df.empty:
        duplicate_mask = df.astype("string").duplicated(keep=False)
        for position, is_duplicate in enumerate(duplicate_mask.tolist(), start=2):
            if is_duplicate:
                issues.append(_issue(position, "", "duplicate", "warning",
                                     "Entire row duplicates another row in this file."))

    schema = pa.DataFrameSchema(
        {str(column): pa.Column(nullable=True, required=False) for column in df.columns},
        strict=False,
        coerce=False,
    )
    try:
        schema.validate(df, lazy=True)
    except pa.errors.SchemaErrors as exc:
        failure_cases = exc.failure_cases
        for _, failure in failure_cases.iterrows():
            issues.append(_issue(
                "", str(failure.get("column", "")), "schema", "error",
                str(failure.get("failure_case", "DataFrame schema validation failed")),
            ))

    if similar_text_values:
        issues.extend(similar_text_value_issues(df).to_dict("records"))

    if outlier_checks:
        for column in df.columns:
            values = pd.to_numeric(df[column].astype("string").str.strip(), errors="coerce")
            valid = values.dropna()
            if len(valid) < 8 or valid.nunique() < 4:
                continue
            q1, q3 = valid.quantile([0.25, 0.75])
            spread = q3 - q1
            if not np.isfinite(spread) or spread <= 0:
                continue
            low, high = q1 - 1.5 * spread, q3 + 1.5 * spread
            outlier_positions = ((values < low) | (values > high)).fillna(False).tolist()
            for position, is_outlier in enumerate(outlier_positions, start=2):
                if is_outlier:
                    issues.append(_issue(position, column, "anomaly", "warning",
                                         f"Numeric value {values.iloc[position - 2]} is outside the IQR screening range "
                                         f"({low:g} to {high:g}); review, do not auto-correct."))

    return pd.DataFrame(issues, columns=ISSUE_COLUMNS)


def findings_summary(findings: pd.DataFrame) -> dict[str, int]:
    """Return stable summary counts for the app and tests."""
    if findings.empty:
        return {"findings": 0, "errors": 0, "warnings": 0, "affected_rows": 0}
    row_values = findings["row_number"].astype("string")
    has_row = row_values.notna() & (row_values != "")
    return {
        "findings": int(len(findings)),
        "errors": int((findings["severity"] == "error").sum()),
        "warnings": int((findings["severity"] == "warning").sum()),
        "affected_rows": int(row_values[has_row].nunique()),
    }


QA_FLAG_DETAILS = [
    (
        "qa_gps_precision_0",
        "No GPS fix",
        "GPS precision was recorded as 0.0, which usually means the phone had no usable location when the record was saved.",
    ),
    (
        "qa_missing_coordinates",
        "Missing coordinates",
        "Latitude or longitude is blank for this record.",
    ),
    (
        "qa_outside_boundary",
        "Far from the site",
        f"More than {SITE_RADIUS_M} m from the site reference point. This is a distance warning, not proof the point is outside the official site boundary.",
    ),
    (
        "qa_duplicate_uuid",
        "Duplicate record",
        "The same submission identifier appears more than once, so a record may have been downloaded or entered twice.",
    ),
    (
        "qa_species_logic",
        "Species answers",
        "A species is marked present with no cover recorded, cover is recorded without the species being marked, or a percentage is outside 0 to 100.",
    ),
    (
        "qa_missing_general_condition",
        "Missing condition",
        "The seagrass general condition answer is blank or was not found in the expected column.",
    ),
    (
        "qa_coverage_mismatch",
        "Coverage does not add up",
        "The species percentages do not match the Epicover percentage within the allowed tolerance.",
    ),
]

QA_FLAG_COLUMNS = [column for column, _, _ in QA_FLAG_DETAILS]
QA_FLAG_LABEL_MAP = {column: label for column, label, _ in QA_FLAG_DETAILS}
QA_FLAG_HELP_MAP = {
    column: f"{label}: {note} 'Yes' or 'Review' in this column means the record has this finding."
    for column, label, note in QA_FLAG_DETAILS
}


def render_generic_csv_checker():
    st.title("Check a KoboToolbox CSV file")
    st.caption(
        "Use this workflow for any KoboToolbox survey exported as a .csv file. The checker lists "
        "rows worth a second look: empty answers, exact copies of another row, unusual numbers, and "
        "values that look like spelling variants. It does not change your file."
    )
    st.caption(
        "Privacy: your file is read by the app running here. For real field data, use only a "
        "deployment your team has approved."
    )
    with st.expander("First time here? Read this before you start"):
        st.markdown(
            """
            1. In KoboToolbox, download your survey data and choose CSV as the format.
            2. Keep that download as your unchanged copy.
            3. Upload it below. The checks start on their own and the results replace the prompt.
            4. Read the summary, then use the row number and column name to find each answer in
               KoboToolbox.

            A finding means "please check this row". It does not prove the answer is wrong.
            """
        )

    st.subheader("Step 1: Upload your CSV file")
    uploaded_csv = st.file_uploader(
        "Choose a KoboToolbox CSV export (.csv)",
        type=["csv"],
        key="generic_csv_upload",
        help="The file name usually ends in .csv. A .csv file is a plain table of answers.",
    )
    with st.expander("Choose what to check"):
        st.caption(
            "These settings suit most surveys. Change them only when your team asks you to."
        )
        missing_text = st.text_input(
            "Treat these answers as missing (comma-separated)",
            value=",NA,N/A,NULL,null",
            key="generic_missing_tokens",
            help="Answers in this list are reported as missing. The leading comma means empty cells count as missing.",
        )
        check_duplicates = st.checkbox(
            "Find rows that are exact copies of another row",
            value=True,
            key="generic_duplicates",
            help="Rows with identical values in every column. Nothing is deleted or merged.",
        )
        check_outliers = st.checkbox(
            "Point out unusual numbers for review",
            value=True,
            key="generic_outliers",
            help="Compares each number with the other values in its column. An unusual number may still be a real answer.",
        )
        check_similar_values = st.checkbox(
            "Suggest values that look like spelling variants",
            value=False,
            key="generic_similar_values",
            help="Review suggestions only. The checker never merges or rewrites values.",
        )
        contract_file = st.file_uploader(
            "Optional: team rules file (.json)",
            type=["json"],
            key="generic_contract",
            help="Only use a rules file supplied by the person who owns the survey.",
        )

    contract = None
    if contract_file is not None:
        try:
            contract = json.loads(contract_file.getvalue().decode("utf-8"))
            if not isinstance(contract, dict):
                raise ValueError("The file must contain one JSON object holding the rules.")
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            st.error(
                f"The team rules file could not be read: {exc} Remove it to run the standard checks "
                "without team rules."
            )
            st.stop()

    if uploaded_csv is None:
        st.info(
            "Choose the .csv file you downloaded from KoboToolbox. The checks start on their own "
            "and the results appear here."
        )
        return
    data = uploaded_csv.getvalue()
    try:
        frame = read_csv_bytes(data)
    except ValueError as exc:
        st.error(f"This file could not be read as a CSV table: {exc}")
        return
    tokens = tuple(token.strip() for token in missing_text.split(","))
    try:
        with st.spinner("Checking your file. Large files can take a minute."):
            findings = run_quality_checks(
                data, uploaded_csv.name, frame,
                missing_tokens=tokens,
                duplicate_rows=check_duplicates,
                outlier_checks=check_outliers,
                similar_text_values=check_similar_values,
                contract=contract,
            )
    except QualityCheckError as exc:
        st.error(
            f"The checks stopped during the {exc.stage} step, so no results are shown. "
            "Try the same file once more. If it stops again, tell your coordinator the name of that "
            "step; do not send the survey file itself."
        )
        return

    summary = findings_summary(findings)
    st.subheader("Step 2: Read the summary")
    a, b, c, d = st.columns(4)
    a.metric("Rows", len(frame), help="One row is one survey record.")
    b.metric("Columns", len(frame.columns), help="One column is one question or system field.")
    c.metric(
        "Findings", summary["findings"],
        help="One finding is one answer or row to check. A single row can have more than one.",
    )
    d.metric(
        "Rows with a finding", summary["affected_rows"],
        help="Rows where at least one enabled check reported something to review.",
    )
    st.caption(
        'A finding means "please check this row", not "this answer is wrong". Rows without a '
        "finding were not proven correct; they only passed the checks you switched on."
    )

    st.subheader("Step 3: Review the findings")
    if findings.empty:
        st.success(
            "The checks you switched on did not report anything. That means these checks found "
            "nothing to review, not that every answer is correct."
        )
    else:
        st.caption(
            "Row numbers count the header as row 1, so row 2 is the first survey record. Use the row "
            "and column to find the answer in KoboToolbox."
        )
        categories = st.multiselect(
            "Show only these kinds of finding",
            sorted(findings["category"].dropna().unique()),
            key="generic_categories",
        )
        visible = findings[findings["category"].isin(categories)] if categories else findings
        st.caption(
            f"Showing the first {min(10, len(visible))} of {len(visible):,} findings. "
            "Download the Excel file to see every one."
        )
        st.dataframe(visible.head(10), width="stretch", hide_index=True)
        st.download_button(
            "Download findings (.xlsx)",
            dataframe_to_xlsx(visible, sheet_name="Findings"),
            file_name="kobo_csv_findings.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            help="The findings shown above, ready to share with the team.",
        )

    st.subheader("Step 4: Download or inspect the data")
    with st.expander("Preview the file that was read (first 100 rows)"):
        st.dataframe(frame.head(100), width="stretch", hide_index=True)
    st.download_button(
        "Download input data (.xlsx)",
        dataframe_to_xlsx(frame, sheet_name="Input data"),
        file_name=f"{pathlib.Path(uploaded_csv.name).stem}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        help="An unchanged copy of the answers, as an Excel file for review.",
    )
    st.caption(
        "Keep the original CSV as your source. Fix approved problems in your usual data process, "
        "then run these checks again on the new export."
    )


M4S_WORKFLOW = "Excel file (.xlsx) from the M4S seagrass survey"
CSV_WORKFLOW = "CSV file (.csv) from another KoboToolbox survey"

st.set_page_config(page_title="M4S Field Data QA Checker", layout="wide")
mode = st.sidebar.radio(
    "Which file did you download from KoboToolbox?",
    [M4S_WORKFLOW, CSV_WORKFLOW],
    help="Choose the option that matches the file you saved. The two workflows run different checks.",
)
st.sidebar.caption(
    "An .xlsx file opens in Excel. A .csv file is a plain table. A file from another survey will "
    "not pass the M4S checks."
)

if mode == CSV_WORKFLOW:
    render_generic_csv_checker()
else:
    st.title("Check your M4S seagrass survey data")
    st.caption(
        "Upload the Excel file you downloaded from KoboToolbox. The checker lists survey records "
        "that may need a second look. You decide what to change; the checker never edits your upload."
    )
    st.caption(
        "Privacy: the file is read by the app running here. For real field data, use only a "
        "deployment your team has approved."
    )
    with st.expander("First time here? Read this before you start"):
        st.markdown(
            """
            1. In KoboToolbox, download the M4S seagrass survey as an Excel file (.xlsx).
            2. Keep that download as your unchanged copy.
            3. Upload it below. The checks run on their own and the results replace the upload prompt.
            4. Read the summary in Step 2, then work through the flagged records in Step 4.
            5. Download the reports your coordinator asked for in Step 5.

            A flag means "please check this record". It does not prove the record is wrong.
            """
        )
    with st.expander("What this checker does and does not check"):
        st.markdown(
            f"""
            **It checks** GPS coordinates, GPS precision, distance from the site reference point,
            required answers, seagrass species answers, the general condition answer, percentage
            ranges, duplicate submissions, survey duration, quadrat photos, and whether the species
            percentages add up to the Epicover percentage.

            **It does not check** your form's own skip logic, choice lists, or repeat groups; those
            need the matching XLSForm. It also cannot decide whether a species record is
            ecologically possible for that quadrat.

            The distance check uses a {SITE_RADIUS_M} m circle around the site reference point. That
            is a distance warning, not a test against the official site boundary.
            """
        )

    st.subheader("Step 1: Upload your Excel file")
    uploaded = st.file_uploader(
        "Choose your KoboToolbox Excel file (.xlsx)",
        type=["xlsx"],
        help="Use the Excel export for the M4S seagrass survey. This workflow is not for CSV files or other projects.",
    )
    st.caption(
        "The file name usually ends in .xlsx. A CSV file, or an export from another survey, belongs "
        "in the other workflow on the left."
    )
    if uploaded is None:
        st.info(
            "Choose the .xlsx file you downloaded from KoboToolbox. The checks start on their own "
            "and the results appear below."
        )
        st.stop()

    # Keep data-cleaning thresholds visible and adjustable instead of hiding them as constants.
    with st.expander("Advanced: name and site spelling settings"):
        st.caption(
            "Leave these as they are unless your coordinator asked you to change them. A higher "
            "number means fewer names and site labels are treated as the same value."
        )
        enumerator_match_threshold = st.slider(
            "Enumerator name matching threshold",
            min_value=80, max_value=100, value=ENUMERATOR_MATCH_THRESHOLD, step=1,
            help="How close two spellings must score before the names are grouped as one enumerator.",
        )
        geography_match_threshold = st.slider(
            "Geography name matching threshold",
            min_value=80, max_value=100, value=GEO_MATCH_THRESHOLD, step=1,
            help="How close a post or village spelling must score before it is corrected to the known name.",
        )

    st.caption("The checks run in a few stages. A large export can take a minute.")
    # Run each stage separately so failures stop the workflow without exposing a traceback.
    with st.spinner("Checking your file..."):
        try:
            raw_df, df = load_data(uploaded)
        except ValueError as exc:
            st.error(f"Could not load the uploaded XLSX file: {exc}")
            st.stop()
        except Exception:
            st.error(
                "The uploaded XLSX file could not be loaded. Check that it is a valid Kobo export, "
                "then retry. If the problem persists, report the load stage without sharing survey data."
            )
            st.stop()

        try:
            df = standardize(df)
        except Exception:
            st.error(
                "M4S QA could not complete during data standardization. No results are available. "
                "Check that the export matches the expected survey schema, then retry. "
                "If the problem persists, report the standardization stage without sharing survey data."
            )
            st.stop()

        try:
            issues = validate(df)
            display_issues = localize_qa_issue_messages(issues)
        except Exception:
            st.error(
                "M4S QA could not complete during validation. No results are available. Retry the workflow. "
                "If the problem persists, report the validation stage without sharing survey data."
            )
            st.stop()

        try:
            raw_with_qa = add_qa_columns(raw_df, issues)
        except Exception:
            st.error(
                "M4S QA could not prepare row-level QA flags. No results are available. Retry the workflow. "
                "If the problem persists, report the QA-flag stage without sharing survey data."
            )
            st.stop()

        try:
            clean_df, correction_log = correct(
                df, enumerator_match_threshold=enumerator_match_threshold,
                geography_match_threshold=geography_match_threshold,
            )
        except Exception:
            st.error(
                "M4S QA could not complete the correction stage. No results are available. "
                "The uploaded source file is not changed. Retry the workflow; if the problem persists, "
                "report the correction stage without sharing survey data."
            )
            st.stop()

    total = len(clean_df)
    flagged = issues.row_index.nunique() if len(issues) else 0
    errors = (issues.severity == "error").sum() if len(issues) else 0
    warnings = (issues.severity == "warning").sum() if len(issues) else 0

    st.subheader("Step 2: Read the summary")
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Total records", total, help="One record is one survey submission.")
    col2.metric(
        "Records with no finding", total - flagged,
        help="No enabled check reported anything for these records. That is not proof that they are correct.",
    )
    col3.metric(
        "Errors", int(errors),
        help="Findings the rules classify as errors. Check each one before using the data.",
    )
    col4.metric(
        "Warnings", int(warnings),
        help="Findings worth a look. Some describe normal field conditions.",
    )
    col5.metric(
        "Automatic corrections", len(correction_log),
        help="Small clean-ups such as extra spaces, name casing, and site spelling. Every change is listed in the 'What changed' tab.",
    )
    st.caption(
        "A finding is a reason to check the original submission, not proof that the answer is wrong. "
        "These counts cover only the checks listed under 'What this checker does and does not check'."
    )

    st.divider()
    st.subheader("Step 3: See what kinds of finding were reported")
    st.caption(
        "Each number counts records with that kind of finding. The names match the qa_ columns in "
        "the downloaded Excel files and in the reference section at the bottom of this page."
    )
    flag_counts = []
    for column, label, note in QA_FLAG_DETAILS:
        if column in raw_with_qa.columns:
            matched = select_rows_for_review(
                raw_with_qa, flag_columns=[column], show_only_flagged=True,
            )
            flag_counts.append((label, len(matched), note))
    for start in range(0, len(flag_counts), 3):
        columns = st.columns(3)
        for container, (label, count, note) in zip(columns, flag_counts[start:start + 3]):
            container.metric(label, count, help=note)

    if sum(count for _, count, _ in flag_counts) == 0:
        if len(issues):
            st.info(
                f"No individual record was flagged, but {len(issues):,} finding(s) apply to the whole "
                "file. Open the 'All findings' tab below to read them."
            )
        else:
            st.success(
                "No flag was set for any record. That means the enabled checks found nothing to "
                "review; it does not certify the dataset as correct."
            )

    st.divider()
    st.subheader("Step 4: Find the records to check")
    st.caption(
        "The filters work together. Start with 'Show only records with a finding', then narrow by "
        "kind of finding or search for a name, quadrat, or value."
    )
    filter_cols = st.columns(3)
    with filter_cols[0]:
        show_only_with_issues = st.checkbox("Show only records with a finding", value=False)
    with filter_cols[1]:
        show_message_only = st.checkbox(
            "Only records with a written explanation", value=False,
            help="Shows records that have text in the Message column.",
        )
    with filter_cols[2]:
        search = st.text_input("Search the table", placeholder="Name, quadrat, value...")

    available_flag_columns = [column for column in QA_FLAG_COLUMNS if column in raw_with_qa.columns]
    if show_only_with_issues:
        qa_cols_for_filter = st.multiselect(
            "Only these kinds of finding",
            options=available_flag_columns,
            default=available_flag_columns,
            format_func=lambda column: QA_FLAG_LABEL_MAP[column],
            help="Leave this empty to see records with any kind of finding.",
        )
    else:
        qa_cols_for_filter = available_flag_columns

    display_df = select_rows_for_review(
        raw_with_qa,
        flag_columns=QA_FLAG_COLUMNS,
        show_only_flagged=show_only_with_issues,
        selected_flags=qa_cols_for_filter,
        message_only=show_message_only,
        search_text=search,
    )

    # Keep the key downloads above the preview so users do not have to scroll
    # through thousands of records to reach the next actions.
    st.caption(
        f"Showing {len(display_df):,} of {len(raw_with_qa):,} records. The preview below shows the "
        f"first {min(10, len(display_df)):,}; open the expandable table or download the filtered view "
        "when you need more."
    )
    if display_df.empty:
        st.info(
            "No record matches the current filters. Clear the search box or untick a filter to see "
            "records again."
        )

    st.subheader("Step 5: Download what you need")
    st.caption(
        "Each download is a copy. Your uploaded file is never changed on this page."
    )
    col1, col2, col3 = st.columns(3)
    with col1:
        st.download_button(
            "Download raw data with QA flags and messages (.xlsx)",
            dataframe_to_xlsx(raw_with_qa, sheet_name="Raw data with QA"),
            file_name="raw_with_qa_flags.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            help="Your original columns plus one flag column per finding type and a Message column. This is the file to fix records in.",
        )
        st.caption("Most teams open this one first.")
    with col2:
        st.download_button(
            "Download QA issues list (.xlsx)",
            dataframe_to_xlsx(issues, sheet_name="QA issues"),
            file_name="qa_issues.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            help="One line per finding: record, field, severity, and explanation. Useful for sharing a task list.",
        )
    with col3:
        st.download_button(
            "Download filtered view (.xlsx)",
            dataframe_to_xlsx(display_df, sheet_name="Filtered data"),
            file_name=f"filtered_data_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            help=f"Only the {len(display_df):,} records currently shown in Step 4.",
        )

    with st.expander("Not sure which file to open first?"):
        st.markdown(
            """
            | What you want to do | Download or tab |
            |---|---|
            | Fix the records in Excel | Raw data with QA flags and messages |
            | Send a list of findings to a colleague | QA issues list |
            | Check only the records you filtered | Filtered view |
            | Read a short summary to share | Summary report tab |
            | See what the checker changed | What changed tab |
            | Give each enumerator their own file | Reports for each enumerator, further down |
            """
        )

    table_config = {
        column: st.column_config.Column(
            column,
            help=QA_FLAG_HELP_MAP[column],
            width="small",
        ) for column in QA_FLAG_COLUMNS if column in display_df.columns
    }
    st.subheader("Data preview")
    st.caption(
        "Column names match the downloaded files. Hover a qa_ column heading to read what it means."
    )
    st.dataframe(
        display_df.head(10),
        width="stretch",
        hide_index=True,
        column_config=table_config,
    )
    with st.expander(f"Open full filtered table ({len(display_df):,} records)"):
        st.dataframe(
            display_df,
            width="stretch",
            hide_index=True,
            column_config=table_config,
        )

    st.divider()

    tab_report, tab_issues, tab_corrections, tab_clean = st.tabs(
        ["Summary report", "All findings", "What changed", "Cleaned data"]
    )

    with tab_report:
        st.caption("A short overview you can paste into an email or report.")
        # The managed temporary directory is removed automatically after the report is read.
        with tempfile.TemporaryDirectory(prefix="m4s_qa_") as temp_dir:
            report_path = pathlib.Path(temp_dir) / "qa_report.md"
            generate_qa_report(clean_df, display_issues, correction_log, report_path)
            report_text = report_path.read_text(encoding="utf-8")
        st.markdown(report_text)
        st.download_button("Download QA report (Markdown)", report_text, file_name="qa_report.md")

    with tab_issues:
        st.caption(
            "Every finding from every check, one per line. Records without a finding are not listed here."
        )
        st.caption(f"Preview: first {min(10, len(issues))} of {len(issues):,} findings. Download the Excel workbook for the full issue list.")
        st.dataframe(display_issues.head(10), width='stretch', hide_index=True)
        st.download_button(
            "Download QA issues (.xlsx)",
            dataframe_to_xlsx(display_issues, sheet_name="QA issues"),
            file_name="qa_issues.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    with tab_corrections:
        st.caption(
            "Every automatic change, with the value before and after. Check anything that looks wrong "
            "in the original export."
        )
        st.caption(f"Preview: first {min(10, len(correction_log))} of {len(correction_log):,} correction-log rows. Download the Excel workbook for the full log.")
        st.dataframe(correction_log.head(10), width='stretch', hide_index=True)
        st.download_button(
            "Download correction log (.xlsx)",
            dataframe_to_xlsx(correction_log, sheet_name="Correction log"),
            file_name="correction_log.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    with tab_clean:
        st.caption(
            "The dataset after the automatic clean-ups. Keep this separate from your original download."
        )
        st.caption(f"Preview: first {min(10, len(clean_df))} of {len(clean_df):,} dataset rows. Download the Excel workbook for the complete dataset.")
        clean_preview = clean_df.head(10).copy()
        # Streamlit/PyArrow cannot infer one Arrow type for mixed numeric/text IDs.
        # Cast only the preview's mixed object columns; downloaded XLSX data stays unchanged.
        for column in clean_preview.columns:
            if clean_preview[column].dtype == object:
                clean_preview[column] = clean_preview[column].map(
                    lambda value: value if pd.isna(value) else str(value)
                )
        st.dataframe(clean_preview, width='stretch', hide_index=True)
        st.download_button(
            "Download clean dataset (.xlsx)",
            dataframe_to_xlsx(clean_df, sheet_name="Clean dataset"),
            file_name="clean_dataset.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    st.divider()
    with st.expander("Optional: review suggested name and site spellings"):
        st.caption(
            "Nothing in this section changes your upload. Only the suggestions you tick are applied, "
            "and only to a separate downloadable copy."
        )
        proposals = suggest_corrections(
            df,
            enumerator_threshold=enumerator_match_threshold,
            geography_threshold=geography_match_threshold,
        )
        if proposals.empty:
            st.success("No name or site spelling suggestions were found at the selected thresholds.")
        else:
            st.warning(
                "A similar spelling is not proof of the same person or place. Confirm each suggestion "
                "with the field team before approving it."
            )
            approved_ids = []
            for _, proposal in proposals.iterrows():
                label = (
                    f"{proposal['field']}: {proposal['current_value']!r} → "
                    f"{proposal['suggested_value']!r} "
                    f"({proposal['similarity']}% match; {proposal['affected_rows']} records)"
                )
                if st.checkbox(label, key=f"integrated_correction_{int(proposal['proposal_id'])}"):
                    approved_ids.append(int(proposal["proposal_id"]))
                st.caption(proposal["reason"])
            if st.button("Apply selected corrections to a review copy", type="primary", disabled=not approved_ids):
                reviewed_df, approved_log = apply_approved_corrections(df, proposals, approved_ids)
                st.success(f"Prepared a review copy with {len(approved_log)} row-level changes. The uploaded source remains unchanged.")
                st.caption(f"Preview: first {min(10, len(reviewed_df))} of {len(reviewed_df):,} rows. The download contains the full reviewed dataset.")
                st.dataframe(reviewed_df.head(10), width="stretch", hide_index=True)
                st.download_button(
                    "Download reviewed dataset (.xlsx)", dataframe_to_xlsx(reviewed_df, sheet_name="Reviewed dataset"),
                    file_name="m4s_corrected_reviewed.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="integrated_reviewed_dataset_download",
                )
                st.caption(f"Preview: first {min(10, len(approved_log))} of {len(approved_log):,} approved changes. The download contains the full audit log.")
                st.dataframe(approved_log.head(10), width="stretch", hide_index=True)
                st.download_button(
                    "Download approved-correction audit log (.xlsx)", dataframe_to_xlsx(approved_log, sheet_name="Approved corrections"),
                    file_name="m4s_approved_correction_log.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="integrated_reviewed_log_download",
                )

    st.divider()
    st.subheader("Optional: reports for each enumerator")
    st.caption(
        "Each download creates one report per enumerator for follow-up. These switches only choose "
        "what appears in those reports; the full findings stay unchanged."
    )
    include_gps_accuracy = st.checkbox(
        "Include GPS precision / accuracy checks in enumerator reports",
        value=True,
        key="enumerator_report_gps_accuracy",
    )
    include_site_distance = st.checkbox(
        "Include GPS site-distance warnings in enumerator reports",
        value=True,
        key="enumerator_report_site_distance",
    )
    include_text_formatting = st.checkbox(
        "Include Tetum / categorical capitalization checks in enumerator reports",
        value=True,
        key="enumerator_report_text_formatting",
        help="Flags inconsistent capitalization in low-cardinality text fields. Findings are suggestions, not automatic corrections.",
    )

    report_workbook = enumerator_error_workbook(
        clean_df, issues,
        include_gps_accuracy=include_gps_accuracy,
        include_site_distance=include_site_distance,
        include_text_formatting=include_text_formatting,
    )
    st.download_button(
        "Download enumerator error reports (Excel .xlsx)",
        data=report_workbook,
        file_name="m4s_enumerator_error_reports.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        help="One Excel workbook with a Summary sheet and one findings sheet per enumerator.",
    )
    st.caption("Most teams use this: one workbook, one sheet per enumerator.")

    report_zip = enumerator_error_zip(
        clean_df, issues,
        include_gps_accuracy=include_gps_accuracy,
        include_site_distance=include_site_distance,
        include_text_formatting=include_text_formatting,
    )
    st.download_button(
        "Download enumerator error logs (.zip)",
        data=report_zip,
        file_name="m4s_enumerator_error_logs.zip",
        mime="application/zip",
        help="A ZIP containing one .xlsx workbook per enumerator, with filters, a frozen header row, and clickable Kobo photo links where available.",
    )
    st.caption("Use this when each enumerator should receive their own separate file.")

    # This is the field team's working copy: preserve all source rows and columns,
    # then append only row-aligned ERROR messages. Warnings stay out of this export.
    raw_data_zip = enumerator_raw_data_zip(
        raw_df, issues,
        include_gps_accuracy=include_gps_accuracy,
        include_site_distance=include_site_distance,
        include_text_formatting=include_text_formatting,
    )
    st.download_button(
        "Download full raw data + error messages per enumerator (.zip)",
        data=raw_data_zip,
        file_name="m4s_enumerator_raw_data_with_errors.zip",
        mime="application/zip",
        help="One .xlsx workbook per enumerator with all original source rows and columns, plus one Error Message column containing errors only (no warnings). Blank source headers are labeled by Excel column position, without guessing their meaning. Headers are frozen and columns are filterable.",
    )
    st.caption(
        "Use this when an enumerator needs to see their original answers next to the error messages. "
        "Errors only; warnings are left out of this export."
    )

    with st.expander("What each flag column means"):
        st.markdown(
            """
            | Column | Plain meaning | When it appears |
            |---|---|---|
            | **qa_gps_precision_0** | No GPS fix | Precision recorded as 0.0 |
            | **qa_missing_coordinates** | Missing coordinates | Latitude or longitude blank |
            | **qa_outside_boundary** | Far from the site | More than 500 m from the site reference point |
            | **qa_duplicate_uuid** | Duplicate record | Same submission identifier twice |
            | **qa_species_logic** | Species answers | Species marked present without cover, or cover without the species |
            | **qa_missing_general_condition** | Missing condition | General condition answer blank |
            | **qa_coverage_mismatch** | Coverage does not add up | Species percentages differ from Epicover beyond tolerance |

            A cell holds **Yes** or **Review** when the finding applies to that record, and is empty
            otherwise.

            The **Message** column explains every finding for a record in one cell. Several
            explanations are separated by semicolons (;).

            A suggested review order:

            1. Read the summary in Step 2.
            2. Open the records flagged in Step 4, errors first.
            3. Compare each one with the original submission and the field protocol.
            4. Record what you changed and who approved it.
            5. Run the checks again on the corrected export.
            """
        )

    st.caption(
        f"File: {uploaded.name} | Records: {total} | Findings: {len(issues)} | "
        f"Automatic corrections: {len(correction_log)}"
    )
