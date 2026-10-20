"""Full-record enumerator exports with one row-aligned error-message column."""

from __future__ import annotations

import io
import re
import zipfile

import pandas as pd

from enumerator_reports import filter_enumerator_report_issues
from qa_message_localization import format_qa_error_message

ENUMERATOR_HEADERS = ("Naran Koletor", "Collector Name", "Enumerator", "enumerator")
ERROR_COLUMN = "Error Message"


def _find_column(columns, candidates):
    normalized = {
        re.sub(r"\s+", " ", str(column)).strip().casefold(): column
        for column in columns
    }
    for candidate in candidates:
        key = re.sub(r"\s+", " ", candidate).strip().casefold()
        if key in normalized:
            return normalized[key]
    return None


def _excel_column_name(index: int) -> str:
    """Convert a zero-based column index to its Excel letter (0 -> A, 70 -> BS)."""
    number = index + 1
    letters = ""
    while number:
        number, remainder = divmod(number - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


def _make_blank_headers_explicit(columns):
    """Label blank or pandas-generated empty headers by position; never guess meaning."""
    output = []
    for index, column in enumerate(columns):
        if column is None or (isinstance(column, str) and not column.strip()):
            output.append(f"Unnamed: {_excel_column_name(index)}")
        elif isinstance(column, str) and re.fullmatch(r"Unnamed:\s*\d+(?:\.\d+)?", column):
            # pandas labels empty Excel header cells as "Unnamed: 70"; use the
            # stable Excel letter instead so reviewers can locate the column.
            output.append(f"Unnamed: {_excel_column_name(index)}")
        else:
            output.append(column)
    return output


def build_enumerator_raw_exports(
    raw_df: pd.DataFrame,
    issues: pd.DataFrame,
    *,
    include_gps_accuracy: bool = True,
    include_site_distance: bool = True,
    include_text_formatting: bool = True,
) -> dict[str, pd.DataFrame]:
    """Preserve all source rows/columns and append only row-aligned error messages.

    Warnings and informational findings are deliberately excluded. Blank source
    headers are given positional placeholder names (for example, Unnamed: BS)
    so exported CSVs do not contain unlabeled columns; no domain meaning is inferred.
    """
    if raw_df is None:
        raise ValueError("Raw source data is required.")
    result = raw_df.copy()
    result.columns = _make_blank_headers_explicit(result.columns)
    if ERROR_COLUMN in result.columns:
        raise ValueError(
            f"The source already contains a {ERROR_COLUMN!r} column; refusing to overwrite source data."
        )

    filtered = filter_enumerator_report_issues(
        issues,
        include_gps_accuracy=include_gps_accuracy,
        include_site_distance=include_site_distance,
        include_text_formatting=include_text_formatting,
    )
    if not filtered.empty and "severity" in filtered.columns:
        filtered = filtered.loc[
            filtered["severity"].astype("string").str.casefold().eq("error")
        ]

    result[ERROR_COLUMN] = ""
    if not filtered.empty and {"row_index", "message"}.issubset(filtered.columns):
        messages = {}
        for _, issue in filtered.iterrows():
            idx = issue.get("row_index")
            if pd.isna(idx) or idx not in result.index:
                # A schema-level error without a source-row reference cannot be
                # safely attached to a particular raw record.
                continue
            message = str(issue.get("message", "") or "").strip()
            message = format_qa_error_message(message, issue.get("category"), issue.get("severity"))
            if message:
                messages.setdefault(idx, []).append(message)
        for idx, items in messages.items():
            result.at[idx, ERROR_COLUMN] = " | ".join(dict.fromkeys(items))

    enumerator_col = _find_column(result.columns, ENUMERATOR_HEADERS)
    if enumerator_col is None:
        # Do not append a helper column to the raw export. Keep all records in a
        # single explicit bucket when the source has no recognized enumerator field.
        names = pd.Series("Unknown enumerator", index=result.index)
    else:
        names = result[enumerator_col].fillna("").astype(str).str.strip()
        names = names.mask(names.eq(""), "Unknown enumerator")

    exports = {}
    for name in sorted(names.unique(), key=str.casefold):
        exports[name] = result.loc[names.eq(name)].copy()
    return exports


def enumerator_raw_data_zip(raw_df, issues, **options) -> bytes:
    """Create one Excel-friendly, error-only CSV per enumerator."""
    exports = build_enumerator_raw_exports(raw_df, issues, **options)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for index, (name, frame) in enumerate(exports.items(), start=1):
            safe = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._") or "enumerator"
            archive.writestr(
                f"{index:02d}_{safe}_raw_with_errors.csv",
                "\ufeff" + frame.to_csv(index=False, sep=";"),
            )
    return buffer.getvalue()
