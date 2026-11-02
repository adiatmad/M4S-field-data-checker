"""Row selection for the M4S review table.

Lives outside the Streamlit entry point so the filter combinations can be tested.
"""
from __future__ import annotations

from collections.abc import Iterable, Sequence

import pandas as pd

# Values written by add_qa_columns(): "Yes", "Review" for centroid warnings, and
# "Yes - <message>" for coverage mismatches.
_FLAGGED_STARTS = ("yes", "review")


def _is_flagged(series: pd.Series) -> pd.Series:
    text = series.astype("string").fillna("").str.strip().str.casefold()
    return text.str.startswith(_FLAGGED_STARTS)


def select_rows_for_review(
    frame: pd.DataFrame,
    *,
    flag_columns: Sequence[str],
    show_only_flagged: bool = False,
    selected_flags: Iterable[str] = (),
    message_only: bool = False,
    search_text: str = "",
) -> pd.DataFrame:
    """Apply the review filters together, so one filter never silently cancels another.

    An empty flag selection keeps every flagged row rather than hiding the whole
    table: unticking every box should show more, never nothing.
    """
    mask = pd.Series(True, index=frame.index)

    if show_only_flagged:
        available = [column for column in flag_columns if column in frame.columns]
        wanted = [column for column in selected_flags if column in available] or available
        if wanted:
            flagged = pd.Series(False, index=frame.index)
            for column in wanted:
                flagged = flagged | _is_flagged(frame[column])
            mask = mask & flagged

    if message_only and "Message" in frame.columns:
        mask = mask & frame["Message"].astype("string").fillna("").str.strip().ne("")

    needle = (search_text or "").strip().casefold()
    if needle:
        text_columns = frame.select_dtypes(include=["object", "string"]).columns
        found = pd.Series(False, index=frame.index)
        for column in text_columns:
            found = found | frame[column].astype("string").fillna("").str.casefold().str.contains(
                needle, regex=False
            )
        mask = mask & found

    return frame[mask]
