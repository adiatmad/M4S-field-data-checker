"""Local-first, generic CSV quality checks for KoboToolbox exports."""
from __future__ import annotations

import csv
from io import BytesIO
from pathlib import Path
import tempfile
from typing import Any
import re

import numpy as np
from rapidfuzz import fuzz
import pandas as pd
import pandera.pandas as pa
from frictionless import validate as frictionless_validate
from csv_contract import validate_contract


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
            value = str(raw).strip()
            if value.casefold() in missing_tokens or len(value) < 3 or value.startswith(("http://", "https://")):
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
