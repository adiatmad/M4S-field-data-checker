# UI/UX Guidelines for the M4S Field Data QA Checker

## Purpose

Make the two Streamlit workflows understandable to field coordinators and data managers who need to decide what to review next. The UI should make validation scope and uncertainty explicit, not make the application look more sophisticated than its checks justify.

These are project-specific rules, informed by GitHub examples including [CabotageLens's Streamlit UI/UX skill](https://github.com/pennylanesccp/cabotage-lens/blob/main/skills/streamlit_ui_ux/SKILL.md), [the AQI Predictor UX best-practices document](https://github.com/AyyanStorm/aqi-predictor/blob/main/UX_BEST_PRACTICES.md), and [the Digital Object Registry accessibility guidance](https://github.com/adammoore/digital-object-registry/blob/main/docs/accessibility.md). Their domain-specific content is not copied: this project has different data, risks, and user tasks. Use the principles below rather than treating any one external file as a drop-in design system.

## Design direction

**Calm, task-first, evidence-led data QA.** Prioritize readable data, clear findings, and safe decisions over decoration. Use Streamlit's native components and the existing dependency set. Do not add custom CSS, JavaScript, component packages, charts, or a visual theme unless a concrete user task requires them and they can be tested.

## Interaction principles

1. **Explain the next action.** The upload state tells users which file type is expected and what happens after upload. Controls use specific labels such as “Show only rows with issues” rather than generic “Filter” or “Go”.
2. **Make validation scope visible.** Explain enabled checks and relevant limits near the workflow. Generic CSV screening is not XLSForm validation; M4S rules are specific to the current form and site assumptions.
3. **Report evidence, not certification.** “No findings from the enabled checks” is acceptable. “All data is clean/valid” is not. A count of rows without flags must not imply that those rows are correct.
4. **Make findings actionable.** A finding should identify the affected row/field where available, explain what was observed, and suggest a safe review step. Do not silently correct uncertain values.
5. **Keep source data and corrections distinguishable.** Label original input, QA-annotated data, corrected output, and correction log explicitly. Never present a corrected export as the unchanged source.
6. **Errors must support recovery.** Explain which stage failed, whether results are incomplete, and what the user can do next. Do not display raw tracebacks or sensitive row values in generic unexpected-error messages.
7. **Use restrained visual hierarchy.** Use headings, whitespace, native alerts, and metric labels consistently. Avoid decorative emoji in headings, metric labels, and tabs; do not rely on color or icons alone to communicate severity.
8. **Use plain, literal copy.** Prefer short sentences, consistent terms, and standard punctuation. Avoid claims that exceed the underlying rule. Keep units and spatial assumptions explicit (for example, distance to a site centroid is not polygon containment).
9. **Respect privacy.** State where uploaded data is processed and avoid sending survey content to external services. Do not add telemetry or AI processing without an explicit, reviewed requirement.
10. **Prefer responsive native controls.** Do not hardcode layout dimensions. Check that wide tables, download actions, and controls remain usable at narrow viewport widths.

## Layout hierarchy

For each workflow, use this order unless usability evidence supports another arrangement:

1. Workflow title and a concise purpose/privacy note.
2. Upload control and the minimum settings needed to run checks.
3. Run status and summary counts with explanatory labels.
4. Findings and row-level data, with filters close to the table they affect.
5. Clearly named exports.
6. Secondary reference material and methodology details in expanders.

Do not add onboarding screens, dashboards, cards, charts, or multi-step wizards just to make the interface appear modern. Add them only when they remove a demonstrated source of confusion.

## Accessibility and content

- Keep visible labels on controls and use Streamlit's native widgets before custom HTML.
- Ensure warning/error/success messages include text; color or symbols alone are insufficient.
- Use consistent names for findings, flags, records, rows, warnings, errors, and corrections.
- Include units and explain spatial assumptions where relevant.
- Avoid decorative glyphs in core labels. Page icons may be omitted when they do not add information.
- Keep messages specific, neutral, and respectful. Do not blame the user for malformed or unsupported input.

## Verification checklist for every UI change

- [ ] The change maps to a user task or a recorded audit finding.
- [ ] No survey-domain rule, threshold, alias, or automatic-correction behavior changed unintentionally.
- [ ] Success states describe only the checks actually run.
- [ ] Error and empty states tell users what happened and what to do next.
- [ ] Labels are clear without decorative emoji or color alone.
- [ ] Spatial claims distinguish centroid-distance checks from polygon containment.
- [ ] Existing pinned Streamlit APIs and dependencies remain compatible.
- [ ] Automated tests and compilation pass.
- [ ] At least one manual click-through is recorded for each affected workflow before release; static tests alone do not prove the UI works.
- [ ] Any limitation in verification is stated in the pull request.

## Scope of the initial implementation

The first pass addresses audit findings about missing UI design direction, overconfident clean-data copy, decorative labels, and em dashes in visible/generated messages. It does not redesign the full page structure, change validation logic, alter ecological thresholds, or claim a manual UI audit has been completed.
