# Changelog

All notable changes to lectern are documented here.

---

## [Unreleased]

### Fixed
- **Declared the `pdfplumber` dependency** that was previously undeclared: added to the `dev` extra (the test suite imports it directly) and to a new optional `verify` extra. `reg-exam-verify` prefers pdfplumber for footer-serial extraction but falls back to the `pdftotext` CLI, so it stays optional at runtime — not a hard dependency.

### Added
- **`reg-lab-digest`** — Layer-2 **writeup digest** (the advisory complement to the autograder). `emit` reads a recon bundle + a structured rubric YAML and writes a per-repo grading work-list + output JSON-Schema; the LLM grading runs in the **harness via a documented contract** (no API dependency in lectern); `merge` validates the graded results and writes advisory writeup scores + one-line rationale comments into the cohort sheet. Deterministic guardrails enforced in code, never trusted to the model: partial-ward zeroing from the autograde truth, authoritative total recompute (`min(cap, Σ)`), confidence/abstain gating. **Never writes the gradebook** — promotion stays a separate human-confirmed step. Ships the Spellbreaker rubric (`templates/spellbreaker.rubric.yaml`) + the grader-prompt contract; first validated end-to-end on a real CECS 378 Lab 1 cohort. New modules `lectern.digest_{rubric,schema,emit,merge}` + `lectern.lab_digest`.
- **`reg-lab-recon`** — sweep a lab's student-repo population into a deterministic **recon bundle** (Part A facts): per-repo autograde points (parsed from CI logs — robust to `continue-on-error`-masked job conclusions), honor gate, commit-pattern triage, and structural writeup facts → `cohort.csv` + `FACTS.md` + a two-tier (verified-record / advisory) cohort-intelligence `REPORT.md`. Advisory; no student graded without human review. New modules `lectern.recon_*`.
- **`reg-triage`** — git-history authenticity triage for GitHub Classroom submissions (`init`/`sweep`/`report`/`rhythm`); two-tier audit doc, advisory-only, 100% human review. Ships with synthetic demo fixtures.
- **`reg-syllabus`** — syllabus generation with a tamper-evident control-number serial (`stamp`/`build`).
- **`reg-gradescope-stats`** — per-outcome item analysis from Gradescope Export Evaluations.
- **Gradebook ledger** — `reg-gradebook build` now emits a navigable grades ledger (bookkeeping model: single-entry with source-document reconciliation):
  - **`GRADEBOOK.md`** — a grouped general ledger: components by weight category (Assignments / Midterms / Final) with per-group subtotals → standing; ungraded cells render `·` (never `0`), in-progress `*`; each component header wikilinks its assignment page. Plus a live per-student statement view (DataviewJS).
  - **`assignments/<short>.md`** — a subsidiary ledger per component. Exam pages carry the score roster (n/mean/median/σ + distribution), links + an `![[ITEM_ANALYSIS]]` embed, and a collapsible per-student×question grid **per form** (A/B).
  - **Reconciliation** — every assignment page reconciles grid totals to recorded scores: true value mismatches surface under an *Out of balance* danger callout; roster differences (e.g. no-shows with a recorded score but no submission) surface as informational *Reconciling items* — surfaced, never silently absorbed.
  - `components.yaml` gains optional `link:` / `analysis:` (assignment + item-analysis wikilinks), `breakdown:` (per-student×question matrix; accepts a glob/list for multi-form exams), and `kind:` (exam/lab/reading).
  - `reg-gradescope-stats` emits a per-student×question `item_scores_<form>.csv` matrix (the grid + reconciliation source).
  - New module `lectern.gradebook_ledger`.

### Changed
- **`reg-exam-build` print layout — one combined PDF per exam, not one file per student.** New manifest key `print_layout: single | per-form` (default **`single`**). In `single`, the per-student serialized copies are merged into a single `<exam-slug>_combined.pdf` for the whole roster (all forms, canonical-name order) — the printable deliverable is exactly one file; the per-student copies become build intermediates under `build/.parts/` (still referenced by `register.csv`'s `output_pdf`, so `reg-exam-verify` and one-off reprints work). `print_layout: per-form` restores the prior behavior (per-form `<id>_combined.pdf` stacks, loose per-student PDFs in `build/`). `reg-exam-verify --dir build/` works unchanged in both layouts (the register's `output_pdf` carries the `.parts/` prefix in `single`).
- `reg-gradebook build` no longer emits the legacy standalone `gradebook.md` cockpit — the new `GRADEBOOK.md` ledger supersedes it. (`render_view` is retained for the legacy Canvas→vault `import` path; the class-note cockpit reads `gradebook.csv` directly and is unaffected.)
- `reg-gradescope-stats`: per-outcome **item analysis** from Gradescope *Export Evaluations*. Joins each rubric-item column back to the exam's `form·Qn·slot` keys in the grading note, computing per-question difficulty (p-value) and per-distractor selection counts.
  - Flags **non-functioning distractors** (chosen by 0), **distractors more popular than the key**, and a **miskey alarm** (a credited item applied yet the question mean is 0 → rubric point value misset in Gradescope).
  - Robust join: exact text → MC `(letter)` prefix (survives prose typos) → no-answer/blank → order outcome; excludes the Gradescope `Rubric Numbers` legend row and impossible-score rows.
  - Emits three artifacts: `ITEM_ANALYSIS.md` (Obsidian-tagged report), `item_analysis.html` (a self-contained newspaper/agate **Item Analysis broadsheet**), and `item_analysis.json` (downstream analytics). Can splice a *Post-exam statistics* link section into the grading note (`--link-grading-note`).
  - New module `lectern.gradescope_stats` + `references/item_analysis.template.html`.
- `reg-gradebook build` + `reg-gradebook export-canvas`: **vault-native gradebook** — the vault is the grade source of truth; grades flow vault → Canvas (inverting the Canvas → vault `import` path).
  - `build` rolls per-component score files into `gradebook.csv` (+ `gradebook.md` cockpit) via a per-section `components.yaml` registry that binds each scores file (`sid`, `score`, `status`) to a `gradebook-schema` column.
  - **In-progress current standing**: `compute_weighted(graded_only=…)` renormalizes group weights over graded work, so a partly-graded term is not scored all-F and converges to the full-schema final once every column is graded.
  - Roster handling: off-roster students with a real grade (e.g. a new enrollee) are kept and flagged `stale-roster`; a non-roster student who only no-showed is treated as dropped and excluded from the gradebook.
  - `export-canvas` emits a Canvas bulk-upload CSV (`SIS User ID` + one column per graded component) for pushing grades back to Canvas; ungraded components get no column (never upload-zeroes work that isn't done).
  - New module `lectern.gradebook_build`; legacy `reg-gradebook import` (Canvas → vault) retained for reconciliation.
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
