import pandas as pd
import pytest

from csv_contract import validate_contract


def test_contract_flags_required_columns_allowed_values_ranges_and_duplicate_keys():
    frame = pd.DataFrame({
        "record_id": ["A", "B", "A"],
        "age": ["20", "-1", "130"],
        "consent": ["yes", "maybe", "no"],
    })
    contract = {
        "required_columns": ["record_id", "visit_date"],
        "key_columns": ["record_id"],
        "columns": {
            "age": {"type": "integer", "min": 0, "max": 120},
            "consent": {"allowed_values": ["yes", "no"]},
        },
    }

    issues = validate_contract(frame, contract)

    assert ((issues["column"] == "visit_date") & (issues["row_number"] == "")).any()
    assert ((issues["column"] == "consent") & (issues["row_number"] == 3)).any()
    assert ((issues["column"] == "age") & (issues["row_number"] == 3)).any()
    assert ((issues["column"] == "age") & (issues["row_number"] == 4)).any()
    assert ((issues["column"] == "record_id") & (issues["row_number"] == 2)).any()
    assert ((issues["column"] == "record_id") & (issues["row_number"] == 4)).any()


def test_contract_flags_non_numeric_and_invalid_dates():
    frame = pd.DataFrame({"age": ["unknown"], "visit_date": ["not-a-date"]})
    issues = validate_contract(frame, {
        "columns": {
            "age": {"type": "number"},
            "visit_date": {"type": "date"},
        }
    })

    assert len(issues) == 2
    assert set(issues["column"]) == {"age", "visit_date"}


def test_contract_rejects_unsupported_or_malformed_rules():
    with pytest.raises(ValueError, match="Unsupported contract keys"):
        validate_contract(pd.DataFrame({"id": ["1"]}), {"guess": True})
    with pytest.raises(ValueError, match="min.*max"):
        validate_contract(pd.DataFrame({"age": ["1"]}), {
            "columns": {"age": {"type": "number", "min": 10, "max": 1}}
        })


def test_empty_contract_returns_stable_issue_schema():
    findings = validate_contract(pd.DataFrame({"id": ["1"]}), {})
    assert list(findings.columns) == ["row_number", "column", "category", "severity", "message"]
    assert findings.empty
