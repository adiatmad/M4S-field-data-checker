"""Human-reviewed correction proposals for M4S field data.

This module never mutates a dataframe while generating suggestions. A correction is
applied only when the caller explicitly selects its proposal.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

import pandas as pd
from rapidfuzz import fuzz

DEFAULT_THRESHOLD = 85
GEO_CANONICAL = {
    "Administration Post": "Metinaro",
    "Village": "Sabuli",
}
PROPOSAL_COLUMNS = [
    "proposal_id", "field", "current_value", "suggested_value",
    "similarity", "affected_rows", "reason",
]
LOG_COLUMNS = [
    "row_index", "uuid", "field", "rule", "before", "after", "timestamp",
]


def _text(value: object) -> str:
    return " ".join(str(value).replace("_", " ").split()).strip()


def suggest_corrections(
    df: pd.DataFrame, *, threshold: int = DEFAULT_THRESHOLD
) -> pd.DataFrame:
    """Return proposed value mappings without changing source data.

    Collector-name suggestions point to an existing value, selected by frequency
    and a simple formatting preference. Geographic suggestions use the project's
    explicit canonical labels. All proposals require human approval.
    """
    if isinstance(threshold, bool) or not isinstance(threshold, int) or not 80 <= threshold <= 100:
        raise ValueError("Threshold must be an integer from 80 to 100.")

    proposals: list[dict] = []
    next_id = 1

    if "Collector Name" in df.columns:
        series = df["Collector Name"]
        values = [v for v in series.dropna().unique().tolist() if isinstance(v, str) and v.strip()]
        counts = series.value_counts(dropna=True)

        def preference(value: str) -> tuple[int, int, int]:
            # Prefer conventional spacing/case, then the most frequently used spelling.
            normalized = _text(value)
            clean_format = int(value == normalized and "_" not in value)
            title_or_mixed = int(value != value.lower())
            return (clean_format, title_or_mixed, int(counts.get(value, 0)))

        for current in values:
            alternatives = []
            current_norm = _text(current).casefold()
            for candidate in values:
                if candidate == current:
                    continue
                score = int(round(fuzz.token_sort_ratio(current_norm, _text(candidate).casefold())))
                if score >= threshold and preference(candidate) > preference(current):
                    alternatives.append((score, preference(candidate), candidate))
            if alternatives:
                alternatives.sort(reverse=True)
                best_score, _, target = alternatives[0]
                # Avoid proposing a mapping when two distinct alternatives are tied.
                tied = [item for item in alternatives if item[0] == best_score and item[1] == alternatives[0][1]]
                if len({item[2] for item in tied}) > 1:
                    continue
                proposals.append({
                    "proposal_id": next_id, "field": "Collector Name",
                    "current_value": current, "suggested_value": target,
                    "similarity": best_score,
                    "affected_rows": int((series == current).sum()),
                    "reason": "Similar existing collector-name value; confirm spelling with the field team.",
                })
                next_id += 1

    for field, canonical in GEO_CANONICAL.items():
        if field not in df.columns:
            continue
        series = df[field]
        for current in series.dropna().unique().tolist():
            if not isinstance(current, str) or not current.strip() or current == canonical:
                continue
            score = int(round(fuzz.token_sort_ratio(_text(current).casefold(), canonical.casefold())))
            if score >= threshold:
                proposals.append({
                    "proposal_id": next_id, "field": field,
                    "current_value": current, "suggested_value": canonical,
                    "similarity": score,
                    "affected_rows": int((series == current).sum()),
                    "reason": f"Similar to the configured project label {canonical!r}; verify the site assignment.",
                })
                next_id += 1

    return pd.DataFrame(proposals, columns=PROPOSAL_COLUMNS)


def apply_approved_corrections(
    df: pd.DataFrame, proposals: pd.DataFrame, approved_ids: Iterable[int]
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Apply only explicitly approved proposal IDs and return a reversible log."""
    approved = {int(value) for value in approved_ids}
    known = set(proposals["proposal_id"].astype(int)) if not proposals.empty else set()
    unknown = approved - known
    if unknown:
        raise ValueError(f"Unknown proposal IDs: {sorted(unknown)}")

    source = df.copy(deep=True)
    result = df.copy(deep=True)
    log_rows: list[dict] = []
    timestamp = datetime.now(timezone.utc).isoformat()

    selected = proposals[proposals["proposal_id"].isin(approved)] if not proposals.empty else proposals
    for _, proposal in selected.iterrows():
        field = proposal["field"]
        if field not in result.columns:
            raise ValueError(f"Proposal field no longer exists: {field}")
        before = proposal["current_value"]
        after = proposal["suggested_value"]
        # Match against the original snapshot so one approved mapping cannot cascade into another.
        mask = source[field].eq(before).fillna(False)
        for index in result.index[mask]:
            log_rows.append({
                "row_index": index,
                "uuid": result.at[index, "_uuid"] if "_uuid" in result.columns else None,
                "field": field,
                "rule": "human_approved_correction",
                "before": before,
                "after": after,
                "timestamp": timestamp,
            })
        result.loc[mask, field] = after

    return result, pd.DataFrame(log_rows, columns=LOG_COLUMNS)
