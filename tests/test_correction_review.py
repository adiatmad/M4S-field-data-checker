import pandas as pd
import pytest

from correction_review import apply_approved_corrections, suggest_corrections


def test_suggestions_do_not_mutate_input_and_require_approval():
    source = pd.DataFrame({
        "Collector Name": ["Ari L", "Ari_L", "Ari L"],
        "Administration Post": ["Metinara", "Metinaro", "Metinara"],
        "Village": ["Sabuli", "Sabuli", "Sabuli"],
        "_uuid": ["u1", "u2", "u3"],
    })
    original = source.copy(deep=True)

    proposals = suggest_corrections(source)
    pd.testing.assert_frame_equal(source, original)
    assert not proposals.empty
    assert set(proposals["field"]) >= {"Collector Name", "Administration Post"}

    unchanged, empty_log = apply_approved_corrections(source, proposals, [])
    pd.testing.assert_frame_equal(unchanged, source)
    assert empty_log.empty


def test_only_selected_proposals_are_applied_and_logged():
    source = pd.DataFrame({
        "Collector Name": ["Ari_L", "Ari L"],
        "Administration Post": ["Metinara", "Metinaro"],
        "_uuid": ["u1", "u2"],
    })
    proposals = suggest_corrections(source)
    geo = proposals[proposals["field"] == "Administration Post"].iloc[0]

    corrected, log = apply_approved_corrections(source, proposals, [int(geo["proposal_id"])])

    assert corrected.loc[0, "Administration Post"] == "Metinaro"
    assert corrected.loc[0, "Collector Name"] == "Ari_L"
    assert len(log) == 1
    assert log.iloc[0]["before"] == "Metinara"
    assert log.iloc[0]["after"] == "Metinaro"
    assert log.iloc[0]["uuid"] == "u1"
    assert source.loc[0, "Administration Post"] == "Metinara"


def test_unknown_proposal_id_is_rejected():
    source = pd.DataFrame({"Village": ["Sabuli"]})
    proposals = suggest_corrections(source)
    with pytest.raises(ValueError, match="Unknown proposal IDs"):
        apply_approved_corrections(source, proposals, [999])


def test_similarity_threshold_is_validated():
    with pytest.raises(ValueError):
        suggest_corrections(pd.DataFrame({"Collector Name": ["A", "B"]}), threshold=79)
