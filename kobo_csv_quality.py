"""Local-first, generic CSV quality checks for KoboToolbox exports."""
from __future__ import annotations

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


def read_csv_bytes(data: bytes, *, encoding: str = "utf-8-sig") -> pd.DataFrame:
    """Read CSV bytes without silently converting identifier strings to numbers."""
    if not data:
        raise ValueError("The uploaded CSV is empty.")
    try:
        text = data.decode(encoding)
        header = next(csv.reader(text.splitlines()), [])
    except UnicodeDecodeError as exc:
        raise ValueError(f"Could not decode this CSV as {encoding}: {exc}") from exc
    if not header:
        raise ValueError("The CSV has no columns.")
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


def validate_dataframe(
    df: pd.DataFrame,
    *,
    missing_tokens: tuple[str, ...] = ("", "NA", "N/A", "NULL", "null"),
    duplicate_rows: bool = True,
    outlier_checks: bool = True,
) -> pd.DataFrame:
    """Apply generic checks; row_number is the 1-based CSV data row (header excluded)."""
    issues: list[dict] = []
    normalized_missing = {token.casefold() for token in missing_tokens}
    for column in df.columns:
        values = df[column].astype("string")
        missing = values.str.strip().str.casefold().isin(normalized_missing)
        for idx in df.index[missing]:
            issues.append(_issue(int(df.index.get_loc(idx)) + 2, column, "missing", "warning",
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
            for idx in valid.index[(valid < low) | (valid > high)]:
                issues.append(_issue(int(df.index.get_loc(idx)) + 2, column, "anomaly", "warning",
                                     f"Numeric value {values.loc[idx]} is outside the IQR screening range "
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
