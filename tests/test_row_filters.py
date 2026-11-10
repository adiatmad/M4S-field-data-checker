import pandas as pd

from row_filters import filter_raw_rows


def _frame():
    return pd.DataFrame(
        {
            "Message": ["", "GPS precision is 0.0", ""],
            "Village": ["Sabuli", "Metinaro", "Sabuli"],
            "qa_gps_precision_0": ["", "Yes", ""],
            "qa_coverage_mismatch": ["", "", "Yes - 25 vs 55"],
        }
    )


def test_no_filters_keeps_every_row():
    frame = _frame()

    assert list(filter_raw_rows(frame).index) == [0, 1, 2]


def test_row_scope_keeps_only_the_listed_rows():
    frame = _frame()

    assert list(filter_raw_rows(frame, rows_to_show={1}).index) == [1]


def test_flags_keep_rows_with_any_selected_flag():
    frame = _frame()

    matched = filter_raw_rows(frame, flags=["qa_gps_precision_0", "qa_coverage_mismatch"])

    assert list(matched.index) == [1, 2]


def test_enumerator_filter_keeps_selected_enumerators():
    frame = _frame()
    enumerators = pd.Series(["Ana", "Beto", "Ana"], index=frame.index)

    matched = filter_raw_rows(frame, enumerator_values=enumerators, enumerators=["Ana"])

    assert list(matched.index) == [0, 2]


def test_search_is_literal_and_case_insensitive():
    # A reviewer may paste text with regex characters, such as "(%)".
    frame = _frame()
    frame.loc[1, "Village"] = "Metinaro (%)"

    assert list(filter_raw_rows(frame, search="metinaro").index) == [1]
    assert list(filter_raw_rows(frame, search="(%)").index) == [1]


def test_selected_filters_combine():
    frame = _frame()
    enumerators = pd.Series(["Ana", "Beto", "Ana"], index=frame.index)

    matched = filter_raw_rows(
        frame,
        rows_to_show={0, 1, 2},
        flags=["qa_gps_precision_0"],
        enumerator_values=enumerators,
        enumerators=["Ana"],
    )

    assert matched.empty
