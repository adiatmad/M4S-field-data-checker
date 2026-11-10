"""Row filters for the QA-annotated data view.

Pure pandas helpers so the on-screen filters can be tested without a Streamlit runtime.
Filters only narrow which rows are shown and downloaded; they never edit the source.
"""

import pandas as pd


def filter_raw_rows(df, *, rows_to_show=None, flags=(), enumerator_values=None, enumerators=(), search=""):
    """Return the rows matching the entered filters.

    `rows_to_show` restricts rows by QA scope (None keeps every row), `flags` keeps rows with any
    selected QA flag, `enumerators` keeps rows whose enumerator label is selected, and `search` is a
    literal case-insensitive match across text columns. Selected filters combine with AND.
    """
    visible = df
    if rows_to_show is not None:
        visible = visible[visible.index.isin(rows_to_show)]
    if flags:
        mask = pd.Series(False, index=visible.index)
        for name in flags:
            if name in visible.columns:
                # Coverage-mismatch flags carry a suffix; the other flags are a plain "Yes".
                mask = mask | visible[name].astype("string").str.startswith("Yes", na=False)
        visible = visible[mask]
    if enumerators and enumerator_values is not None:
        visible = visible[enumerator_values.loc[visible.index].isin(enumerators)]
    if search:
        mask = pd.Series(False, index=visible.index)
        for name in visible.select_dtypes(include=["object", "string"]).columns:
            mask = mask | visible[name].astype(str).str.contains(search, case=False, na=False, regex=False)
        visible = visible[mask]
    return visible
