# Agent instructions

Inspect this file, the README/user guide, current implementation, tests, and any project-specific configuration before editing.

## Product and data constraints

- This is a human-reviewed survey-data QA tool. A finding is a prompt to investigate, not proof that a record is wrong.
- Keep generic CSV checks separate from M4S-specific seagrass rules. Never generalize M4S expected columns, species assumptions, site locations, or thresholds to another survey.
- Preserve original source rows and columns unless a transformation is explicitly specified. Keep correction logs and export behavior auditable.
- Do not infer the meaning of unknown survey questions or empty source headers. Preserve source identifiers and explain uncertainty.
- Protect uploaded survey data and potentially identifying information. Do not add telemetry, external uploads, or unnecessary data retention.
- Maintain the documented distinction between errors and warnings, enumerator exports, consolidated workbooks, and raw-data ZIP outputs.

## Required engineering workflow

1. Inspect the repository state, current data flow, configuration, and relevant tests before editing.
2. For non-trivial behavior changes, define the user outcome, scope, non-goals, constraints, risks, and testable acceptance criteria. Use the repository's existing spec format if present.
3. Work in vertical red-green-refactor slices. Test through public workflow seams and use representative fixtures; avoid tests coupled to private implementation.
4. For data bugs, reproduce with a minimal representative fixture, identify the exact row/column and transformation, and add a regression test before changing behavior.
5. Prefer the smallest coherent change. Avoid speculative abstractions, silent data coercion, guessed field semantics, and unnecessary dependencies.
6. Review separately against the accepted requirements and data-safety/quality standards. Check that exports preserve the promised source data and do not silently drop records or columns.
7. Run relevant tests and inspect the final diff. Report exact commands and results, and distinguish fixture tests from real Kobo/export acceptance.

## Quality gates

- Apply the full Anti-Slop core in `antislop.md`; reject generic copy, invented metrics, decorative UI, and unnecessary code.
- This is a Streamlit UI. Use UI/UX Pro Max when installed for substantive interface work, while preserving the current task-focused workflow. Verify responsive behavior, keyboard/focus, empty/loading/error states, and real interactions.
- Model multi-step work as a dependency graph; parallelise only independent tasks and keep data transformations and verification checkpoints explicit.
- Never weaken tests, expose sensitive survey data in logs, or silently change export contracts.
