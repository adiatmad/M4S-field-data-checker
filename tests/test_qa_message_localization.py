import pandas as pd

from qa_message_localization import (
    format_qa_error_message,
    localize_qa_issue_messages,
)


def test_recognized_survey_error_displays_tetum_then_exact_english_original():
    original = "Missing GPS coordinates"
    result = format_qa_error_message(original, "gps", "error")
    assert result == "Koordenada GPS falta (Missing GPS coordinates)"


def test_dynamic_species_error_preserves_species_name_and_original():
    original = "Halophila ovalis marked present but no % cover recorded"
    result = format_qa_error_message(original, "species", "error")
    assert result == (
        "Espésie Halophila ovalis marka hanesan prezente, maibé la rejista % kober "
        "(Halophila ovalis marked present but no % cover recorded)"
    )


def test_localization_is_presentation_only_and_does_not_mutate_source_issues():
    issues = pd.DataFrame([
        {"category": "gps", "severity": "error", "message": "Missing GPS coordinates"},
        {"category": "gps", "severity": "warning", "message": "GPS precision 12.0 m: below recommended accuracy"},
        {"category": "schema", "severity": "error", "message": "Required seagrass species-selection fields are missing from the export."},
        {"category": "species", "severity": "error", "message": "New unreviewed survey rule"},
    ])
    localized = localize_qa_issue_messages(issues)

    assert localized.loc[0, "message"] == "Koordenada GPS falta (Missing GPS coordinates)"
    assert localized.loc[1, "message"] == issues.loc[1, "message"]
    assert localized.loc[2, "message"] == issues.loc[2, "message"]
    assert localized.loc[3, "message"] == issues.loc[3, "message"]
    pd.testing.assert_frame_equal(issues, pd.DataFrame([
        {"category": "gps", "severity": "error", "message": "Missing GPS coordinates"},
        {"category": "gps", "severity": "warning", "message": "GPS precision 12.0 m: below recommended accuracy"},
        {"category": "schema", "severity": "error", "message": "Required seagrass species-selection fields are missing from the export."},
        {"category": "species", "severity": "error", "message": "New unreviewed survey rule"},
    ]))


def test_technical_and_unrecognized_messages_remain_english():
    assert format_qa_error_message("Unsupported Kobo form schema", "schema", "error") == "Unsupported Kobo form schema"
    assert format_qa_error_message("Missing GPS coordinates", "gps", "warning") == "Missing GPS coordinates"
    assert format_qa_error_message("A new error message", "logic", "error") == "A new error message"


def test_mandatory_field_translation_keeps_field_name_and_english_original():
    original = "Mandatory field 'Quadrat Number' is missing or blank"
    assert format_qa_error_message(original, "logic", "error") == (
        "Koluna obrigatóriu 'Quadrat Number' falta ka mamuk "
        "(Mandatory field 'Quadrat Number' is missing or blank)"
    )



def test_enumerator_raw_error_export_uses_tetum_plus_english_without_changing_columns():
    from enumerator_raw_exports import build_enumerator_raw_exports

    raw = pd.DataFrame({"Naran Koletor": ["Ana"], "answer": ["x"]})
    issues = pd.DataFrame([{
        "row_index": 0, "uuid": "u1", "category": "gps", "field": "_Local GPS",
        "severity": "error", "message": "Missing GPS coordinates",
    }])
    exported = build_enumerator_raw_exports(raw, issues)["Ana"]

    assert exported.columns.tolist() == ["Naran Koletor", "answer", "Error Message"]
    assert exported.loc[0, "Error Message"] == "Koordenada GPS falta (Missing GPS coordinates)"


def test_enumerator_findings_localize_only_recognized_survey_errors():
    from enumerator_reports import build_enumerator_error_logs

    source = pd.DataFrame({"Collector Name": ["Ana"], "Quadrat Photo_URL": ["https://example.test/photo"]})
    issues = pd.DataFrame([
        {"row_index": 0, "uuid": "u1", "category": "gps", "field": "_Local GPS",
         "severity": "error", "message": "Missing GPS coordinates"},
        {"row_index": 0, "uuid": "u1", "category": "schema", "field": "schema",
         "severity": "error", "message": "Unsupported Kobo form schema"},
    ])
    logs = build_enumerator_error_logs(source, issues)
    messages = logs["Ana"]["message"].tolist()

    assert messages == [
        "Koordenada GPS falta (Missing GPS coordinates)",
        "Unsupported Kobo form schema",
    ]
    assert issues.loc[0, "message"] == "Missing GPS coordinates"
