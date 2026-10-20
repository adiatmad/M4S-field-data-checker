import pandas as pd
import pytest

from m4s_seagrass_qa import (
    _canonicalize_form_columns,
    generate_qa_report,
    load_data,
    standardize,
    validate,
    validate_categorical_text_quality,
)


def tetun_export_frame():
    return pd.DataFrame(
        {
            "start": ["2026-07-09 12:18:10"],
            "end": ["2026-07-09 12:30:10"],
            "Naran Koletor": ["Field Team"],
            "Data no Horas": ["2026-07-09 13:03:00"],
            "Postu Administrativu": ["metinaro"],
            "Suku": ["Sabuli"],
            "_GPS Lokal_latitude": [-8.5203],
            "_GPS Lokal_longitude": [125.7150],
            "_GPS Lokal_altitude": [44.6],
            "_GPS Lokal_precision": [4.8],
            "Numeru Tranjektu": [1],
            "Numeru Quadrante": [2],
            "Prezensa Du'ut tasi (Seagrass)": ["Sim"],
            "General Condition": ["Healthy"],
            "Persentajen Kober Alga (%)": [10],
            "Persentajen Epicover (%) ": [40],
            "Foto Quadrante_URL": ["https://example.invalid/photo.jpg"],
            "Espesie du'ut tasi (seagrass) ne'ebe prezensa iha Quadrante/Halophila ovalis": [1],
            "Persentajen (Ho) Halophila ovalis  (%)": [40],
            "_uuid": ["test-uuid-1"],
            "unrecognized_field": ["keep me"],
        }
    )


def test_tetun_headers_map_to_canonical_names_without_mutating_raw_columns():
    raw = tetun_export_frame()
    canonical = _canonicalize_form_columns(raw)

    assert "Naran Koletor" in raw.columns
    assert "Collector Name" not in raw.columns
    assert canonical.loc[0, "Collector Name"] == "Field Team"
    assert canonical.loc[0, "Administration Post"] == "metinaro"
    assert canonical.loc[0, "Village"] == "Sabuli"
    assert canonical.loc[0, "_Local GPS_latitude"] == pytest.approx(-8.5203)
    assert canonical.loc[0, "_Local GPS_precision"] == pytest.approx(4.8)
    assert canonical.loc[0, "Presence of Seagrass"] == "Yes"
    assert canonical.loc[0, "Seagrass species present in the Quadrat/Halophila ovalis"] == 1
    assert canonical.loc[0, "Percent Halophila ovalis (%)"] == 40
    assert canonical.loc[0, "Epicover Percentage (%)"] == 40
    assert canonical.loc[0, "unrecognized_field"] == "keep me"


def test_header_alias_lookup_ignores_whitespace_variations_without_rewriting_unknown_headers():
    raw = tetun_export_frame().rename(
        columns={
            "Naran Koletor": "  Naran   Koletor ",
            "Persentajen Epicover (%) ": "Persentajen   Epicover (%)",
            "Persentajen (Ho) Halophila ovalis  (%)": " Persentajen (Ho) Halophila ovalis (%) ",
        }
    )

    canonical = _canonicalize_form_columns(raw)

    assert canonical.loc[0, "Collector Name"] == "Field Team"
    assert canonical.loc[0, "Epicover Percentage (%)"] == 40
    assert canonical.loc[0, "Percent Halophila ovalis (%)"] == 40
    assert "  Naran   Koletor " in raw.columns
    assert "unrecognized_field" in canonical.columns


def test_load_data_accepts_current_tetun_export_and_preserves_raw_copy(tmp_path):
    path = tmp_path / "tetun_export.xlsx"
    source = tetun_export_frame()
    source.to_excel(path, index=False)

    raw, working = load_data(str(path))

    assert "Naran Koletor" in raw.columns
    assert "Collector Name" not in raw.columns
    assert "Collector Name" in working.columns
    assert "Presence of Seagrass" in working.columns
    assert len(raw) == len(working) == 1


def test_load_data_accepts_export_without_optional_kobo_metadata(tmp_path):
    source = tetun_export_frame().drop(columns=["start", "end", "_uuid"])
    source["_index"] = [1]
    path = tmp_path / "tetun_export_without_metadata.xlsx"
    source.to_excel(path, index=False)

    raw, working = load_data(str(path))
    assert "_index" in raw.columns
    assert "_index" in working.columns
    assert "start" not in working.columns
    assert "end" not in working.columns
    assert "_uuid" not in working.columns

    standardized = standardize(working)
    issues = validate(standardized)
    assert "_duration_seconds" in standardized.columns
    assert standardized["_duration_seconds"].isna().all()
    assert not any(issue["field"] == "start/end" for issue in issues.to_dict("records"))


def test_missing_uuid_does_not_create_false_duplicate_findings():
    from m4s_seagrass_qa import validate_duplicate_submissions

    frame = _canonicalize_form_columns(tetun_export_frame().drop(columns=["_uuid"]))
    frame = pd.concat([frame, frame], ignore_index=True)
    issues = validate_duplicate_submissions(frame)
    assert not any(issue["field"] == "_uuid" for issue in issues)


def test_load_data_still_rejects_missing_required_fields(tmp_path):
    path = tmp_path / "incomplete.xlsx"
    pd.DataFrame({"start": ["2026-07-09"], "_uuid": ["x"]}).to_excel(path, index=False)

    with pytest.raises(ValueError, match="Unsupported Kobo form schema") as exc:
        load_data(str(path))

    assert "Collector Name" in str(exc.value)
    assert "Available headers" in str(exc.value)



def test_load_data_rejects_missing_m4s_required_columns(tmp_path):
    path = tmp_path / "missing_quadrat_fields.xlsx"
    source = tetun_export_frame().drop(columns=["Numeru Quadrante"])
    source.to_excel(path, index=False)

    with pytest.raises(ValueError, match="Unsupported Kobo form schema") as exc:
        load_data(str(path))

    assert "Quadrat Number" in str(exc.value)


def test_mandatory_fields_flag_whitespace_only_values():
    frame = _canonicalize_form_columns(tetun_export_frame())
    frame["Quadrat Number"] = frame["Quadrat Number"].astype(object)
    frame.loc[0, "Quadrat Number"] = "   "
    frame.loc[0, "Collector Name"] = "  "
    standardized = standardize(frame)

    issues = validate(standardized)
    missing = issues[(issues["category"] == "logic") & (issues["severity"] == "error")]

    assert "Collector Name" in set(missing["field"])
    assert "Quadrat Number" in set(missing["field"])


def test_invalid_nonblank_numeric_values_are_reported():
    frame = _canonicalize_form_columns(tetun_export_frame())
    frame["Percentage of Algal Cover (%)"] = frame["Percentage of Algal Cover (%)"].astype(object)
    frame.loc[0, "Percentage of Algal Cover (%)"] = "not-a-number"
    standardized = standardize(frame)

    issues = validate(standardized)
    invalid = issues[issues["category"] == "numeric"]

    assert len(invalid) == 1
    assert invalid.iloc[0]["field"] == "Percentage of Algal Cover (%)"
    assert "not-a-number" in invalid.iloc[0]["message"]


def test_clean_dataset_generates_report_with_zero_issues(tmp_path):
    frame = _canonicalize_form_columns(tetun_export_frame())
    standardized = standardize(frame)
    issues = validate(standardized)

    # The fixture intentionally has a coverage value that is otherwise valid and
    # a species percentage matching epicover; the validation pipeline must be stable.
    assert list(issues.columns) == [
        "row_index", "uuid", "category", "field", "severity", "message"
    ]
    assert issues.empty

    report_path = tmp_path / "qa_report.md"
    generate_qa_report(standardized, issues, pd.DataFrame(), report_path)

    report = report_path.read_text(encoding="utf-8")
    assert "Clean (no issues): **1**" in report
    assert "Errors: **0**" in report
    assert "No issues found." in report


def test_tetum_yes_no_values_are_normalized_case_insensitively():
    frame = tetun_export_frame()
    frame.loc[0, "Prezensa Du'ut tasi (Seagrass)"] = "SIM"
    canonical = _canonicalize_form_columns(frame)
    assert canonical.loc[0, "Presence of Seagrass"] == "Yes"

    frame.loc[0, "Prezensa Du'ut tasi (Seagrass)"] = "LAE"
    canonical = _canonicalize_form_columns(frame)
    assert canonical.loc[0, "Presence of Seagrass"] == "No"


def test_categorical_capitalization_variants_are_flagged_without_auto_correction():
    frame = pd.DataFrame({
        "General Condition": ["Diak", "diak", "Diak"],
        "_uuid": ["one", "two", "three"],
    })
    issues = validate_categorical_text_quality(frame)

    assert len(issues) == 1
    assert issues[0]["row_index"] == 1
    assert issues[0]["category"] == "text_formatting"
    assert "Inconsistent capitalization" in issues[0]["message"]
    assert frame.loc[1, "General Condition"] == "diak"


def test_enumerator_report_can_hide_text_formatting_findings_only():
    from m4s_seagrass_qa import filter_enumerator_report_issues

    issues = pd.DataFrame([
        {"row_index": 0, "uuid": "a", "category": "text_formatting", "field": "General Condition",
         "severity": "warning", "message": "Inconsistent capitalization"},
        {"row_index": 0, "uuid": "a", "category": "gps", "field": "_Local GPS_precision",
         "severity": "warning", "message": "GPS precision 12.0 m: below recommended accuracy"},
    ])
    visible = filter_enumerator_report_issues(issues, include_text_formatting=False)
    assert visible["category"].tolist() == ["gps"]


def test_tetum_categorical_spelling_variants_are_suggested_not_corrected():
    frame = pd.DataFrame({
        "General Condition": ["Diak", "Di'ak", "Diak", "Diak"],
        "_uuid": ["one", "two", "three", "four"],
    })
    issues = validate_categorical_text_quality(frame)
    spelling = [issue for issue in issues if "Possible spelling variant" in issue["message"]]

    assert spelling
    assert spelling[0]["row_index"] == 1
    assert frame.loc[1, "General Condition"] == "Di'ak"



def test_gps_precision_column_is_optional_but_coordinates_are_still_checked(tmp_path):
    source = tetun_export_frame().drop(columns=["_GPS Lokal_precision"])
    path = tmp_path / "without_gps_precision.xlsx"
    source.to_excel(path, index=False)

    raw, working = load_data(str(path))
    assert "_Local GPS_precision" not in working.columns

    standardized = standardize(working)
    issues = validate(standardized)
    assert not (
        (issues["category"] == "gps")
        & issues["field"].astype(str).str.contains("precision", case=False)
    ).any()


def test_species_selection_ad_to_aq_requires_matching_percentage_ar_to_be():
    from m4s_seagrass_qa import SPECIES_LIST, validate_species_logic

    # AD:AQ = 14 species-selection fields; AR:BE = their corresponding cover fields.
    columns = [f"unused_{index}" for index in range(57)]
    for offset, species in enumerate(SPECIES_LIST):
        columns[29 + offset] = f"Seagrass species present in the Quadrat/{species}"
        columns[43 + offset] = f"Percent {species} (%)"
    frame = pd.DataFrame([{column: None for column in columns}], columns=columns)
    frame["_uuid"] = "positional-test"
    frame["Presence of Seagrass"] = "Yes"

    # Every one of the 14 selection values is 1; every paired percentage is missing.
    for species in SPECIES_LIST:
        frame.at[0, f"Seagrass species present in the Quadrat/{species}"] = 1

    issues = validate_species_logic(frame)
    missing_cover_fields = {
        issue["field"] for issue in issues
        if issue["row_index"] == 0 and "marked present but no % cover recorded" in issue["message"]
    }
    expected_cover_fields = {f"Percent {species} (%)" for species in SPECIES_LIST}
    assert missing_cover_fields == expected_cover_fields

    # Supplying numeric cover values for every pair clears all missing-cover findings.
    for species in SPECIES_LIST:
        frame.at[0, f"Percent {species} (%)"] = 10
    repaired_issues = validate_species_logic(frame)
    assert not any("marked present but no % cover recorded" in issue["message"] for issue in repaired_issues)
def test_correct_exposes_separate_conservative_match_thresholds():
    from m4s_seagrass_qa import correct

    frame = pd.DataFrame({
        "Collector Name": ["Alice", "Alicee"],
        "Administration Post": ["Metinaro", "Metinara"],
        "Village": ["Sabuli", "Sabuli"],
        "_uuid": ["one", "two"],
    })

    corrected, _ = correct(
        frame,
        enumerator_match_threshold=100,
        geography_match_threshold=100,
    )
    assert corrected.loc[1, "Collector Name"] == "Alicee"
    assert corrected.loc[1, "Administration Post"] == "Metinara"

    with pytest.raises(ValueError, match="threshold must be an integer from 80 to 100"):
        correct(frame, enumerator_match_threshold=79)


def test_correct_stage_logs_changes_when_optional_uuid_column_is_absent():
    from m4s_seagrass_qa import correct

    frame = pd.DataFrame({
        "Collector Name": ["alice", "Alice"],
        "Administration Post": ["metinaro", "Metinara"],
        "Village": ["Sabuli", "Sabuli"],
    })
    original = frame.copy(deep=True)

    corrected, correction_log = correct(frame)

    assert corrected.loc[0, "Collector Name"] == "Alice"
    assert corrected.loc[0, "Administration Post"] == "Metinaro"
    assert not correction_log.empty
    assert "uuid" in correction_log.columns
    assert correction_log["uuid"].isna().all()
    pd.testing.assert_frame_equal(frame, original)
