# Specification: generic Kobo CSV quality checks

## Goal
Add a reusable, local-first validation path for raw KoboToolbox CSV exports without removing the existing M4S seagrass XLSX-specific workflow.

## Users
Field coordinators, data managers, and survey teams who need actionable flags before analysis.

## MVP requirements
- Accept CSV uploads and preserve identifier values such as IDs with leading zeroes.
- Run Frictionless resource/CSV structure validation.
- Run Pandera dataframe schema validation without inventing domain-specific constraints.
- Flag configurable missing-value tokens, exact duplicate rows, and optional numeric IQR outliers.
- Show finding category, severity, row number, column, and explanation.
- Export findings as CSV and allow download of the unchanged input.
- Keep survey content out of external services; no telemetry or AI processing.

## Non-goals
- No automatic edits to source records.
- No assumption that every numeric outlier is an error.
- No automatic inference of skip logic, repeat groups, or XLSForm constraints in this generic MVP.
- No claim of complete Kobo schema validation without the XLSForm or an explicit schema.

## Acceptance criteria
1. The app can be run locally using the README instructions.
2. CSV identifiers remain strings.
3. Empty input and duplicate headers produce understandable errors.
4. Findings include a usable row reference and column where applicable.
5. Automated tests cover parsing, missing values, duplicates, and empty summaries.
6. Existing M4S-specific app and CLI remain available.
