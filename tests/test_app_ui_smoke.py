"""Headless UI checks for both Streamlit entry points.

AppTest renders the real scripts and inspects the resulting elements. It covers
rendering and state changes, not visual layout, keyboard order, or narrow viewports.
"""
import io
from pathlib import Path

import pandas as pd
import pytest

AppTest = pytest.importorskip("streamlit.testing.v1").AppTest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
M4S_WORKFLOW = "Excel file (.xlsx) from the M4S seagrass survey"
CSV_WORKFLOW = "CSV file (.csv) from another KoboToolbox survey"


def m4s_export(**overrides) -> bytes:
    species = "Halophila ovalis"
    row = {
        "start": "2026-07-09 12:00:00",
        "end": "2026-07-09 12:12:00",
        "Collector Name": "Ari",
        "Date and time": "2026-07-09 12:12:00",
        "Administration Post": "Metinaro",
        "Village": "Sabuli",
        "_uuid": "u1",
        "_Local GPS_latitude": -8.51967,
        "_Local GPS_longitude": 125.7174723,
        "_Local GPS_precision": 4.0,
        "Transect Number": 1,
        "Quadrat Number": 1,
        "Presence of Seagrass": "Yes",
        "Quadrat Photo_URL": "https://kobo.example/photo",
        "General Condition": "Healthy",
        f"Seagrass species present in the Quadrat/{species}": 1,
        f"Percent {species} (%)": 20.0,
        "Epicover Percentage (%)": 40.0,
    }
    row.update(overrides)
    buffer = io.BytesIO()
    pd.DataFrame([row]).to_excel(buffer, index=False)
    return buffer.getvalue()


def load_app() -> "AppTest":
    return AppTest.from_file(str(PROJECT_ROOT / "m4s_app.py"), default_timeout=180).run()


def find(widgets, label):
    return next(widget for widget in widgets if widget.label == label)


def test_m4s_workflow_opens_with_the_upload_prompt():
    at = load_app()
    assert not at.exception
    assert at.title[0].value == "Check your M4S seagrass survey data"
    assert at.radio[0].options == [M4S_WORKFLOW, CSV_WORKFLOW]
    assert any("Choose the .xlsx file" in note.value for note in at.info)
    assert not at.metric


def test_m4s_upload_reaches_the_numbered_results_steps():
    at = load_app()
    at.file_uploader[0].set_value(
        ("survey.xlsx", m4s_export(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    ).run()
    assert not at.exception
    headings = [heading.value for heading in at.subheader]
    for expected in (
        "Step 2: Read the summary",
        "Step 3: See what kinds of finding were reported",
        "Step 4: Find the records to check",
        "Step 5: Download what you need",
    ):
        assert expected in headings
    labels = [metric.label for metric in at.metric]
    assert "Total records" in labels
    assert "Records with no finding" in labels


def test_m4s_search_without_matches_explains_an_empty_table():
    at = load_app()
    at.file_uploader[0].set_value(
        ("survey.xlsx", m4s_export(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    ).run()
    find(at.checkbox, "Show only records with a finding").set_value(True).run()
    assert not at.exception
    find(at.text_input, "Search the table").set_value("no-such-value-anywhere").run()
    assert not at.exception
    assert any("No record matches the current filters" in note.value for note in at.info)


def test_m4s_wrong_schema_shows_a_recoverable_error_without_results():
    at = load_app()
    at.file_uploader[0].set_value(
        ("other.xlsx", m4s_export(**{"Collector Name": None, "Village": None}), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    ).run()
    buffer = io.BytesIO()
    pd.DataFrame({"unrelated": [1]}).to_excel(buffer, index=False)
    at.file_uploader[0].set_value(
        ("unrelated.xlsx", buffer.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    ).run()
    assert not at.exception
    assert any("Could not load the uploaded XLSX file" in error.value for error in at.error)
    assert not at.metric


def test_csv_workflow_switches_and_reports_findings():
    at = load_app()
    at.radio[0].set_value(CSV_WORKFLOW).run()
    assert not at.exception
    assert at.title[0].value == "Check a KoboToolbox CSV file"
    at.file_uploader[0].set_value(
        ("export.csv", b"record_id,name,age\n0012,Ari,20\n0012,Bia,\n", "text/csv")
    ).run()
    assert not at.exception
    assert not at.error
    assert [metric.label for metric in at.metric] == [
        "Rows", "Columns", "Findings", "Rows with a finding",
    ]
    assert any("Row numbers count the header as row 1" in caption.value for caption in at.caption)


def test_standalone_csv_app_renders_a_summary_for_an_upload():
    at = AppTest.from_file(str(PROJECT_ROOT / "kobo_csv_quality_app.py"), default_timeout=180).run()
    assert not at.exception
    assert any("Choose the .csv file" in note.value for note in at.info)
    at.file_uploader[0].set_value(("export.csv", b"record_id,name\n0012,Ari\n", "text/csv")).run()
    assert not at.exception
    assert [metric.label for metric in at.metric][:2] == ["Rows", "Columns"]
