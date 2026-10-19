import io
import zipfile

import pandas as pd

from m4s_seagrass_qa import (
    SPECIES_LIST,
    build_enumerator_error_logs,
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
