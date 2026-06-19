# AGENTS.md — AI Operation Guide for Lectern

Lectern is fully operable two ways: driven by an AI agent (Claude Code skill) **or** run directly by a human via its `reg-*` CLI commands. This file documents the AI-agent path and maps every skill action to its CLI equivalent.

## Entry points

Every skill action maps to a `reg-*` CLI command. An agent performing any Lectern operation MUST invoke the corresponding CLI command — the skill is a thin dispatch layer over the CLI, not a reimplementation.

| Skill action | CLI command | Module |
|---|---|---|
| Scaffold a new term | `reg-term-create` | `term_create` |
| Finalize a term (reconcile grades, flip statuses) | `reg-term-finalize` | `term_finalize` |
| Build an archive bundle | `reg-term-archive` | `term_archive` |
| Import and consolidate grades | `reg-gradebook` | `gradebook` |
| Build exam PDFs (single / multi-form / individualized) | `reg-exam-build` | `exam_build` |
| Verify a student exam serial | `reg-exam-verify` | `exam_verify` |
| Generate exam reading-list study guides | `reg-exam-readinglist` | (drives `lecture-materials`) |
| Run item analysis from Gradescope evaluations | `reg-gradescope-stats` | `gradescope_stats` |
| Normalize Canvas grades export | `reg-lms-grades-import` | `lms_grades` |
| Normalize CSULB enrollment roster | `reg-lms-roster-import` | `lms_roster` |
| Pre-seed GitHub Classroom roster | `reg-classroom-roster-seed` | `classroom_seed` |
| Bind student GitHub IDs to roster entries | `reg-github-bind` | `github_bind` |
| Publish ISA grading artifacts to Drive | `reg-isa-publish` | `isa_publish` |
| Generate and stamp course syllabus | `reg-syllabus` | `syllabus` |
| Triage GitHub Classroom submission authenticity | `reg-triage` | `triage` |

## Grading split

- **Code/lab autograding** is performed by **[Oracle](https://github.com/agiacalone/oracle)** — the verify-by-proof oracle service + `gradebox` sandboxed runner. Lectern does not own this step.
- **Lectern** *coordinates and records*: `manifest.yaml` tracks template-repo commits, lab names, exam serials, and grade distributions; ISA-published artifacts (keys, rubrics) are published via `reg-isa-publish`.
- **Exam autograding** (MC-bubble / Gradescope) is Lectern's own — see `docs/gradescope-workflow.md`.

## Agent conventions

- All commands accept `--vault-root <path>` to locate vault notes. Pass it explicitly; never rely on a hard-coded default.
- Prefer `--dry-run` on `reg-term-finalize` before committing; the agent should surface the preview output for review.
- `reg-term-archive --check` exits 0 on a clean bundle and nonzero on drift — use the exit code as a quality gate.
- All state lives in plain files (Markdown · CSV · YAML · LaTeX) — the agent can read and diff these directly.

## Skill file

`SKILL.md` — the Claude Code skill definition (frontmatter `name: lectern`). Import via the `lectern` skill name.
