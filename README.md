# M4S Field Data QA Checker

A Streamlit application and command-line pipeline for quality assurance of M4S seagrass field data exported from KoboToolbox, with an additional generic CSV quality checker for other survey exports.

## Choose your workflow

### Generic raw Kobo CSV checker

Use this when you have a CSV export and want general quality flags without assuming a particular survey form.

- `kobo_csv_quality_app.py` — Streamlit interface for CSV uploads, structure checks, missing values, exact duplicates, and optional numeric outlier screening.
- `kobo_csv_quality.py` — reusable validation functions powered by Frictionless and Pandera.

Run locally:

```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux: source .venv/bin/activate
python -m pip install -r requirements.txt
streamlit run kobo_csv_quality_app.py
```

The app reports findings with category, severity, row reference, column, and message, and lets you download findings as CSV. It preserves CSV values as strings so identifiers such as `0012` are not silently converted to `12`.

**Failure handling:** structural and value validation run through a shared orchestration function. If either stage raises an unexpected error, the app displays a safe failure message and stops the run rather than presenting partial findings as a completed validation. Internal exception details are not exposed in the UI.

### M4S seagrass XLSX workflow

- `m4s_app.py` — single-file Streamlit entry point with two selectable workflows: M4S seagrass XLSX QA and generic Kobo CSV quality checks. The M4S pipeline, generic CSV checks, and optional JSON-contract validation are embedded in this file so the deployed app does not import other project modules at runtime.
- `m4s_seagrass_qa.py` — separate command-line M4S QA pipeline, retained for local/batch use.
- `kobo_csv_quality_app.py`, `kobo_csv_quality.py`, and `csv_contract.py` — original generic-checker implementation retained for modular use and automated tests.

```bash
python -m pip install -r requirements.txt
streamlit run m4s_app.py
# Optional standalone command-line workflow:
python3 m4s_seagrass_qa.py <raw_kobo_export.xlsx> [output_dir]
```

The M4S-specific pipeline checks GPS, seagrass species logic, percentage fields, mandatory fields, timestamps, photos, duplicates, and coverage mismatches. Its domain assumptions (including site coordinates and expected columns) are specific to that project; review them before applying to another survey.

## Privacy

Both Streamlit apps process uploaded data in the server process that runs them. Do not assume hosted uploads remain only on your device. For sensitive field data, run the app locally or verify hosting access controls, retention, and data-protection arrangements before use. Do not commit real survey exports, credentials, or personally identifiable information.

## Limitations

Generic checks are screening aids, not a replacement for the survey's XLSForm. The optional JSON contract validates only rules explicitly supplied by the user; it does not implement XLSForm skip logic, conditional requirements, or repeat groups. A full check of required fields, constraints, skip logic, choices, and repeat groups requires the relevant form/schema. Outlier flags are not automatic errors and source data is never automatically corrected by the generic checker. A clean result means only that the enabled checks emitted no findings; it does not certify the entire survey as valid.

## Repository benchmark

A focused comparison of related biodiversity, Kobo, and data-validation projects—and the implementation decisions they informed—is documented in [`docs/REPOSITORY_BENCHMARK.md`](docs/REPOSITORY_BENCHMARK.md). The M4S pipeline now fails on missing required survey columns, flags whitespace-only mandatory values and invalid numeric strings, and handles clean runs with zero findings. The epicover/species-sum rule is disabled pending confirmation against the field protocol.

## Tests

Run the automated test suite from the repository root:

```bash
python -m pytest -q
```

The generic CSV checker and validation failure handling have regression coverage. GitHub Actions passed dependency installation, Python compilation, and the full test suite for the merged change. Streamlit UI interactions were not separately exercised, so automated checks should not be interpreted as full manual UI or production validation.

See [docs/SPEC.md](docs/SPEC.md), [docs/VALIDATION_RULES.md](docs/VALIDATION_RULES.md), and the [Loop and Graph contract](docs/LOOP_GRAPH_CONTRACT.md) for the validation flow, failure boundaries, and bounded development/verification loop.

## License

See [LICENSE](LICENSE). The existing repository license is AGPL-3.0.
