import io
import zipfile

import pandas as pd

from enumerator_raw_exports import build_enumerator_raw_exports, enumerator_raw_data_zip


ISSUE_COLUMNS = ["row_index", "uuid", "category", "field", "severity", "message"]


def test_raw_export_preserves_rows_and_columns_and_appends_only_error_message():
    raw = pd.DataFrame({
        "Naran Koletor": ["Ana", "Ana", "Beto"],
        "Numeru Quadrante": [1, 2, 3],
        "Foto Quadrante_URL": ["https://example.test/photo1", "", ""],
        "Ho presence": [1, 1, 0],
    })
    issues = pd.DataFrame([
        {"row_index": 0, "uuid": "u1", "category": "species", "field": "Ho cover",
         "severity": "error", "message": "Ho marked present but no % cover recorded"},
        {"row_index": 0, "uuid": "u1", "category": "gps", "field": "GPS",
         "severity": "warning", "message": "GPS precision below recommended accuracy"},
        {"row_index": 1, "uuid": "u2", "category": "species", "field": "Ho cover",
         "severity": "ERROR", "message": "Ho cover is missing"},
    ])

    exports = build_enumerator_raw_exports(raw, issues)

    assert set(exports) == {"Ana", "Beto"}
    ana = exports["Ana"]
    assert len(ana) == 2
    assert ana["Numeru Quadrante"].tolist() == [1, 2]
    assert ana["Foto Quadrante_URL"].tolist() == ["https://example.test/photo1", ""]
    assert ana.columns.tolist() == [*raw.columns.tolist(), "Error Message"]
    assert ana.loc[0, "Error Message"] == "Espésie Ho marka hanesan prezente, maibé la rejista % kober (Ho marked present but no % cover recorded)"
    assert ana.loc[1, "Error Message"] == "Ho cover is missing"
    assert "warning" not in " ".join(ana["Error Message"].tolist()).casefold()
    assert exports["Beto"]["Error Message"].tolist() == [""]


def test_raw_export_does_not_add_missing_cover_or_qa_helper_columns():
    raw = pd.DataFrame({"Collector Name": ["Cak"], "source_value": ["keep"]})
    issues = pd.DataFrame([
        {"row_index": 0, "uuid": "u1", "category": "species",
         "field": "Percent Halophila ovalis (%)", "severity": "error",
         "message": "Halophila ovalis marked present but its percentage-cover column is missing from the export"}
    ])

    exported = build_enumerator_raw_exports(raw, issues)["Cak"]

    assert exported.columns.tolist() == ["Collector Name", "source_value", "Error Message"]
    assert "percentage-cover column is missing" in exported.loc[0, "Error Message"]


def test_blank_source_headers_are_explicitly_labeled_by_excel_position():
    raw = pd.DataFrame([["Ana", "value-bs", "value-bt"]], columns=["Collector Name", "", " "])
    issues = pd.DataFrame(columns=ISSUE_COLUMNS)

    exported = build_enumerator_raw_exports(raw, issues)["Ana"]

    assert exported.columns.tolist() == ["Collector Name", "Unnamed: B", "Unnamed: C", "Error Message"]
    assert exported.loc[0, "Unnamed: B"] == "value-bs"
    assert exported.loc[0, "Unnamed: C"] == "value-bt"


def test_blank_header_at_excel_column_bs_uses_position_label():
    columns = [""] * 71
    columns[0] = "Collector Name"
    raw = pd.DataFrame([["Ana"] + [f"v{i}" for i in range(70)]], columns=columns)
    issues = pd.DataFrame(columns=ISSUE_COLUMNS)

    exported = build_enumerator_raw_exports(raw, issues)["Ana"]

    assert exported.columns[70] == "Unnamed: BS"
    assert exported.columns[-1] == "Error Message"
    assert exported.iloc[0, 70] == "v69"

def test_pandas_generated_unnamed_header_at_bs_is_normalized_by_position():
    columns = ["Collector Name"] + [f"field{i}" for i in range(69)] + ["Unnamed: 70"]
    raw = pd.DataFrame([["Ana"] + [f"v{i}" for i in range(70)]], columns=columns)
    issues = pd.DataFrame(columns=ISSUE_COLUMNS)

    exported = build_enumerator_raw_exports(raw, issues)["Ana"]

    assert exported.columns[70] == "Unnamed: BS"
    assert exported.iloc[0, 70] == "v69"


def test_raw_export_keeps_rows_when_no_errors_and_excludes_warnings():
    raw = pd.DataFrame({"Collector Name": ["Cak", "Cak"], "source_value": ["keep", "also keep"]})
    issues = pd.DataFrame([
        {"row_index": 0, "uuid": "u1", "category": "gps", "field": "GPS precision",
         "severity": "warning", "message": "Check GPS precision"}
    ])

    exported = build_enumerator_raw_exports(raw, issues)["Cak"]

    assert len(exported) == 2
    assert exported["source_value"].tolist() == ["keep", "also keep"]
    assert exported["Error Message"].eq("").all()
    assert exported.columns.tolist() == ["Collector Name", "source_value", "Error Message"]


def test_zip_contains_per_enumerator_xlsx_with_excel_filters_and_preserved_values():
    from openpyxl import load_workbook

    raw = pd.DataFrame({"Collector Name": ["Ana"], "answer": ["sí"], "photo_URL": ["https://example.test/photo"]})
    issues = pd.DataFrame([
        {"row_index": 0, "uuid": "u1", "category": "required", "field": "answer",
         "severity": "error", "message": "Check answer"}
    ])

    payload = enumerator_raw_data_zip(raw, issues)

    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        names = archive.namelist()
        assert names == ["01_Ana_raw_with_errors.xlsx"]
        content = archive.read(names[0])
    workbook = load_workbook(io.BytesIO(content), data_only=True)
    sheet = workbook["Raw data"]
    assert [cell.value for cell in sheet[1]] == ["Collector Name", "answer", "photo_URL", "Error Message"]
    assert sheet["B2"].value == "sí"
    assert sheet["D2"].value == "Check answer"
    assert sheet.freeze_panes == "A2"
    assert sheet.auto_filter.ref == sheet.dimensions
    assert sheet["C2"].hyperlink.target == "https://example.test/photo"
