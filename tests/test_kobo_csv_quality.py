import pandas as pd
import pytest

from kobo_csv_quality import (
    findings_summary,
    read_csv_bytes,
    structural_issues,
    validate_dataframe,
)


def test_read_csv_preserves_identifier_leading_zeroes():
    frame = read_csv_bytes(b"participant_id,answer\n0012,yes\n")
    assert frame.loc[0, "participant_id"] == "0012"


def test_read_csv_rejects_empty_file():
    with pytest.raises(ValueError, match="empty"):
        read_csv_bytes(b"")


def test_read_csv_rejects_duplicate_headers():
    with pytest.raises(ValueError, match="Duplicate column"):
        read_csv_bytes(b"id,id\n1,2\n")


def test_frictionless_accepts_well_formed_csv():
    assert structural_issues(b"participant_id,answer\n0012,yes\n", "survey.csv") == []


def test_finds_missing_cells_and_exact_duplicate_rows():
    frame = pd.DataFrame({"name": ["A", "", "A"], "score": ["3", "4", "3"]})
    findings = validate_dataframe(frame, outlier_checks=False)
    assert (findings["category"] == "missing").sum() == 1
    assert (findings["category"] == "duplicate").sum() == 2
    assert set(findings.loc[findings["category"] == "duplicate", "row_number"]) == {2, 4}


def test_summary_empty_findings():
    summary = findings_summary(pd.DataFrame(columns=["row_number", "column", "category", "severity", "message"]))
    assert summary == {"findings": 0, "errors": 0, "warnings": 0, "affected_rows": 0}
