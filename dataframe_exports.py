"""Excel export helpers shared by the Streamlit app and tests."""

from __future__ import annotations

import datetime as dt
import io

import pandas as pd


def _excel_safe_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Copy a frame and preserve timezone-aware timestamps as ISO 8601 text.

    Excel has no timezone-aware datetime cell type. Text keeps the timestamp's
    explicit UTC offset instead of silently changing or dropping timezone data.
    """
    safe = frame.copy()
    for column in safe.columns:
        series = safe[column]
        if isinstance(series.dtype, pd.DatetimeTZDtype):
            safe[column] = series.map(lambda value: value.isoformat() if pd.notna(value) else None)
            continue

        if series.dtype == object:
            def preserve_timezone(value):
                if isinstance(value, (dt.datetime, pd.Timestamp)) and value.tzinfo is not None:
                    try:
                        if value.utcoffset() is not None:
                            return value.isoformat()
                    except (TypeError, ValueError):
                        pass
                return value

            safe[column] = series.map(preserve_timezone)
    return safe


def dataframe_to_xlsx(frame: pd.DataFrame, *, sheet_name: str = "Data") -> bytes:
    """Serialize a dataframe as a real XLSX workbook for Excel-friendly downloads."""
    buffer = io.BytesIO()
    safe_sheet_name = sheet_name[:31] or "Data"
    safe_frame = _excel_safe_frame(frame)
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        safe_frame.to_excel(writer, sheet_name=safe_sheet_name, index=False)
        worksheet = writer.book[safe_sheet_name]
        worksheet.freeze_panes = "A2"
        worksheet.auto_filter.ref = worksheet.dimensions
        worksheet.sheet_view.showGridLines = False
    return buffer.getvalue()
