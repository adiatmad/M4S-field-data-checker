# Repository benchmark and implementation plan

## Scope and method

This is a targeted GitHub repository discovery, not an exhaustive census of GitHub. Searches covered CSV/data validation, KoboToolbox cleaning, ODK validation, biodiversity data quality, and ecological data cleaning. Search results are incomplete by design: repositories with weak descriptions, private code, or different terminology may not appear.

The goal is to identify reusable *patterns* for M4S seagrass field-data QA, not to copy whole applications or add dependencies without a demonstrated need.

## Most relevant references

| Repository | Relevant capability | Decision for this project |
|---|---|---|
| [biodiversity-aq/BiodiversityData_QC_standardWorkflow](https://github.com/biodiversity-aq/BiodiversityData_QC_standardWorkflow) | Biodiversity-specific standardization and content QA, including dates, coordinates, typos, and pseudoreplicates | Use as the closest domain-workflow reference. Adapt rules only when they match M4S field protocol. |
| [frictionlessdata/frictionless-py](https://github.com/frictionlessdata/frictionless-py) | Tabular structure/schema validation and structured reports | Already used by the generic CSV checker. Apply the data-contract mindset to the M4S schema; do not duplicate structural validation unnecessarily. |
| [tdwg/bdq](https://github.com/tdwg/bdq) | Shared biodiversity data-quality concepts, tests, and terminology | Use as a reference for rule definitions and interpretation; it is not a ready-made seagrass checker. |
| [bonschorno/kobojanitor](https://github.com/bonschorno/kobojanitor) | Kobo export cleaning, variable selection, and response-label normalization | Use as a reference for preserving raw export values while mapping known form fields. It is an R package, not a Python dependency to add here. |
| [posit-dev/pointblank](https://github.com/posit-dev/pointblank) | Declarative column, row, and table validations with reporting | Reference for future rule organization. A migration is not justified for this small pipeline. |
| [datacarpentry/OpenRefine-ecology-lesson](https://github.com/datacarpentry/OpenRefine-ecology-lesson) | Ecological data cleaning and clustering of likely misspellings | Keep fuzzy matches as review candidates; do not treat similarity alone as proof that two field values are equivalent. |
| [getodk/validate](https://github.com/getodk/validate) | ODK/XLSForm validation | Useful for validating the form definition itself. It does not replace checks of submitted ecological observations. |
| [getodk/validate](https://github.com/getodk/validate) | ODK/XLSForm form-definition validation | Consider validating the survey form definition separately from the submitted observations; do not confuse form validation with content QA. |

Additional search results included [digital-preservation/csv-validator](https://github.com/digital-preservation/csv-validator), a CSV structural validator, and [alimanfoo/csvvalidator](https://github.com/alimanfoo/csvvalidator), whose README says it is no longer maintained and points users to petl. They are not preferred implementation bases.

## What was changed in this branch

1. **Fail closed on missing M4S schema columns.** Transect, quadrat, seagrass-presence, and quadrat-photo fields are now part of the required schema. A form change should fail with a clear message instead of silently skipping checks.
2. **Treat blank strings as missing.** Required values consisting only of whitespace are flagged.
3. **Keep numeric parse failures visible.** Nonblank values such as `"not-a-number"` are reported as errors before being coerced to `NaN`; they no longer look indistinguishable from genuinely blank optional values.
4. **Make clean runs reportable.** Validation returns a stable issue-table schema even when there are zero findings, and the Markdown report handles an empty findings table.
5. **Stop running the epicover/species-sum check by default.** The rule remains in the code for reference, but is removed from the active pipeline until the survey protocol confirms that the quantities are mathematically expected to match. A plausible-looking scientific rule is not enough evidence to enforce it.

Regression tests were added for missing required columns, whitespace-only required values, invalid numeric values, and zero-issue report generation.

## Important remaining risks

- The 500 m radius around a hard-coded centroid is a screening heuristic, not a true survey polygon boundary. Use an authoritative survey boundary if one is available.
- Fuzzy auto-corrections of enumerator and place names still need a human-review policy and an approved alias list. Similarity scores alone cannot establish identity. This branch does not claim to solve that problem.
- Rules for species presence, species cover, epicover, algae cover, GPS precision, and duplicate transect/quadrat submissions must be checked against the actual M4S protocol/XLSForm.
- The previously uploaded survey export was not rerun in this branch. No finding counts or claims about that dataset are asserted here.
- Passing tests establishes only the behavior covered by those tests; it does not certify the ecological validity of all observations.

## Verification

Run locally:

```bash
python -m compileall -q m4s_seagrass_qa.py m4s_app.py
python -m pytest -q
```

The branch should not be merged until the CI result is inspected and the diff is reviewed. A real-export smoke test should be run locally with sensitive data kept out of Git.
