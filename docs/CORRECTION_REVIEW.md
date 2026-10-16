# Correction review workflow

The **Review M4S Corrections** page is a separate, human-in-the-loop workflow for possible
collector-name and project geography spelling corrections.

## Safety contract

- Generating proposals never mutates the input dataframe.
- No correction is applied by default.
- A user must explicitly select each proposal before applying it.
- Applied row-level changes are exported with before/after values, UUID (when available),
  field, rule, and timestamp.
- The original uploaded export is not overwritten.
- Similarity scores are candidate-generation evidence, not proof that values are equivalent.

## Scope and limitations

The page is available as a Streamlit multipage entry at `pages/1_Review_M4S_Corrections.py`.
It uses the existing M4S XLSX schema and current configured canonical labels (Metinaro and
Sabuli). It does not modify the existing legacy QA pipeline or its command-line output.
Collector-name proposals are deliberately conservative, but still require field-team review.
The exported corrected CSV is a new artifact; retain the raw export and inspect the audit log
before using corrected values downstream.
