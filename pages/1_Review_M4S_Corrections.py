"""Streamlit page for proposing and explicitly approving M4S corrections."""
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

from correction_review import apply_approved_corrections, suggest_corrections
from m4s_seagrass_qa import load_data, standardize

st.set_page_config(page_title="Review M4S Corrections", page_icon="🧾", layout="wide")
st.title("Review M4S Corrections")
st.write(
    "This page suggests possible spelling and label corrections. Nothing is changed "
    "until you explicitly approve individual proposals. Always verify names and locations "
    "against the field record."
)

uploaded = st.file_uploader("Upload the M4S KoboToolbox Excel export (.xlsx)", type=["xlsx"])
if uploaded is None:
    st.info("Upload an export to generate reviewable proposals.")
    st.stop()

try:
    with tempfile.TemporaryDirectory(prefix="m4s_review_") as temp_dir:
        input_path = Path(temp_dir) / uploaded.name
        input_path.write_bytes(uploaded.getvalue())
        raw_df, working_df = load_data(str(input_path))
    working_df = standardize(working_df)
except Exception as exc:
    st.error(f"Could not load this export using the configured M4S schema: {exc}")
    st.stop()

proposals = suggest_corrections(working_df)
st.metric("Correction proposals", len(proposals))
if proposals.empty:
    st.success("No candidate corrections were found by the current rules.")
    st.stop()

st.warning("Similarity is not proof. Do not approve a proposal unless you have verified it.")
approved_ids = []
for _, proposal in proposals.iterrows():
    label = (
        f"{proposal['field']}: {proposal['current_value']!r} → "
        f"{proposal['suggested_value']!r} "
        f"({proposal['similarity']}% similarity; {proposal['affected_rows']} rows)"
    )
    if st.checkbox(label, key=f"proposal_{int(proposal['proposal_id'])}"):
        approved_ids.append(int(proposal["proposal_id"]))
    st.caption(proposal["reason"])

if st.button("Apply selected corrections", type="primary", disabled=not approved_ids):
    corrected, log = apply_approved_corrections(working_df, proposals, approved_ids)
    st.success(f"Applied {len(log)} row-level changes. Download and review both files.")
    st.subheader("Preview of corrected data")
    st.dataframe(corrected, use_container_width=True)
    st.download_button(
        "Download corrected dataset (CSV)", corrected.to_csv(index=False),
        file_name="m4s_corrected_reviewed.csv", mime="text/csv",
    )
    st.dataframe(log, use_container_width=True)
    st.download_button(
        "Download correction audit log (CSV)", log.to_csv(index=False),
        file_name="m4s_approved_correction_log.csv", mime="text/csv",
    )
