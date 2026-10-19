"""Full-record enumerator exports that preserve the uploaded Kobo columns."""

from __future__ import annotations

import io
import re
import zipfile

import pandas as pd

from enumerator_reports import filter_enumerator_report_issues

# Labels used by the current M4S Kobo form when a species-cover question is absent
# from an export. Ho is explicitly included because field reviewers identify it by
# this abbreviation in the survey workflow.
SPECIES_COVER_SOURCE_HEADERS = {
    "Halophila ovalis": "Persentajen (Ho) Halophila ovalis (%)",
    "Halophila minor": "Persentajen (Hm) Halophila minor (%)",
    "Halodule pinifolia": "Persentajen Halodule pinifolia (%)",
    "Halodule uninervis": "Persentajen (Hu) Halodule uninervis (%)",
    "Halophila decipiens": "Persentajen (Hd) Halophila decipiens (%)",
    "Halophila beccarii": "Persentajen (Hb) Halophila beccarii (%)",
    "Halophila spinulosa": "Persentajen (Hs) Halophila spinulosa (%)",
    "Enhalus acoroides": "Persentajen (Ea) Enhalus acoroides (%)",
    "Thalassia hemprichii": "Persentajen (Th) Thalassia hemprichii (%)",
    "Cymodocea rotundata": "Persentajen (Cr) Cymodocea rotundata (%)",
    "Cymodocea serrulata": "Persentajen (Cs) Cymodocea serrulata (%)",
    "Syringodium isoetifolium": "Persentajen (Si) Syringodium isoetifolium (%)",
    "Ruppia maritima": "Persentajen (Rm) Ruppia maritima (%)",
    "Thalassodendron ciliatum": "Persentajen (Tc) Thalassodendron ciliatum (%)",
}

ENUMERATOR_HEADERS = ("Naran Koletor", "Collector Name", "Enumerator", "enumerator")
CANONICAL_PERCENT_RE = re.compile(r"^Percent (.+) \(%\)$")


def _find_column(columns, candidates):
    normalized = {re.sub(r"\s+", " ", str(column)).strip().casefold(): column for column in columns}
    for candidate in candidates:
        key = re.sub(r"\s+", " ", candidate).strip().casefold()
        if key in normalized:
            return normalized[key]
    return None


def build_enumerator_raw_exports(
    raw_df: pd.DataFrame,
    issues: pd.DataFrame,
    *,
    include_gps_accuracy: bool = True,
    include_site_distance: bool = True,
    include_text_formatting: bool = True,
) -> dict[str, pd.DataFrame]:
    """Preserve every source column and row, adding actionable QA columns per enumerator."""
    if raw_df is None:
        raise ValueError("Raw source data is required.")
    result = raw_df.copy()
    filtered = filter_enumerator_report_issues(
        issues, include_gps_accuracy=include_gps_accuracy,
        include_site_distance=include_site_distance,
        include_text_formatting=include_text_formatting,
    )
    # When a selected species has no cover question in the export, add an empty
    # entry column so the field team has an actual place to enter the missing value.
    if not filtered.empty and {"category", "field", "message"}.issubset(filtered.columns):
        missing_cover = filtered[
            filtered["category"].eq("species")
            & filtered["message"].astype("string").str.contains(
                "percentage-cover column is missing from the export", case=False, na=False
            )
        ]
        for field in missing_cover["field"].dropna().astype(str).unique():
            match = CANONICAL_PERCENT_RE.match(field)
            if not match:
                continue
            species = match.group(1)
            source_header = SPECIES_COVER_SOURCE_HEADERS.get(species, field)
            if _find_column(result.columns, [source_header, field]) is None:
                result[source_header] = pd.NA

    for column in ("QA Message", "QA Fields to Check", "QA Severity"):
        result[column] = ""

    if not filtered.empty:
        messages = {}
        fields = {}
        severities = {}
        for _, issue in filtered.iterrows():
            idx = issue.get("row_index")
            if pd.isna(idx) or idx not in result.index:
                continue
            message = str(issue.get("message", "") or "").strip()
            field = str(issue.get("field", "") or "").strip()
            severity = str(issue.get("severity", "") or "").strip().upper()
            if message:
                messages.setdefault(idx, []).append(message)
            if field and field not in fields.setdefault(idx, []):
                fields[idx].append(field)
            if severity:
                severities.setdefault(idx, set()).add(severity)
        for idx, items in messages.items():
            result.at[idx, "QA Message"] = " | ".join(dict.fromkeys(items))
        for idx, items in fields.items():
            result.at[idx, "QA Fields to Check"] = "; ".join(items)
        for idx, items in severities.items():
            order = [value for value in ("ERROR", "WARNING", "INFO") if value in items]
            result.at[idx, "QA Severity"] = "; ".join(order)

    enumerator_col = _find_column(result.columns, ENUMERATOR_HEADERS)
    if enumerator_col is None:
        result["QA Enumerator"] = "Unknown enumerator"
        enumerator_col = "QA Enumerator"
    names = result[enumerator_col].fillna("").astype(str).str.strip()
    names = names.mask(names.eq(""), "Unknown enumerator")
    exports = {}
    for name in sorted(names.unique(), key=str.casefold):
        exports[name] = result.loc[names.eq(name)].copy()
    return exports


def enumerator_raw_data_zip(raw_df, issues, **options) -> bytes:
    """Create one Excel-friendly CSV per enumerator, retaining the complete raw row."""
    exports = build_enumerator_raw_exports(raw_df, issues, **options)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for index, (name, frame) in enumerate(exports.items(), start=1):
            safe = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._") or "enumerator"
            # Semicolon delimiter + BOM supports direct double-click opening in Excel
            # on common Windows regional settings, consistent with the existing error ZIP.
            archive.writestr(
                f"{index:02d}_{safe}_raw_with_QA.csv",
                "\ufeff" + frame.to_csv(index=False, sep=";"),
            )
    return buffer.getvalue()
