# Manual UI verification checklist

Use this checklist before releasing a change that affects either Streamlit workflow. Automated tests and compilation are not substitutes for exercising the UI. Record the app version/commit, browser, date, tester, and outcome for each run. Use synthetic or approved anonymized data; never commit real survey exports.

## M4S seagrass XLSX workflow (m4s_app.py)

- [ ] App starts and the M4S workflow can be selected.
- [ ] A valid XLSX export loads and reaches the findings/results view.
- [ ] An XLSX missing a required canonical field shows a useful schema error and no partial QA output.
- [ ] An unsupported or malformed file gives a recoverable error rather than a traceback.
- [ ] A synthetic record beyond the centroid-distance threshold is labelled for review, not described as proven outside the site polygon.
- [ ] Findings, row-level QA flags, correction log, and report exports are usable and agree with the displayed results.
- [ ] The original uploaded data remains distinguishable from standardized, corrected, and QA-annotated outputs.

## Generic Kobo CSV workflow

- [ ] A valid CSV loads while identifiers with leading zeroes remain strings.
- [ ] Empty, malformed, and duplicate-header CSV cases are rejected with understandable messages.
- [ ] Missing-value, duplicate, optional outlier, and explicit JSON-contract checks can be enabled and disabled as intended.
- [ ] A contract rule that references a missing column is reported as a file-level finding.
- [ ] A clean run states only that enabled checks produced no findings.
- [ ] Findings table filters work and the displayed count matches the filtered rows.
- [ ] Findings CSV downloads successfully.
- [ ] Downloaded source bytes match the uploaded file byte-for-byte.

## Usability and recovery

- [ ] Keyboard navigation reaches uploads, options, tabs, tables, and download controls in a sensible order.
- [ ] Error and warning meaning is conveyed by text, not color or icon alone.
- [ ] Wide tables and controls remain usable at a narrow viewport.
- [ ] No real field data is sent to an external service or committed to the repository.

## Evidence record

- App/commit: 
- Browser/OS: 
- Date and tester: 
- Failed checks and issue links: 
- Overall result: **Not run** until this record is completed by a human tester.
