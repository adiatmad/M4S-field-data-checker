# M4S Kobo schema compatibility

## Problem
The M4S QA pipeline originally required English column labels, but the current Metinaro field export uses Tetun labels. The data are structurally compatible; rejecting the export based only on label language blocks QA before validation can run.

## Contract
- Keep the uploaded DataFrame unchanged as the raw source for export and auditing.
- Build a separate working copy with explicit, reviewed header aliases for the known Tetun M4S form.
- Normalize the known Tetun yes/no values (`Sim`/`Lae`) only in the canonical seagrass-presence field.
- Preserve unknown headers and values.
- Never infer a required field from similarity or silently combine two source columns into one canonical field.
- If required fields remain absent after known aliases are applied, stop with a useful error listing missing canonical fields and available headers.

## Supported aliases
Core metadata: `Naran Koletor`, `Data no Horas`, `Postu Administrativu`, `Suku`, `_GPS Lokal_latitude/longitude/altitude/precision`, `Numeru Tranjektu`, `Numeru Quadrante`.

QA inputs: the Tetun seagrass-presence and species-selection fields, algal/epicover percentage fields, species percentage fields, and quadrat-photo URL are mapped to their existing canonical names by explicit aliases.

## Upstream findings and export guidance

KoboToolbox's XLSForm guidance distinguishes stable structural names from translated labels: question names are not translated, while labels are. Its own export code also documents a `lang=_xml` option for using question and choice names instead of labels (see [KoboToolbox KPI export implementation](https://github.com/kobotoolbox/kpi/blob/master/kpi/models/import_export_task.py) and [XLSForm language guidance](https://github.com/kobotoolbox/docs/blob/master/source/language_xls.md)).

**Preferred workflow for future exports:** where the Kobo API export workflow is available, request XML/question names (`lang=_xml`) and verify the resulting headers against the form's actual question names before relying on them. Do not guess field names: grouped questions, repeats, and system fields can have specific export names. The current explicit Tetun-label adapter remains necessary for existing manually exported workbooks and continues to fail closed when required fields cannot be identified.

Header matching now ignores Unicode-equivalent forms and leading, trailing, or repeated whitespace for known aliases only. It does not translate arbitrary headers, fuzzy-match required fields, or rewrite unknown source headers.

## Validation
Automated tests must verify known aliases, preservation of raw headers and unknown fields, value normalization, XLSX loading, and fail-closed behavior when required fields are genuinely missing. Use a sanitized export fixture; never commit real field submissions or GPS data.

## Out of scope
This compatibility layer does not change the site boundary, GPS thresholds, species list, scientific QA rules, or correction policy. Those require separate evidence and domain review.
