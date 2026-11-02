import pandas as pd

from qa_table_filters import select_rows_for_review

FLAG_COLUMNS = ["qa_gps_precision_0", "qa_species_logic"]


def review_frame():
    return pd.DataFrame({
        "Collector Name": ["Ari", "Bia", "Cai"],
        "qa_gps_precision_0": ["Yes", "", ""],
        "qa_species_logic": ["", "Yes", ""],
        "Message": ["Missing GPS coordinates", "", ""],
    })


def test_no_filters_keeps_every_row():
    result = select_rows_for_review(review_frame(), flag_columns=FLAG_COLUMNS)
    assert list(result.index) == [0, 1, 2]


def test_selected_flag_types_narrow_to_matching_rows():
    result = select_rows_for_review(
        review_frame(), flag_columns=FLAG_COLUMNS, show_only_flagged=True,
        selected_flags=["qa_species_logic"],
    )
    assert list(result.index) == [1]


def test_unticking_every_flag_type_shows_all_flagged_rows_instead_of_nothing():
    result = select_rows_for_review(
        review_frame(), flag_columns=FLAG_COLUMNS, show_only_flagged=True, selected_flags=[],
    )
    assert list(result.index) == [0, 1]


def test_review_marker_counts_as_flagged():
    data = review_frame()
    data["qa_gps_precision_0"] = ["Review", "", ""]
    result = select_rows_for_review(
        data, flag_columns=FLAG_COLUMNS, show_only_flagged=True,
        selected_flags=["qa_gps_precision_0"],
    )
    assert list(result.index) == [0]


def test_message_filter_and_search_combine():
    result = select_rows_for_review(
        review_frame(), flag_columns=FLAG_COLUMNS, message_only=True, search_text="gps",
    )
    assert list(result.index) == [0]


def test_search_is_case_insensitive():
    result = select_rows_for_review(review_frame(), flag_columns=FLAG_COLUMNS, search_text="BIA")
    assert list(result.index) == [1]


def test_flag_columns_absent_from_the_table_are_ignored():
    result = select_rows_for_review(
        review_frame(),
        flag_columns=FLAG_COLUMNS + ["qa_missing_general_condition"],
        show_only_flagged=True,
    )
    assert list(result.index) == [0, 1]
