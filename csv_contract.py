"""Explicit, user-authored contracts for generic CSV quality checks.

The contract is deliberately declarative: it validates only rules supplied by the
survey owner and never infers ecological or survey semantics.
"""
from __future__ import annotations

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
            issues.append(_issue(
                "", column,
                "Column referenced by the contract is missing; its configured checks could not run."
            ))
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
