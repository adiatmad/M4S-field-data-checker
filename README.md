# M4S Field Data QA Checker

A Streamlit application and command-line pipeline for quality assurance of M4S seagrass field data exported from Kobo.

## What it does

The project provides two entry points:

- `m4s_app.py` — Streamlit interface for uploading a raw Kobo XLSX export, reviewing QA flags, filtering records, and downloading QA outputs.
- `m4s_seagrass_qa.py` — command-line QA pipeline for processing a Kobo XLSX export.

The QA pipeline checks areas including GPS data, seagrass species logic, percentage fields, mandatory fields, timestamps, photos, duplicate submissions, and coverage mismatches. It also applies defined safe corrections and records those changes in a correction log.

## Requirements

Python 3 and the packages listed in `requirements.txt`.

## Streamlit app

```bash
pip install -r requirements.txt
streamlit run m4s_app.py
```

Upload the raw Kobo XLSX export in the browser.

## Command line

```bash
python3 m4s_seagrass_qa.py <raw_kobo_export.xlsx> [output_dir]
```

The pipeline writes QA flags, the cleaned dataset, issue and correction CSVs, and a Markdown QA report to the output directory.

## Data handling

The Streamlit interface states that uploaded data is processed within the session and provides outputs for download rather than saving them to a server.

## License

See [LICENSE](LICENSE).
