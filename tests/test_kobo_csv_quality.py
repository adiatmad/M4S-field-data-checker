import pandas as pd
import pytest

from kobo_csv_quality import (
    QualityCheckError,
    findings_summary,
    read_csv_bytes,
    run_quality_checks,
    similar_text_value_issues,
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



def test_read_csv_rejects_blank_column_names():
    with pytest.raises(ValueError, match="column names cannot be blank"):
        read_csv_bytes(b"id,,answer\n1,extra,yes\n")


def test_row_numbers_are_positional_even_with_duplicate_dataframe_index():
    frame = pd.DataFrame(
        {"score": ["1", "2", "3", "4", "5", "6", "7", "100"],
         "note": ["ok", "ok", "ok", "ok", "ok", "ok", "ok", ""]},
        index=[0, 0, 0, 0, 0, 0, 0, 0],
    )
    findings = validate_dataframe(frame, duplicate_rows=False, outlier_checks=True)
    missing_rows = set(findings.loc[findings["category"] == "missing", "row_number"])
    outlier_rows = set(findings.loc[findings["category"] == "anomaly", "row_number"])
    assert missing_rows == {9}
    assert outlier_rows == {9}



def test_structural_check_crash_is_reported_and_value_stage_is_not_run(monkeypatch):
    import kobo_csv_quality as checker

    def fail_structure(*args, **kwargs):
        raise RuntimeError("internal details must not be shown to users")

    def unexpected_value_check(*args, **kwargs):
        pytest.fail("value checks must not run after structural validation fails")

    monkeypatch.setattr(checker, "structural_issues", fail_structure)
    monkeypatch.setattr(checker, "validate_dataframe", unexpected_value_check)

    with pytest.raises(QualityCheckError, match="structural validation") as exc:
        run_quality_checks(b"id\n1\n", "survey.csv", pd.DataFrame({"id": ["1"]}))

    assert exc.value.stage == "structural validation"
    assert "internal details" not in str(exc.value)


def test_value_check_crash_is_reported_without_returning_partial_findings(monkeypatch):
    import kobo_csv_quality as checker

    monkeypatch.setattr(checker, "structural_issues", lambda *args, **kwargs: [])

    def fail_values(*args, **kwargs):
        raise RuntimeError("internal details must not be shown to users")

    monkeypatch.setattr(checker, "validate_dataframe", fail_values)

    with pytest.raises(QualityCheckError, match="value validation") as exc:
        run_quality_checks(b"id\n1\n", "survey.csv", pd.DataFrame({"id": ["1"]}))

    assert exc.value.stage == "value validation"
    assert "internal details" not in str(exc.value)


def test_run_quality_checks_applies_optional_contract():
    data = b"record_id,consent\n001,yes\n002,maybe\n"
    frame = read_csv_bytes(data)
    findings = run_quality_checks(
        data, "survey.csv", frame,
        duplicate_rows=False,
        outlier_checks=False,
        contract={
            "required_columns": ["record_id", "consent"],
            "key_columns": ["record_id"],
            "columns": {"consent": {"allowed_values": ["yes", "no"]}},
        },
    )
    contract_findings = findings[findings["category"] == "contract"]
    assert len(contract_findings) == 1
    assert contract_findings.iloc[0]["column"] == "consent"
    assert contract_findings.iloc[0]["row_number"] == 3

def test_contract_rule_for_missing_column_is_reported_instead_of_skipped():
    data = b"record_id,consent\\n001,yes\\n"
    frame = read_csv_bytes(data)

    findings = run_quality_checks(
        data, "survey.csv", frame,
        duplicate_rows=False,
        outlier_checks=False,
        contract={"columns": {"consnet": {"allowed_values": ["yes", "no"]}}},
    )

    missing_column = findings[
        (findings["category"] == "contract")
        & (findings["column"] == "consnet")
    ]
    assert len(missing_column) == 1
    assert missing_column.iloc[0]["row_number"] == ""
    assert "configured checks could not run" in missing_column.iloc[0]["message"]



def test_similar_text_values_are_review_warnings_and_do_not_mutate_input():
    frame = pd.DataFrame({"village": ["Sabuli", "Sabul i", "Metinaro"], "record_id": ["001", "002", "003"]})
    before = frame.copy(deep=True)

    findings = similar_text_value_issues(frame, threshold=85)

    assert not findings.empty
    assert set(findings["category"]) == {"value_variant"}
    assert set(findings["severity"]) == {"warning"}
    assert set(findings["row_number"]) == {2, 3}
    pd.testing.assert_frame_equal(frame, before)


def test_similar_text_values_skip_identifier_columns_and_numeric_values():
    frame = pd.DataFrame({"record_id": ["ABC123", "ABC12B"], "score": ["100", "101"]})
    assert similar_text_value_issues(frame).empty


def test_similar_text_values_can_be_enabled_through_pipeline():
    data = b"village,record_id\nSabuli,001\nSabul i,002\n"
    frame = read_csv_bytes(data)
    findings = run_quality_checks(data, "survey.csv", frame,
                                  duplicate_rows=False, outlier_checks=False,
                                  similar_text_values=True)
    assert (findings["category"] == "value_variant").any()


def test_similar_text_values_detect_whitespace_and_case_variants():
    frame = pd.DataFrame({"village": ["Sabuli", " sabuli "]})

    findings = similar_text_value_issues(frame)

    assert set(findings["row_number"]) == {2, 3}
    assert (findings["category"] == "value_variant").all()
