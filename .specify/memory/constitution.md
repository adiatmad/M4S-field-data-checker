# M4S Field Data QA — Engineering Constitution

## I. Human review remains authoritative
Automated findings identify records worth checking. They must not be presented as definitive proof that a survey response is wrong.

## II. Keep generic and project-specific rules separate
Generic CSV quality checks must not inherit M4S-specific schema, species, geography, or threshold assumptions. Project-specific checks must be explicit and configurable where the product requires it.

## III. Preserve source data and provenance
Do not silently discard, reorder, rename, or coerce source fields. Any cleaned output must have documented transformations and a reviewable correction log. Raw exports must preserve the agreed source rows and columns.

## IV. Make uncertainty explicit
Unknown headers, ambiguous question semantics, missing optional fields, and heuristic matches must remain identifiable. Never invent a meaning for an unfamiliar field.

## V. Protect survey data
Treat uploaded survey files and photos as sensitive project data. Do not add telemetry, external uploads, or retention beyond the user's stated workflow.

## VI. Test data behavior
Changes to validation, correction, or exports require representative regression fixtures. Verify row counts, field preservation, error/warning separation, and workbook/ZIP contracts.

## VII. Honest delivery
Inspect the diff and run relevant tests. Report actual commands, results, and any real-Kobo or manual acceptance that remains unverified.

## Governance
Keep the README, field-team guide, configuration, and implementation aligned. Amend this constitution only when the project-wide data and QA contract changes.
