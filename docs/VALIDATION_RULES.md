# Validation rules and interpretation

| Check | Engine | Severity | Interpretation |
|---|---|---|---|
| CSV/resource structure | Frictionless | Error | The file may be malformed or contain resource-level issues; inspect the report. |
| Blank/configured missing token | Custom | Warning | A value may be absent; whether it is required depends on the survey. |
| Exact duplicate row | Custom | Warning | Two complete rows match; verify before removing either. |
| DataFrame schema stage | Pandera | Error if emitted | Generic structural schema stage only; domain-specific types and constraints require an explicit schema. |
| Numeric IQR outlier | Custom | Warning | Statistical screening only; valid extreme observations are possible. |
| Explicit JSON contract | Custom | Error | Checks only user-supplied required columns, allowed values, types, numeric bounds, and key uniqueness; no automatic correction. |

Row numbers refer to CSV data rows with the header as row 1 (so the first data record is row 2). Schema failures that cannot be mapped to an original row are shown without a row number.

Never auto-delete duplicates, impute missing values, or auto-correct anomalies. Confirm findings with the survey owner and, where possible, the XLSForm's required/constraint/relevant logic.


## Explicit JSON contract

The generic checker optionally accepts a JSON contract. Contract row references use the same convention as other CSV findings: the header is row 1 and the first data row is row 2. Missing required columns, missing key columns, and columns referenced by rules but absent from the CSV are file-level findings without a row number. A rule that references a missing column is reported instead of being silently skipped. Duplicate key values are reported for each involved row; investigate before editing or deleting records. Invalid contract syntax/rules stop that validation stage rather than being silently ignored.


## M4S GPS site-distance alert

The M4S GPS check compares each coordinate with one configured reference centroid and a 500 m radius. A point beyond that radius is a **review warning**, not proof that it lies outside the actual site polygon. Check the latitude/longitude values, coordinate reference system (CRS), and site assignment. A true polygon-containment check requires the authoritative site boundary geometry; the current centroid-only check does not perform one.
