# User Guide: M4S Field Data QA Checker

This guide is for **field enumerators and field coordinators**. It explains how to check survey exports, understand findings, and download reports. You do not need to know Python or how the checker is built.

> **Important:** A finding means “please review this,” not automatically “the data is wrong.” Check the original KoboToolbox submission and follow the approved M4S field protocol before changing data.

## 1. Choose the correct workflow

Answer **Which file did you download from KoboToolbox?** in the left sidebar.

| Your file | Choose |
|---|---|
| An Excel `.xlsx` export of the M4S seagrass survey from KoboToolbox | **Excel file (.xlsx) from the M4S seagrass survey** |
| A general KoboToolbox survey exported as a `.csv` file | **CSV file (.csv) from another KoboToolbox survey** |

These workflows do different checks. The M4S workflow contains project-specific rules for the M4S seagrass survey. The generic workflow checks general file quality and does not know the meaning of every survey question.

## 2. Before you upload

1. Export the data from KoboToolbox.
2. Keep the original export unchanged as your source copy.
3. Confirm you have the correct file type: `.xlsx` for M4S or `.csv` for the generic checker.
4. Use only a deployment approved by your team for real field data. Uploaded files are processed on the server where the app runs. A hosted app is not automatically private just because it is opened in a browser. If you are unsure, ask your coordinator whether to use the approved local deployment.

The M4S upload screen currently states a **200 MB per-file limit**.

## 3. Excel (.xlsx) workflow for the M4S seagrass survey

### Step 1 — Upload the KoboToolbox Excel export

Choose **Excel file (.xlsx) from the M4S seagrass survey**, then upload the `.xlsx` export in Step 1. If you are new to the checker, open **First time here? Read this before you start** and **What this checker does and does not check** first. Wait for the checks to finish.

If processing stops with an error, read the message. Check that you uploaded the correct file and that it contains the expected M4S survey columns. If the problem remains, report the error to the coordinator or person maintaining the app. Do not share a real survey export in a public issue or chat.

### Step 2 — Read the summary

The summary includes measures such as:

- **Total records:** the number of survey records processed.
- **Records with no finding:** records for which the active checks did not report a finding.
- **Errors and warnings:** findings that need attention.
- **Automatic corrections:** changes made by the workflow's standardization and correction steps, recorded in the **What changed** tab and in the correction log download.

A row without a finding is not guaranteed to be correct. The checker only tests the rules it knows.

### Step 3 — Find the records that need review

Use the available filters to narrow the data:

- **Show only records with a finding** to focus on flagged records.
- **Only these kinds of finding** to show particular types of finding. Leaving it empty shows records with any kind of finding.
- **Search the table** to look for a value or record.
- **Only records with a written explanation** to focus on records that have a message.

The filters work together. Combine them in any order, and clear a filter to see more records. If no record matches, the page says so instead of showing a blank table.

The app normally previews the first 10 rows. An expandable section can show the full filtered table. Use filters to investigate; they do not edit the original KoboToolbox submission.

### Step 4 — Understand common M4S flags

| Flag | What it means | What to do |
|---|---|---|
| `qa_missing_coordinates` | Latitude or longitude is missing. | Check the original submission and location capture. Do not invent coordinates. |
| `qa_gps_precision_0` | GPS precision is recorded as 0.0. This may indicate that the device did not obtain a usable fix. | Review the source record and field context. |
| `qa_outside_boundary` | The point is more than 500 m from the configured site reference centroid. This is a distance warning, not a true polygon-boundary test. | Check coordinates, site assignment, and the approved site boundary. |
| `qa_duplicate_uuid` | A submission UUID appears more than once. | Compare the records and check with the coordinator before removing anything. |
| `qa_species_logic` | A species-presence or species-cover rule may not be satisfied. For example, a species marked present may have no valid non-zero cover value. | Compare the species and cover fields with the original record and field protocol. |
| `qa_missing_general_condition` | The seagrass general-condition answer is missing or was not recognized in the expected field. | Check the answer and the active form's field label. |
| `qa_coverage_mismatch` | The sum of species percentages does not match the Epicover percentage within the configured tolerance. | Recalculate and compare with the approved M4S protocol. The checker uses a 5-percentage-point tolerance, which should be confirmed against the current protocol. |

The message column may contain multiple messages separated by semicolons. Read all messages for a row before deciding what needs to be checked.

### Step 5 — Download the right output

The M4S workflow offers different outputs for different tasks:

- **Raw data with QA flags and messages**: the source rows with QA information added. Most teams open this file first.
- **QA issues list**: a list of findings to investigate.
- **Summary report**: a short overview of the findings, under the **Summary report** tab.
- **What changed**: every automatic change, under the **What changed** tab and in the correction log download.
- **Cleaned data**: the processed dataset, under the **Cleaned data** tab. Review its findings and the change list before using it.
- **Filtered view**: the records currently shown by your filters.

Use the correction log to understand changes. Keep the original export and do not treat the cleaned dataset as automatically approved.

### Step 6 — Review suggested name and geography corrections

Some names or geography values may be offered as suggestions because they look similar to a known value. Similarity does not prove that two values refer to the same person or place.

1. Open **Review suggested name and geography corrections**.
2. Read each proposed change.
3. Select only changes you can justify from an authoritative source.
4. Apply the selected corrections to a review copy.
5. Download and inspect the reviewed dataset and approved-correction audit log.

Do not approve a correction only because the spelling looks more familiar. Ask the coordinator if the correct value is uncertain.

### Step 7 — Create enumerator-specific error reports

The **Enumerator-specific error reports** section creates reports for field follow-up. The switches control which findings appear in enumerator-facing reports; they do **not** delete findings from the full internal QA results.

- **Include GPS precision / accuracy checks** — include or hide GPS precision findings in enumerator reports.
- **Include GPS site-distance warnings** — include or hide site-distance warnings.
- **Include Tetum / categorical capitalization checks** — include or hide these text-formatting findings.

Choose the switches according to your team's review process, then select the download that matches your task:

| Download | Use it for |
|---|---|
| **Download enumerator error logs (.zip)** | A ZIP containing separate Excel workbooks for enumerators. |
| **Download enumerator error reports (Excel .xlsx)** | A combined Excel workbook for reviewing enumerator reports together. |
| **Download full raw data + error messages per enumerator (.zip)** | Follow-up that needs each enumerator's source rows plus an `Error Message` column. This export includes errors; warnings are excluded. |

Where the KoboToolbox export contains a photo URL, the report can include a direct link to that photo. If the source has no photo URL, the report cannot create one.

**Privacy and access:** These switches are report filters, not security permissions. They do not make the underlying findings private from someone who can access the app or other outputs. Share reports only with the intended team members.

**Screenshot note:** The screenshot supplied for this guide shows the three report switches and download buttons. It is not embedded in this document yet; add the approved screenshot asset under `docs/images/` and link it here when the image is committed to the repository.

## 4. CSV workflow for other KoboToolbox surveys

Use this workflow for a general survey CSV when you want broad quality checks rather than the M4S-specific seagrass rules.

### Step 1 — Upload a CSV

Choose **CSV file (.csv) from another KoboToolbox survey** and upload the `.csv` file in Step 1. The app processes the uploaded file on the server where it runs. Use an approved local deployment for sensitive data unless your team has reviewed the hosted deployment's protections.

### Step 2 — Choose the checks

The available options can include:

- **Missing-value tokens:** values such as blank cells, `NA`, `N/A`, or `NULL` that should be treated as missing for the check. Review this list if your survey uses any of these strings as legitimate answers.
- **Check exact duplicate rows:** flags rows whose complete contents match. It does not delete either row.
- **Screen numeric-looking columns for outliers (IQR):** flags unusual numeric values for review. An unusual value may still be valid.
- **Suggest similar text values:** optional suggestions for spelling, spacing, or capitalization variants. This is a review aid, not an automatic correction.
- **Validation contract JSON:** an optional set of explicit rules for required columns, allowed values, data types, numeric ranges, or unique keys. Use only a contract supplied or approved by the survey owner.

The generic checker keeps CSV values as text during checks to help preserve identifiers such as `0012`. It does not automatically correct the CSV.

### Step 3 — Review the results

The results summary shows the number of rows, columns, findings, and rows with a finding. Filter findings by category and review the findings preview. The app previews the first 10 findings; the input preview can show the first 100 rows. Row numbers count the header as row 1, so row 2 is the first survey record.

Finding categories can include:

- **Structure:** the CSV may be malformed or have a resource-level problem.
- **Missing:** a configured missing value was found.
- **Duplicate:** an exact duplicate row was found.
- **Schema / contract:** a file or value did not meet a supplied structural rule.
- **Anomaly:** a value was flagged by the statistical outlier check.
- **Similar text:** values may be spelling, spacing, or capitalization variants.

Outlier checks need enough numeric values to be useful. Small samples or columns with too few distinct values may be skipped. Do not treat a flagged outlier as wrong without checking the source.

### Step 4 — Download results

- Download the **findings workbook** to investigate issues.
- Download the **input workbook** if you need an Excel copy for review.

The downloaded input workbook is for inspection; the generic workflow does not automatically correct the original CSV. Make approved changes in your normal data-management process, keep an audit trail, and rerun the checker on the revised export if needed.

## 5. A safe review process for field teams

1. Keep an unchanged copy of the original export.
2. Assign findings to the person who can check the source submission.
3. Confirm issues against KoboToolbox, the survey form, and the approved field protocol.
4. Record what was changed, why it was changed, and who approved it.
5. Rerun the relevant checks after approved edits.
6. Store and share exports only in approved locations.

Do not publish personal information, precise field locations, raw submissions, credentials, or photo links in public repositories or public support requests.

## 6. When to ask for help

Contact the field coordinator or app maintainer when:

- the upload is rejected or processing stops;
- a required column is missing or appears under an unexpected name;
- a flag seems inconsistent with the approved form or protocol;
- a proposed name/geography correction is ambiguous;
- you are unsure which report to share; or
- you need a rule changed.

When reporting a problem, share the error text and a small, anonymized example where possible. Do not send the full raw survey file unless your team's approved process explicitly permits it.

## 7. Quick glossary

- **Record / row:** one submitted survey observation in the exported table.
- **Finding / flag:** a possible data-quality issue reported by a check.
- **Error:** a finding that the current rules classify as an error; it still needs source review.
- **Warning:** a reason to investigate, not proof of an error.
- **Enumerator:** the person who collected the field data.
- **Correction log / audit log:** a record of changes made or approved.
- **CSV:** a plain-text table file, often exported from KoboToolbox.
- **XLSX:** an Excel workbook.
- **JSON contract:** an optional file of explicit validation rules for the generic CSV workflow.
