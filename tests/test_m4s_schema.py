import pandas as pd
import pytest

from m4s_seagrass_qa import _canonicalize_form_columns, load_data


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


def test_load_data_still_rejects_missing_required_fields(tmp_path):
    path = tmp_path / "incomplete.xlsx"
    pd.DataFrame({"start": ["2026-07-09"], "_uuid": ["x"]}).to_excel(path, index=False)

    with pytest.raises(ValueError, match="Unsupported Kobo form schema") as exc:
        load_data(str(path))

    assert "Collector Name" in str(exc.value)
    assert "Available headers" in str(exc.value)



def test_existing_canonical_column_is_not_overwritten_by_tetun_alias():
    raw = tetun_export_frame()
    raw["Collector Name"] = ["Canonical value"]
    canonical = _canonicalize_form_columns(raw)

    assert canonical.loc[0, "Collector Name"] == "Canonical value"
    # The translated source is retained rather than silently discarded.
    assert canonical.loc[0, "Naran Koletor"] == "Field Team"


def test_load_data_rejects_missing_mandatory_qa_input_even_if_core_metadata_exists(tmp_path):
    source = tetun_export_frame().drop(columns=["Prezensa Du'ut tasi (Seagrass)"])
    path = tmp_path / "missing_presence.xlsx"
    source.to_excel(path, index=False)

    with pytest.raises(ValueError, match="Unsupported Kobo form schema") as exc:
        load_data(str(path))

    assert "Presence of Seagrass" in str(exc.value)
