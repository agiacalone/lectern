# Changelog

All notable changes to lectern are documented here.

---

## [Unreleased]

### Added
- `exam_pack` module: pack-mode exam build via `exam.build.yaml` manifest
  - Multi-form (A/B/C) support with hand-authored form variants
  - Per-student individualized builds (pre-filled NAME/ID, unique footer serials)
  - Form-assignment policies: `alternating`, `seeded-random`, `every-form`
  - Gradescope product emission: `region` (template/key/outline) and `bubble` (bubble key/outline)
  - Gradescope **grading note** (`GRADING_NOTE.md`): one self-contained, ISA-ready Markdown grading guide per exam — exam identity, Gradescope setup steps, and a per-form answer-key + rubric table. Emitted whenever a `gradescope:` target is set. Because Gradescope imports no key or rubric, this is the human crib a grader (especially a TA who did not author the exam) works from.
  - Per-question `% name:` / `% rubric:` LaTeX annotations: authored in the exam `.tex`, they supply the grading note's question names and rubric criteria. `% name:` is required on every question; `% rubric:` is required on `fib`/`code` items and optional (defaults to all-or-nothing) on `mc`/`tf`.
  - Consolidated `register.csv` with `form` column spanning all forms
- `reg-exam-build` now dispatches on input type: `.tex` for legacy single-source mode, `.yaml` for pack mode
- Per-student identity block: `\fieldline` + `\identityinstruction` macros pre-fill student name and ID on individualized copies; student only adds the date
- `references/reference_exam.tex`: canonical A.2 exam skeleton with all per-student macros, single-source answer key toggle, color conventions, and Gradescope-additive rubric structure

### Fixed
- `exam_pack`: fill-in-the-blank answers in `<form>_outline.csv` are no longer truncated to the first blank — multi-blank FIB answers (e.g. `confusion; diffusion`) are preserved in full.

### Documentation
- `docs/design/exam-system.md`: multi-form exam system design, build matrix, defensibility
- `docs/design/exam-tex-format.md`: house `.tex` format standard, serial computation, appeals runbook
- `docs/gradescope-workflow.md`: Gradescope region/bubble workflow, A/B Version Sets, roster

---

## [0.1.0] — 2026-05-23

Initial public release.

### Included
- `reg-term-create`, `reg-term-finalize`, `reg-term-archive`: term lifecycle
- `reg-gradebook`: Canvas grades + roster + YAML schema → `gradebook.csv` + DataviewJS view
- `reg-exam-build` (single-source mode): `.tex` → student PDF + key PDF with shared source serial
- `reg-exam-verify`: per-student serial verification against register
- `reg-lms-grades-import`, `reg-lms-roster-import`: LMS export normalization
- `reg-classroom-roster-seed`: GitHub Classroom roster pre-seeding
- `reg-github-bind`: student-id → GitHub username binding
- `reg-isa-publish`: Drive publishing with hash-based idempotency
- `manifest_schema`: JSONSchema validator for archive bundle manifests
- `student_id`: 9-digit zero-padding normalization
