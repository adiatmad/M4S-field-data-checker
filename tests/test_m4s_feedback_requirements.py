import io
import zipfile

import pandas as pd

from m4s_seagrass_qa import (
    SPECIES_LIST,
    _strip_all_strings,
    add_qa_columns,
    build_enumerator_error_logs,
    correct,
    standardize,
    validate,
    enumerator_error_zip,
    filter_enumerator_report_issues,
    validate_coverage_mismatch,
    validate_seagrass_general_condition,
    validate_species_logic,
)


def test_present_species_requires_its_percentage_even_if_column_is_missing():
    species = SPECIES_LIST[0]
    frame = pd.DataFrame({
        "_uuid": ["u1"],
        "Presence of Seagrass": ["Yes"],
        f"Seagrass species present in the Quadrat/{species}": [1],
    })
    issues = pd.DataFrame(validate_species_logic(frame))
    assert len(issues) == 1
    assert "percentage-cover column is missing" in issues.iloc[0]["message"]


def test_yes_without_any_selected_species_is_critical_error():
    frame = pd.DataFrame({
        "_uuid": ["u1"],
        "Presence of Seagrass": ["Yes"],
        f"Seagrass species present in the Quadrat/{SPECIES_LIST[0]}": [0],
    })
    issues = pd.DataFrame(validate_species_logic(frame))
    assert any("Missing seagrass species" in message for message in issues["message"])
    assert issues.loc[issues["message"].str.contains("Missing seagrass species"), "severity"].iloc[0] == "error"


def test_missing_or_blank_general_condition_is_reported():
    missing_column = pd.DataFrame({"_uuid": ["u1"]})
    missing = validate_seagrass_general_condition(missing_column)
    assert missing[0]["category"] == "schema"
    assert "general condition" in missing[0]["message"].lower()

    blank_value = pd.DataFrame({"_uuid": ["u1"], "General Condition": ["  "]})
    blank = validate_seagrass_general_condition(blank_value)
    assert len(blank) == 1
    assert blank[0]["category"] == "condition"


def test_species_sum_mismatch_is_reported_with_tolerance():
    species = SPECIES_LIST[0]
    frame = pd.DataFrame({
        "_uuid": ["u1"],
        f"Percent {species} (%)": [20.0],
        "Epicover Percentage (%)": [40.0],
    })
    issues = validate_coverage_mismatch(frame)
    assert len(issues) == 1
    assert "sum to 20.0%" in issues[0]["message"]


def test_enumerator_exports_include_photo_links_and_are_sorted():
    frame = pd.DataFrame({
        "Collector Name": ["Zara", "Ari"],
        "Quadrat Photo_URL": ["https://kobo.example/img/1", "https://kobo.example/img/2"],
        "_uuid": ["u1", "u2"],
    }, index=[0, 1])
    issues = pd.DataFrame([
        {"row_index": 0, "uuid": "u1", "category": "gps", "field": "_Local GPS_precision",
         "severity": "warning", "message": "GPS precision 12 m: below recommended accuracy"},
        {"row_index": 1, "uuid": "u2", "category": "species", "field": "species",
         "severity": "error", "message": "Missing seagrass species"},
    ])
    logs = build_enumerator_error_logs(frame, issues)
    assert list(logs) == ["Ari", "Zara"]
    assert logs["Ari"].iloc[0]["photo_url"] == "https://kobo.example/img/2"
    archive = zipfile.ZipFile(io.BytesIO(enumerator_error_zip(frame, issues)))
    assert len(archive.namelist()) == 2
    csv_text = archive.read(archive.namelist()[0]).decode("utf-8")
    assert "photo_url" in csv_text
    assert "https://kobo.example/img/2" in csv_text


def test_enumerator_report_can_hide_gps_accuracy_without_mutating_internal_issues():
    issues = pd.DataFrame([
        {"row_index": 0, "uuid": "u1", "category": "gps", "field": "_Local GPS_precision",
         "severity": "warning", "message": "GPS precision 12 m"},
        {"row_index": 0, "uuid": "u1", "category": "gps", "field": "_Local GPS",
         "severity": "error", "message": "Missing GPS coordinates"},
    ])
    filtered = filter_enumerator_report_issues(issues, include_gps_accuracy=False)
    assert len(filtered) == 1
    assert filtered.iloc[0]["message"] == "Missing GPS coordinates"
    assert len(issues) == 2


def test_main_validation_pipeline_runs_coverage_mismatch_rule():
    species = SPECIES_LIST[0]
    frame = pd.DataFrame({
        "start": ["2026-07-09 12:00:00"],
        "end": ["2026-07-09 12:12:00"],
        "Collector Name": ["Ari"],
        "Date and time": ["2026-07-09 12:12:00"],
        "Administration Post": ["Metinaro"],
        "Village": ["Sabuli"],
        "_Local GPS_latitude": [-8.51967],
        "_Local GPS_longitude": [125.7174723],
        "_Local GPS_precision": [4.0],
        "_uuid": ["u1"],
        "Transect Number": [1],
        "Quadrat Number": [1],
        "Presence of Seagrass": ["Yes"],
        "Quadrat Photo_URL": ["https://kobo.example/photo"],
        "General Condition": ["Healthy"],
        f"Seagrass species present in the Quadrat/{species}": [1],
        f"Percent {species} (%)": [20.0],
        "Epicover Percentage (%)": [40.0],
    })
    issues = validate(standardize(frame))
    assert any(issues["category"] == "coverage_mismatch")


def test_basic_spacing_and_simple_enumerator_capitalization_are_corrected_and_logged():
    source = pd.DataFrame({
        "Collector Name": ["  john   doe  "],
        "Administration Post": ["Metinaro"],
        "Village": ["Sabuli"],
        "_uuid": ["u1"],
    })
    spaced = _strip_all_strings(source.copy())
    assert spaced.loc[0, "Collector Name"] == "john doe"
    corrected, log = correct(spaced)
    assert corrected.loc[0, "Collector Name"] == "John Doe"
    assert "enumerator_name_formatting" in set(log["rule"])


def test_missing_species_findings_appear_in_row_flags_and_message_column():
    source = pd.DataFrame({"_uuid": ["u1"], "Collector Name": ["Ari"]})
    issues = pd.DataFrame([{
        "row_index": 0,
        "uuid": "u1",
        "category": "species",
        "field": "Seagrass species",
        "severity": "error",
        "message": "Missing seagrass species: Presence of Seagrass = Yes but no species selected",
    }])
    result = add_qa_columns(source, issues)
    assert result.loc[0, "qa_species_logic"] == "Yes"
    assert "Missing seagrass species" in result.loc[0, "Message"]
