# Loop and graph contract

## Decision

Use a **bounded development loop** and a **static validation graph**. Do not add an agent framework, dynamic routing, retries, or orchestration dependencies to this small deterministic Streamlit/CLI project.

The reference concepts come from [Loop & Graph Engineering](https://github.com/FlorianBruniaux/claude-code-ultimate-guide/blob/main/guide/core/loop-graph-engineering.md). This document adapts its control-contract ideas to the actual M4S Field Data QA Checker; it does not claim the application is an agent system.

## 1. Runtime validation graph

### Contract

- **Graph identity:** kobo-csv-quality, version 1.
- **Input:** uploaded CSV bytes and filename; user-selected missing tokens, duplicate check, and outlier check.
- **Privacy:** processing stays in the application process; no external AI/API calls or telemetry are part of this workflow.
- **Source integrity:** never mutate uploaded bytes or automatically correct records.
- **State:** parsed DataFrame, structural findings, value findings, normalized findings, summary. Keep source data in memory for the session only.
- **Acceptance boundary:** checks produce *findings*, not a claim that the survey is valid. Survey-specific requirements need the relevant XLSForm or an explicit schema.
- **Terminal outcomes:** rejected_input, completed_with_findings, completed_clean, or check_failed. A clean result means only that enabled checks emitted no findings.

### Static graph

~~~mermaid
flowchart TD
    A[CSV upload + options] --> B[Parse CSV and validate headers]
    B -->|Invalid input| X[Rejected input: explain error]
    B -->|Parsed| C[Run structural validation]
    B -->|Parsed| D[Run generic value checks]
    C --> E[Normalize findings]
    D --> E
    E --> F[Summarize findings]
    F --> G[Display findings and preview]
    G --> H[Download findings or unchanged source]
    C -. unexpected exception .-> Y[Check failed: surface safe error]
    D -. unexpected exception .-> Y
~~~

The graph describes the intended control flow. The current UI executes the structural and value checks sequentially, not concurrently; both branches depend on successful parsing. An unexpected validator exception should be reported as a check failure rather than presented as a clean result.

### Node contracts

| Node | Input → output | Failure / side-effect policy |
|---|---|---|
| Parse | bytes → string-preserving DataFrame | Reject empty files, invalid encoding, blank or duplicate headers, and malformed CSV. Do not coerce IDs such as 0012 into numbers. |
| Structural validation | original bytes + filename → structure findings | Use Frictionless; preserve normalized row/column/message evidence. Exceptions must not be silently converted to success. |
| Generic checks | DataFrame + options → value findings | Missing values, exact duplicates, generic Pandera stage, optional IQR screening. No source mutation. |
| Normalize | findings from enabled checks → stable issue columns | Keep row_number, column, category, severity, message; make schema/structure findings with no source row explicit. |
| Summarize | findings → counts | Empty findings must return zero counts; affected rows count unique non-empty row references. |
| Present/export | findings + original bytes → UI/downloads | Filtering affects displayed/downloaded findings only. Source download must be byte-for-byte unchanged. |

## 2. Development feedback loop

A code change follows this bounded loop:

1. **Freeze the contract:** state the user-visible behavior and relevant acceptance criteria before editing.
2. **Inspect context:** read the relevant implementation, tests, dependency constraints, and current branch/base revision.
3. **Make the smallest patch:** avoid new frameworks unless a demonstrated requirement cannot be met by the current structure.
4. **Verify:** run targeted tests, then the full test suite; for UI changes, exercise upload, failure, findings, and download paths.
5. **Review evidence:** compare behavior to the requirement and inspect the diff for scope, privacy, and regression risks.
6. **Stop or escalate:** finish only when checks and review support the claim. If a check cannot run, report that limitation. Do not loop indefinitely or describe unrun tests as passing.

### Budget and stop rules

- One focused implementation pass, followed by fixes for concrete verification failures.
- No more than two fix-and-retest cycles for the same failure without reassessing the approach.
- Stop on a missing requirement, destructive/unclear side effect, unexpected privacy exposure, or failing check whose cause is not understood; request human input rather than guessing.
- A successful test command is evidence for the tested behavior only; it is not proof of full survey correctness or production readiness.

## 3. Evidence to retain in a change or pull request

- Base and candidate commit references.
- Changed files and a concise explanation of why each changed.
- Exact verification commands and their exit status/output summary.
- Known untested paths and remaining risks.
- Confirmation that no real survey exports, credentials, or personal data were added to the repository.

Do not add token telemetry, external data transmission, dynamic graph generation, automatic retries, or multi-agent coordination without a separate requirement and threat/operational review.

## 4. Failure boundary (implemented)

The generic checker now routes both validation stages through `run_quality_checks`. Unexpected exceptions are wrapped in `QualityCheckError` with a stage label, without exposing the original exception text to the UI. The Streamlit app displays a safe error and stops the run; it does not summarize or export partial findings as if the checks completed.

Regression tests cover failures in structural and value validation, including the requirement that value checks do not run after structural validation fails. The tests still need to be executed in a configured Python environment before this change can be considered verified.

## 5. References

- [Loop & Graph Engineering guide](https://github.com/FlorianBruniaux/claude-code-ultimate-guide/blob/main/guide/core/loop-graph-engineering.md)
- [Project specification](SPEC.md)
- [Validation rules and interpretation](VALIDATION_RULES.md)
