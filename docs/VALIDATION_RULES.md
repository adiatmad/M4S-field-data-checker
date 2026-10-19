# Validation rules and interpretation

| Check | Engine | Severity | Interpretation |
|---|---|---|---|
| CSV/resource structure | Frictionless | Error | The file may be malformed or contain resource-level issues; inspect the report. |
| Blank/configured missing token | Custom | Warning | A value may be absent; whether it is required depends on the survey. |
| Exact duplicate row | Custom | Warning | Two complete rows match; verify before removing either. |
| DataFrame schema stage | Pandera | Error if emitted | Generic structural schema stage only; domain-specific types and constraints require an explicit schema. |
| Numeric IQR outlier | Custom | Warning | Statistical screening only; valid extreme observations are possible. |
| Similar text values (opt-in) | RapidFuzz similarity | Warning | Suggests likely spelling, whitespace, or capitalization variants in low-cardinality text columns; review manually. Some matches will be false positives. |
| Explicit JSON contract | Custom | Error | Checks only user-supplied required columns, allowed values, types, numeric bounds, and key uniqueness; no automatic correction. |

Row numbers refer to CSV data rows with the header as row 1 (so the first data record is row 2). Schema failures that cannot be mapped to an original row are shown without a row number.

Never auto-delete duplicates, impute missing values, or auto-correct anomalies. Confirm findings with the survey owner and, where possible, the XLSForm's required/constraint/relevant logic.


## Explicit JSON contract

The generic checker optionally accepts a JSON contract. Contract row references use the same convention as other CSV findings: the header is row 1 and the first data row is row 2. Missing required columns, missing key columns, and columns referenced by rules but absent from the CSV are file-level findings without a row number. A rule that references a missing column is reported instead of being silently skipped. Duplicate key values are reported for each involved row; investigate before editing or deleting records. Invalid contract syntax/rules stop that validation stage rather than being silently ignored.


## M4S GPS site-distance alert

The M4S GPS check compares each coordinate with one configured reference centroid and a 500 m radius. A point beyond that radius is a **review warning**, not proof that it lies outside the actual site polygon. Check the latitude/longitude values, coordinate reference system (CRS), and site assignment. A true polygon-containment check requires the authoritative site boundary geometry; the current centroid-only check does not perform one.


## Similar text value suggestions

This opt-in generic check compares distinct text values only in columns with 2–100 distinct values, uses a 90% similarity threshold by default, and skips identifier-, URL-, location-coordinate-, date/time-, and numeric-only columns. It reports source row numbers and warnings; it never merges, replaces, or normalizes source values. Similarity is a candidate-generation heuristic, not proof that two values mean the same thing. The current version is intentionally bounded and does not reproduce OpenRefine's full clustering algorithms or interactive operation history.


## Review-before-apply corrections

The optional Streamlit page at `pages/1_Review_M4S_Corrections.py` generates candidate spelling corrections without mutating source values. Only individually approved proposal IDs are applied, and every changed row is recorded in an audit log. The feature does not replace the existing legacy correction pipeline; use the review page when human approval is required. Similarity is not evidence that two collector names refer to the same person.


## M4S conditional seagrass checks

- If a species is selected as present (including numeric/string encodings of 1), its corresponding species-cover percentage must be recorded and non-zero. If the species selection field exists but its cover column is absent, the record is flagged.
- If overall seagrass presence is Yes but no species is selected, the row is an error.
- A seagrass general-condition field must exist and have a nonblank value. The checker recognizes a short list of English and Tetun header variants; confirm the actual field label against the active Kobo XLSForm.
- Missing latitude or longitude is an error. The GPS precision/accuracy column is optional: if it is present, its values are checked; if absent, coordinate and site-distance checks still run. GPS precision and site-distance findings can be hidden from enumerator-facing reports independently.
- Individual species percentages are summed and compared with Epicover Percentage (%) using a 5-percentage-point tolerance. This is a project assumption, not a universal ecological rule; confirm the total field and tolerance with the approved M4S protocol.

## Enumerator error exports

The M4S workflow can produce one CSV per enumerator, sorted by enumerator name, with row-level findings and a photo_url column sourced from the Kobo Quadrat Photo_URL field. If no URL exists in the source export, the field remains blank. The ZIP export is generated locally in the current app process. GPS precision and site-distance findings can be hidden from enumerator-facing reports without deleting them from the full internal findings. These UI switches are not authentication or authorization; deployments needing administrator-only controls must add access control separately.

Basic string whitespace trimming and whitespace collapsing are performed during standardization. Existing logged formatting corrections remain limited to configured enumerator/geography fields; the checker does not automatically title-case arbitrary ecological values or scientific names.


## Tetum and categorical text cleaning

- Known Tetum yes/no answers for seagrass presence are normalized case-insensitively: `Sim`, `SIM`, and other case variants map to Yes; `Lae` variants map to No.
- The M4S validation pipeline warns when low-cardinality text fields contain capitalization variants (for example, `Diak` and `diak`) and suggests likely spelling variants in categorical values (for example, `Diak` and `Di'ak`) for manual review. Similarity is only a candidate signal: it does not prove a typo or infer the correct Tetum meaning. The checker does not automatically rewrite ecological condition values.
- Enumerator-facing CSV exports can include or exclude these text-formatting warnings, independently of the GPS accuracy and site-distance options. The full internal QA findings remain available.
