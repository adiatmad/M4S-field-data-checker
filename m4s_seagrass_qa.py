"""
M4S Seagrass Monitoring (Metinaro, Timor-Leste) — QA Pipeline
================================================================
Turns a raw KoboToolbox export into an analysis-ready dataset.

Pipeline stages (run in order, each is a plain function so you can
call them one at a time from a notebook while debugging):

    1. load_data          -> read the raw .xlsx, keep an untouched copy
    2. standardize         -> parse dates, trim whitespace, fix dtypes
    3. validate             -> run every QA rule, collect issues
    4. correct               -> apply ONLY the safe, reversible corrections
    5. generate_qa_report -> one Markdown report summarizing everything
    6. export_outputs      -> write clean dataset + correction log + raw copy

Run directly:  python3 m4s_seagrass_qa.py raw_export.xlsx
Outputs land in ./output/

Design notes for future-you (see accompanying README for the full
rationale) — this is intentionally specific to the M4S Seagrass form
schema below, not a generic Kobo cleaner. Column names are matched
literally, not by position, so it survives Kobo re-ordering columns
between exports, but it WILL break if a question is renamed. That's
by design: a silent schema change on an ecological dataset is a
"stop and look" event, not a "guess and continue" event, so the
pipeline hard-fails with a clear message instead.
"""

import sys
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import numpy as np
from rapidfuzz import fuzz, process

# ----------------------------------------------------------------------
# PROJECT-SPECIFIC REFERENCE DATA
# (This is the part that's genuinely M4S/Metinaro-specific. Change
#  here, not in the logic below, when the project scope changes.)
# ----------------------------------------------------------------------

# Canonical seagrass species list (from the form's own choice list —
# these are the 14 species the questionnaire was built around).
SPECIES_LIST = [
    "Halophila ovalis", "Halophila minor", "Halodule pinifolia",
    "Halodule uninervis", "Halophila decipiens", "Halophila beccarii",
    "Halophila spinulosa", "Enhalus acoroides", "Thalassia hemprichii",
    "Cymodocea rotundata", "Cymodocea serrulata", "Syringodium isoetifolium",
    "Ruppia maritima", "Thalassodendron ciliatum",
]

# Canonical admin geography for this project. Metinaro / Sabuli is the
# ONLY valid combination for this pilot — anything else is either a
# typo or a genuine out-of-scope submission that needs a human look.
CANONICAL_ADMIN_POST = "Metinaro"
CANONICAL_VILLAGE = "Sabuli"

# GPS sanity boundary. Centroid + radius rather than a bounding box,
# because the survey site is a compact coastal flat, not a rectangle.
# Values below were derived from this dataset's own distribution
# (see README) — 99% of points fall within ~320m of the centroid;
# one point sat at 2.9km. Recompute per season if the survey area
# changes.
SITE_CENTROID = (-8.51967, 125.7174723)   # (lat, lon), WGS84
SITE_RADIUS_M = 500                        # flag anything further out

# Fuzzy-match thresholds (0-100, rapidfuzz token_sort_ratio scale)
ENUMERATOR_MATCH_THRESHOLD = 85
GEO_MATCH_THRESHOLD = 80

# GPS quality thresholds
GPS_PRECISION_WARN_M = 10     # Kobo's own reported horizontal accuracy
GPS_PRECISION_ERROR_M = 30

# Survey duration sanity (seconds), based on this form's own distribution
DURATION_TOO_FAST_S = 60          # can't credibly complete the form
DURATION_LONG_SESSION_S = 8 * 3600  # likely a form left open/resumed


# ----------------------------------------------------------------------
# STAGE 1 — LOAD
# ----------------------------------------------------------------------

def load_data(path: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Read the raw Kobo export. Returns (raw_df, working_df).

    raw_df is never mutated again — it's what "preserve the original
    raw data" in the brief refers to. working_df is what every later
    stage touches.
    """
    raw = pd.read_excel(path)
    required = [
        "start", "end", "Collector Name", "Date and time",
        "Administration Post", "Village", "_Local GPS_latitude",
        "_Local GPS_longitude", "_Local GPS_precision", "_uuid",
    ]
    missing = [c for c in required if c not in raw.columns]
    if missing:
        raise ValueError(
            f"Form schema changed — missing expected columns: {missing}. "
            "Stopping rather than guessing; update SPECIES_LIST/column "
            "references at the top of this file if the form was "
            "intentionally redesigned."
        )
    return raw, raw.copy()


# ----------------------------------------------------------------------
# STAGE 2 — STANDARDIZE
# (type coercion, whitespace, nothing that changes meaning yet)
# ----------------------------------------------------------------------

def _strip_all_strings(df: pd.DataFrame) -> pd.DataFrame:
    obj_cols = df.select_dtypes(include="object").columns
    for c in obj_cols:
        df[c] = df[c].apply(lambda v: v.strip() if isinstance(v, str) else v)
        # collapse internal double spaces too
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
    # numeric coercion for everything that should be numeric
    numeric_like = [c for c in df.columns if "(%)" in c or c in (
        "Water Level (Cm)", "_Local GPS_latitude", "_Local GPS_longitude",
        "_Local GPS_altitude", "_Local GPS_precision",
    )]
    for c in numeric_like:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


# ----------------------------------------------------------------------
# STAGE 3 — VALIDATE
# Every rule appends rows to `issues`: one row per (record, problem).
# severity: "error" (blocks analysis use) | "warning" (flag for review)
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
    # duplicate coordinates across different records (possible "forgot to
    # refresh GPS" — flagged, never auto-corrected)
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
    """Every standalone %-cover field (algal, epicover, sedimentation) in 0-100."""
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
                 "Quadrat Number", "Presence of Seagrass"]
    issues = []
    for i, r in df.iterrows():
        for f in mandatory:
            if f in df.columns and pd.isna(r[f]):
                issues.append(_new_issue(i, r["_uuid"], "logic", f, "error",
                                          f"Mandatory field '{f}' is missing"))
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
    for i, r in df.iterrows():
        if "Quadrat Photo_URL" in df.columns and pd.isna(r["Quadrat Photo_URL"]):
            issues.append(_new_issue(i, r["_uuid"], "photo", "Quadrat Photo_URL", "error",
                                      "No quadrat photo attached"))
    return issues


def validate_geography(df):
    """Flag admin post / village values that don't match the canonical
    project geography closely enough to be an obvious typo — these are
    NEVER auto-corrected (only 'safe' string cleanup is), because a
    genuinely different village is a real, meaningful data point."""
    issues = []
    for i, r in df.iterrows():
        for field, canon in [("Administration Post", CANONICAL_ADMIN_POST),
                              ("Village", CANONICAL_VILLAGE)]:
            v = r.get(field)
            if pd.isna(v):
                continue
            score = fuzz.token_sort_ratio(str(v).lower(), canon.lower())
            if v != canon and score < GEO_MATCH_THRESHOLD:
                issues.append(_new_issue(i, r["_uuid"], "geography", field, "warning",
                                          f"'{v}' does not closely match expected '{canon}' — verify, don't assume typo"))
    return issues


def validate_duplicate_submissions(df):
    issues = []
    dup = df.duplicated(subset=["_uuid"], keep=False)
    for i, r in df[dup].iterrows():
        issues.append(_new_issue(i, r["_uuid"], "duplicate", "_uuid", "error",
                                  "Duplicate _uuid — same submission ingested twice"))
    # same collector + transect + quadrat + date submitted more than once
    logical_key = ["Collector Name", "Transect Number", "Quadrat Number", "Date and time"]
    if all(k in df.columns for k in logical_key):
        dup2 = df.duplicated(subset=logical_key, keep=False)
        for i, r in df[dup2].iterrows():
            issues.append(_new_issue(i, r["_uuid"], "duplicate", "combo", "warning",
                                      "Same collector/transect/quadrat/date as another record — possible re-entry"))
    return issues


def validate(df) -> pd.DataFrame:
    all_issues = []
    for fn in (validate_gps, validate_species_logic, validate_percent_fields,
               validate_mandatory_fields, validate_timestamps, validate_photos,
               validate_geography, validate_duplicate_submissions):
        all_issues.extend(fn(df))
    return pd.DataFrame(all_issues)


# ----------------------------------------------------------------------
# STAGE 4 — CORRECT
# Only SAFE, reversible corrections happen here. Every change is logged
# with before/after so it's auditable. Nothing scientific is ever
# touched automatically (GPS, % cover, water depth, species presence).
# ----------------------------------------------------------------------

def _fuzzy_canonicalize(series: pd.Series, threshold: int) -> tuple[pd.Series, dict]:
    """Cluster near-identical free-text values (case/underscore/spacing
    variants of the same name) and map each cluster to its most frequent
    exact spelling. Returns (corrected_series, {original: canonical})."""
    values = series.dropna().unique().tolist()
    # normalize underscores -> spaces before fuzzy comparison, since
    # that's a formatting artifact, not a spelling difference
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
        # Prefer "Title Case With Spaces" over "snake_case" or
        # "all lowercase" — underscore/lowercase forms are a system
        # artifact (e.g. a username), not the person's real name
        # formatting, regardless of how often they show up.
        score = 0
        if "_" not in v:
            score += 2
        if v != v.lower():
            score += 1
        return score

    mapping = {}
    for cluster in clusters:
        # canonical = best-formatted spelling first, most frequent as
        # tiebreaker
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

    # --- Safe correction 1: enumerator name normalization (case,
    # underscores, extra whitespace collapsed to one canonical spelling
    # per person, chosen as their most-used exact spelling) ---
    corrected, mapping = _fuzzy_canonicalize(df["Collector Name"], ENUMERATOR_MATCH_THRESHOLD)
    changed_mask = (df["Collector Name"] != corrected) & df["Collector Name"].notna()
    log_change(changed_mask, "Collector Name", mapping, "enumerator_name_normalization")
    df["Collector Name"] = corrected

    # Any name that's STILL snake_case at this point had no duplicate
    # variant to cluster against — it's just a raw-formatting artifact
    # (e.g. a Kobo username used as the free-text answer). Reformat to
    # "Title Case With Spaces": pure capitalization/spacing, so it's
    # safe per policy even though no clustering was involved.
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

    # --- Safe correction 2: obvious capitalization/whitespace typos in
    # Administration Post ONLY when they fuzzy-match the single known
    # canonical value tightly (>= ENUMERATOR_MATCH_THRESHOLD, i.e. a
    # near-exact string match, not a "different place" match) ---
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
# STAGE 5 — QA REPORT
# ----------------------------------------------------------------------

def generate_qa_report(df, issues, correction_log, out_path):
    total = len(df)
    err = issues[issues.severity == "error"]
    warn = issues[issues.severity == "warning"]
    flagged_records = issues.row_index.nunique() if len(issues) else 0
    passed = total - flagged_records

    lines = []
    lines.append(f"# M4S Seagrass QA Report — {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
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
# STAGE 6 — EXPORT
# ----------------------------------------------------------------------

def export_outputs(raw_df, clean_df, issues, correction_log, out_dir):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_df.to_csv(out_dir / "raw_preserved.csv", index=False)
    clean_df.to_csv(out_dir / "clean_dataset.csv", index=False)
    issues.to_csv(out_dir / "qa_issues.csv", index=False)
    correction_log.to_csv(out_dir / "correction_log.csv", index=False)
    generate_qa_report(clean_df, issues, correction_log, out_dir / "qa_report.md")


# ----------------------------------------------------------------------
# ENTRY POINT
# ----------------------------------------------------------------------

def run(input_path: str, out_dir: str = "output"):
    raw_df, df = load_data(input_path)
    df = standardize(df)
    issues = validate(df)                 # validate BEFORE correcting, so the
                                            # report reflects what came in raw
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
