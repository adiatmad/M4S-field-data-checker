# Engineering skills and agent references

This repository keeps its agent instructions in tracked files. Read `AGENTS.md` first; it governs when guidance overlaps. Nothing here is loaded automatically — load the file that matches the task.

## What is vendored here

| Path | Use it for |
| --- | --- |
| `AGENTS.md` | Repository rules, project/data constraints, quality gates. Always applies. |
| `antislop.md` | Anti-Slop core: the filter for generated UI, copy, and code. Vendored verbatim under `licenses/anti-slop-MIT.txt`. |
| `.specify/memory/constitution.md` | The project's engineering constitution: data, provenance, and delivery standards. |
| `.agents/skills/` | The skills listed below, one folder per skill. |

## Installed skills

Load a skill by reading its `SKILL.md` when its task matches. Never bulk-load all of them.

| Skill | Use it when |
| --- | --- |
| `ponytail` | Any coding task: smallest complete change, one-read reply. |
| `tdd` | Building a feature or fixing a bug test-first. |
| `implement` | Executing a spec or a set of tickets. |
| `to-spec` | Turning an existing conversation into a spec. |
| `to-tickets` | Splitting a plan or spec into tracer-bullet tickets. |
| `code-review` | Reviewing a diff, branch, or PR against standards and the originating spec. |
| `grilling` | Stress-testing a plan or decision with hard questions. |
| `grill-with-docs` | The same interview, recording ADRs and glossary entries as you go. |
| `domain-modeling` | Sharpening terminology, a `GLOSSARY.md`, or an ADR. |
| `codebase-design` | Designing a module interface, finding seams, deepening modules. |
| `retro` | Retrospective on a finished coding session. |

## Not vendored: consult upstream, selectively

- Anti-Slop modular skills (`antislop-ui`, `antislop-copywriting`, `antislop-human`, `antislop-layoutmobile`, `antislop-code`): https://github.com/miqdadbadjuber/anti-slop
- GitHub Spec Kit: https://github.com/github/spec-kit
- Upstream Matt Pocock skills, if you need one that is not in the table above: https://github.com/mattpocock/skills

Do not bulk-copy upstream skills or generated asset datasets into this repository. Identify the concrete task, read the current upstream instructions, and explain why they apply. Do not run installer commands such as `specify init --force` or an agent CLI's skill installer merely to make a repository document discoverable; they rewrite project files.

## Working agreement

1. Inspect the repository state, the relevant code, exports, specs, and tests before editing.
2. State the user outcome, scope, and acceptance criteria for non-trivial work.
3. Make the smallest coherent change, reusing existing structure and conventions.
4. Add a regression test for data bugs, reproduced first with a minimal fixture.
5. Inspect the diff, run the relevant checks, and report exact commands and results. Distinguish tests you ran from tests you could not run.
6. Never overwrite, migrate, or delete existing project files without inspecting the impact.
