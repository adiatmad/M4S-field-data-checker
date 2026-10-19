# M4S Field Data QA Checker

**Found mistakes in your KoboToolbox survey data before you use it in a report, map, or analysis.**

This tool checks downloaded survey files and highlights things worth reviewing, such as missing answers, duplicate records, unusual values, and problems with GPS coordinates. You do not need to be a programmer to use the Streamlit app, but you will need to install it or open a version hosted by your team.

It has two workflows. Choose the one that matches the file you downloaded.

## Start here: Which file do you have?

### I have a CSV file from KoboToolbox

Choose **Generic Kobo CSV checker** if you want general checks for a survey export.

It can help you:
- find blank or missing values;
- identify rows that look exactly alike;
- optionally suggest similar categorical text values (such as spelling, spacing, or capitalization variants) for human review;
- check whether the file's columns and values have basic structural problems;
- flag unusual numeric values for you to review; and
- download a list of findings to investigate.

It does **not** know what every question in your survey means. For example, it cannot reliably decide whether a species observation is ecologically possible unless the appropriate survey rules have been supplied.

### I have an Excel (.xlsx) export for the M4S seagrass survey

Choose **M4S seagrass QA** for the project's specific checks. These include GPS locations, species-related fields, percentage fields, seagrass general condition, required answers, timestamps, photos, duplicates, and species-cover/total-cover mismatches. GPS precision is optional in the input export: when absent, coordinate and site-distance checks still run. The app can also download separate enumerator error logs with direct Kobo photo URLs and optional GPS-accuracy/site-distance findings hidden from enumerator-facing reports. The report switches can independently include or hide GPS precision, site-distance, and Tetum/categorical text-variant findings. They are configuration controls, not role-based access control.

Enumerator-name normalization and geography typo correction have separately configurable similarity thresholds in the M4S workflow. Higher thresholds are more conservative; review the correction log before using the cleaned output. These checks include assumptions specific to the M4S project, such as expected columns and site locations. Do not use them for another survey without reviewing those assumptions first.

## What happens to my data?

1. **You upload your export.** The tool reads the file you selected.
2. **It checks for possible problems.** Findings explain what needs attention and, where available, identify the row and column.
3. **You review the findings.** A warning is a reason to investigate, not proof that a record is wrong.
4. **You download the results.** Depending on the workflow, you can download a findings list or QA outputs for further review.

The generic CSV checker keeps CSV values as text during checks, so an identifier like `0012` is not silently changed to `12`. It does not automatically correct your original CSV. The M4S-specific command-line workflow can make a limited set of documented corrections; it also keeps a raw copy and correction log in its output.

**Important:** A result with no findings means only that the checks you ran did not report a problem. It does not prove that every answer is correct.

## How to run the app

If your team already provides a hosted version, follow their instructions and check how your data is handled before uploading it. Otherwise, you can run the app on your own computer.

You will need Python installed.

1. Download or clone this repository.
2. Open a terminal in the project folder.
3. Create and activate a Python environment, then install the required packages.
4. Start the app with the command below.

```bash
python -m venv .venv
# Windows:
.venv/Scripts/Activate.ps1
# macOS/Linux:
source .venv/bin/activate

python -m pip install -r requirements.txt
streamlit run m4s_app.py
```

The app opens in your browser. Choose the workflow that matches your file and follow the on-screen instructions.

For the standalone generic CSV checker, you can also run:

```bash
streamlit run kobo_csv_quality_app.py
```

## Optional: Run the M4S checks from the command line

This is for users who are comfortable using a terminal or need to process a file in a repeatable batch workflow:

```bash
python3 m4s_seagrass_qa.py raw_export.xlsx
```

By default, the results are written to an `output/` folder. You can choose another output folder as the second argument.

## Important limits

- **This tool supports review; it does not replace your survey form or field protocol.** For complete checks of required answers, skip logic, choices, and repeat groups, the matching KoboToolbox XLSForm or another authoritative schema may be needed.
- **Do not accept a flag blindly.** Check the original record and the survey context before deciding what to change.
- **Unusual values are not automatically errors.** An outlier may be a genuine observation. Similar-text suggestions can also be false positives; they are opt-in review aids, not automatic corrections.
- **Survey-specific rules need evidence.** Ecological thresholds and species rules should match the approved M4S protocol. Species cover is compared with Epicover using a 5-percentage-point tolerance; confirm this tolerance and the meaning of Epicover against the current field protocol before treating the check as authoritative.
- **Protect field data.** The apps process uploaded files on the server where they run. Running locally keeps processing on your computer; before using a hosted version, confirm its access controls, retention, and data-protection arrangements. Never commit real survey exports, credentials, or personal information to this repository.

## For developers and advanced users

- `m4s_app.py` — main Streamlit app with both workflows.
- `kobo_csv_quality_app.py` and `kobo_csv_quality.py` — standalone generic CSV checker and its reusable validation functions.
- `csv_contract.py` — optional checks based on rules explicitly provided in a JSON contract. It does not infer survey meaning or implement all XLSForm logic.
- `m4s_seagrass_qa.py` — standalone M4S-specific command-line QA workflow.

Read [docs/SPEC.md](docs/SPEC.md), [docs/VALIDATION_RULES.md](docs/VALIDATION_RULES.md), the [Loop and Graph contract](docs/LOOP_GRAPH_CONTRACT.md), and the [UI/UX guidelines](docs/UI_UX_GUIDELINES.md) for implementation details and validation behavior.

## Tests

Run the automated tests from the repository root:

```bash
python -m pytest -q
```

The test suite covers the generic CSV checker and validation failure handling. Automated tests do not replace a manual walkthrough of the Streamlit interface or validation against a real, approved survey export.

## License

See [LICENSE](LICENSE). The repository is licensed under AGPL-3.0.


## Optional: Review M4S corrections before applying

The M4S workflow includes a collapsed **Review suggested name and geography corrections** section on the same page as the QA findings. Nothing is changed until you explicitly approve individual proposals. Approved changes can be downloaded with a before/after audit log. Keep the raw export unchanged and verify proposals with the field team. See [the correction review workflow](docs/CORRECTION_REVIEW.md).
