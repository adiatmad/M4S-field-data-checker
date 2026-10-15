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

## Validation
Automated tests must verify known aliases, preservation of raw headers and unknown fields, value normalization, XLSX loading, and fail-closed behavior when required fields are genuinely missing. Use a sanitized export fixture; never commit real field submissions or GPS data.

## Out of scope
This compatibility layer does not change the site boundary, GPS thresholds, species list, scientific QA rules, or correction policy. Those require separate evidence and domain review.
