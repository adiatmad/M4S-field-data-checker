import pandas as pd

from enumerator_raw_exports import build_enumerator_raw_exports


def test_exports_keep_all_raw_rows_and_columns_and_add_missing_ho_cover_column():
    raw = pd.DataFrame({
        "Naran Koletor": ["Ana", "Ana", "Beto"],
        "Numeru Quadrante": [1, 2, 3],
        "Foto Quadrante_URL": ["https://example.test/photo1", "", ""],
        "Espesie du'ut tasi (seagrass) ne'ebe prezensa iha Quadrante/Halophila ovalis": [1, 1, 0],
    })
    issues = pd.DataFrame([
        {
            "row_index": 0, "uuid": "u1", "category": "species",
            "field": "Percent Halophila ovalis (%)", "severity": "error",
            "message": "Halophila ovalis marked present but its percentage-cover column is missing from the export",
        },
        {
            "row_index": 1, "uuid": "u2", "category": "species",
            "field": "Percent Halophila ovalis (%)", "severity": "error",
            "message": "Halophila ovalis marked present but its percentage-cover column is missing from the export",
        },
    ])

    exports = build_enumerator_raw_exports(raw, issues)

    assert set(exports) == {"Ana", "Beto"}
    ana = exports["Ana"]
    assert len(ana) == 2  # Keep clean and flagged rows for the enumerator.
    assert ana["Numeru Quadrante"].tolist() == [1, 2]
    assert "Foto Quadrante_URL" in ana.columns
    ho_column = "Persentajen (Ho) Halophila ovalis (%)"
    assert ho_column in ana.columns
    assert ana[ho_column].isna().all()
    assert "percentage-cover column is missing" in ana.loc[0, "QA Message"]
    assert ana.loc[0, "QA Fields to Check"] == "Percent Halophila ovalis (%)"
    assert ana.loc[0, "QA Severity"] == "ERROR"
    assert ana.loc[1, "QA Message"] != ""


def test_exports_keep_source_data_and_report_blank_rows_without_errors():
    raw = pd.DataFrame({"Collector Name": ["Cak", "Cak"], "source_value": ["keep", "also keep"]})
    issues = pd.DataFrame(columns=["row_index", "uuid", "category", "field", "severity", "message"])

    exports = build_enumerator_raw_exports(raw, issues)

    assert len(exports["Cak"]) == 2
    assert exports["Cak"]["source_value"].tolist() == ["keep", "also keep"]
    assert exports["Cak"]["QA Message"].eq("").all()
    assert exports["Cak"]["QA Fields to Check"].eq("").all()
