# Lectern

> Long before slide decks, a **lectern** was the slanted desk a *lector* leaned on to read aloud to the hall — Latin *legere*, "to read." We kept the name because the work never changed: stand at the front, keep the term running, and make sure every roster, grade, and exam stays something you can open and read by hand years from now — no locked gradebooks, no vendor between you and your students' record.

**The Registrar** — a 100% open-source teaching-operations toolkit for university instructors.

Lectern handles the full administrative lifecycle of running courses: term scaffolding, gradebook consolidation, exam build and verification, ISA grading artifact publishing, GitHub Classroom binding, campus-LMS (Canvas) roster/grade import, and end-of-term archival. All state lives in plain, version-controllable files. All tools are scriptable CLI commands in the `reg-*` family.

---

## Part of a self-hosted LMS — Lectern · Scriptorium · Oracle

**Lectern · Scriptorium · Oracle** together form a **self-hosted, open-format learning-management
system (LMS)** for university CS courses — faculty-owned, no vendor lock-in, spanning the full course
lifecycle: **administration** (Lectern) · **content** (Scriptorium) · **grading** (Oracle). It covers
what a commercial LMS does, but in plain version-controllable formats you own end to end.

**Modular by design:** adopt one tool or all three. Each stands alone, owns one stage of the course
lifecycle, and interoperates through open plain-text formats (Markdown · CSV · YAML · LaTeX) and
stable CLI contracts — no shared database, no monolith, no lock-in. Each tool is also operable two
ways: driven by an AI agent (Claude Code skill) *or* run directly by a human via its CLI.

| Tool | Role | Repo |
|---|---|---|
| **[Lectern](https://github.com/agiacalone/lectern)** — the Registrar | Course **administration** — terms, sections, gradebook, exam build/verify, Classroom binding, archival. | `agiacalone/lectern` |
| **[Scriptorium](https://github.com/agiacalone/scriptorium)** — the workshop | Course **content** — lecture notes, Cornell handouts, quizzes, slides, question banks. | `agiacalone/scriptorium` |
| **[Oracle](https://github.com/agiacalone/oracle)** *(private)* — the secret box | **Grading** — a verify-by-proof oracle service + a sandboxed code-runner (gradebox). | `agiacalone/oracle` *(private — licensed)* |

*You are here: **Lectern**.*

> **Suite licensing.** Lectern and Scriptorium are open source ([MIT](LICENSE)). **Oracle** — the grading engine — is **licensed, not open**: a **source-available license** (PolyForm Strict 1.0.0), private repo, source provided on licensing. Accredited **educational institutions can license it for free**; commercial and other use is by arrangement. Either way, **contact the author for a license** — [@agiacalone](https://github.com/agiacalone).

See [docs/design/lms-suite-integration.md](docs/design/lms-suite-integration.md) for how Lectern, Scriptorium, and Oracle integrate.

---

## Why open formats

> **Lectern is built entirely on open, plain-text, version-controllable file formats.**

| Format | What it carries |
|---|---|
| **LaTeX** (`.tex`) | Exams — student copies, answer keys, per-student serialized PDFs |
| **Markdown / plain text** (`.md`) | Course content, class notes, semester notes, ISA guides, documentation |
| **CSV** (`.csv`) | Rosters, gradebooks, exam registers, GitHub-binding tables, grade exports |
| **YAML** (`.yaml`) | Term specs, exam build manifests, archive manifests, gradebook schemas |

There are no proprietary formats in this pipeline — no `.docx`, no `.xlsx`, no locked LMS exports that can only be read by one vendor. Every file is:

- **Diff-able** — a grade change or question edit is a readable, reviewable diff
- **Git-versionable** — the full history of every exam, gradebook, and archive bundle is in source control
- **Scriptable** — plain CSV and YAML mean any tool (Python, awk, shell) can read or transform the data
- **Durable** — a plain-text LaTeX exam authored today is reproducible decades from now, with no license or cloud account required

This is a deliberate design principle, not an accident. Proprietary LMS gradebooks, locked PDF workflows, and cloud-only tooling create single points of failure and make reproducibility (essential for grade appeals, accreditation evidence, and academic-integrity investigations) fragile. Lectern's answer is: every artifact that matters lives in a format you can open with a text editor.

---

## Feature tour

### Command table (`reg-*`)

| Wrapper | Module | What it does |
|---|---|---|
| `reg-term-create` | `term_create` | Scaffold a term from a YAML term-spec: semester note + per-section class notes + archive manifest skeletons + course-catalog wiring. Idempotent; `--init` writes a stub spec. |
| `reg-term-finalize` | `term_finalize` | Reconcile grade distributions, flip section statuses to finalized, roll up enrollment-weighted aggregates. Supports `--dry-run`. |
| `reg-term-archive` | `term_archive` | Build per-section archive bundles (roster → grades → GitHub → gradebook → exams → lectures → syllabus → `manifest.yaml`). `--check` validates an existing bundle for drift. |
| `reg-gradebook` | `gradebook` + `gradebook_ledger` | Vault-native **grades ledger** (the vault is the grade source of truth; grades flow vault → Canvas). `build` rolls per-component score files (a `components.yaml` registry) into `gradebook.csv` + a `GRADEBOOK.md` ledger (grouped overview + per-assignment subsidiary ledgers + a live per-student view) with source-document reconciliation; `export-canvas` emits a Canvas bulk-upload CSV; the legacy `import` (Canvas → vault) and `dfw` / `dist` / `check` remain. |
| `reg-gradescope-stats` | `gradescope_stats` | Per-outcome **item analysis** from Gradescope *Export Evaluations* — per-distractor stats joined to the grading-note `form·Qn·slot` keys; flags dead distractors, over-key distractors, and the miskey alarm. Emits `ITEM_ANALYSIS.md`, a self-contained newspaper/agate **broadsheet**, and a per-student×question `item_scores` matrix. |
| `reg-exam-build` | `exam_build` | Assemble exam PDFs — single-source `.tex` mode or pack-mode `.yaml` manifest (multi-form A/B/C, per-student individualized, Gradescope products). See below. |
| `reg-exam-verify` | `exam_verify` | Verify a student exam serial against the register. Confirms which form and which student a paper belongs to. |
| `reg-lms-grades-import` | `lms_grades` | Normalize a Canvas `grades.csv` export to Lectern's canonical format. |
| `reg-lms-roster-import` | `lms_roster` | Normalize a faculty-center enrollment roster (`.xls`/`.xlsx`) to Lectern's canonical format. |
| `reg-classroom-roster-seed` | `classroom_seed` | Pre-seed a GitHub Classroom roster from a normalized roster CSV, using the 9-digit student ID as the identifier. |
| `reg-github-bind` | `github_bind` | Bind student GitHub usernames to roster entries — from a Google Form CSV, a GitHub Classroom roster CSV, or org-scrape mode. |
| `reg-isa-publish` | `isa_publish` | Publish ISA grading artifacts (exam keys, rubrics, print stacks) to a shared Drive folder via rclone or service-account backend. Hash-based idempotency: unchanged files are skipped. |
| `reg-syllabus` | `syllabus` | Generate course syllabi from Markdown with a tamper-evident control-number serial. `stamp` injects a repo-tree SHA-256 into the frontmatter + footer and appends a register row (course/section/term/CRN from the repo name); `build` renders `syllabus.html` + a Canvas-RCE-safe `syllabus_canvas.html` (`--pdf` opt-in, print only). |
| `reg-triage` | `triage` | Git-history **authenticity triage** for GitHub Classroom submissions. `init` scaffolds an assignment manifest; `sweep` scores the class into FLAG/REVIEW/PASS (CSV + Markdown broadsheet; optionally discovers repos via org-`scrape` mode post-Classroom); `report` generates a two-tier (verified-record / advisory-heuristic) audit document with a sanitized release variant; `rhythm` flags cross-assignment commit-rhythm shifts (advisory). Roster joins from `github.csv`; 100% triage — no student penalized without human review. |
| `reg-lab-recon` | `recon` | Sweep a lab's student-repo population into a deterministic **recon bundle** — per-repo autograde points (parsed from CI logs, robust to `continue-on-error`-masked job conclusions), honor gate, commit-pattern triage, and structural writeup facts — emitting `cohort.csv` + `FACTS.md` + a two-part (verified-facts / advisory) cohort-intelligence `REPORT.md`. |
| `reg-lab-digest` | `lab_digest` | **Layer-2 writeup digest** — the advisory complement to the autograder. `emit` reads a recon bundle + a structured rubric YAML and writes a per-repo grading work-list + output JSON-Schema; the LLM grading runs in the **harness via a documented contract** (no API dependency in lectern); `merge` validates the graded results and writes advisory writeup scores + one-line rationale comments into the cohort sheet — with deterministic guardrails (partial-ward zeroing from the autograde truth, authoritative total recompute, confidence/abstain gating). Each result carries an internal `comment` plus a sanitized, student-facing `student_comment`. Never touches the gradebook. |
| `reg-lab-report` | `report_render` + `feedback_deliver` | **Layer-3 instructor report + feedback delivery.** `render` deterministically assembles the canonical instructor `REPORT.md` from the recon bundle + digest cohort + optional gradebook standing — distribution stats, Unicode agate charts (grade distribution / score histogram / ward-clear funnel), the grade table, a four-bucket grading-recommendations engine (confirm / edge-cases / low-confidence / upward-adjustment), and a roster-ordered Canvas entry sheet (supersedes the agent-driven recon-report workflow). `deliver` posts a sanitized, GPG-signed `FEEDBACK.md` (grade breakdown + `student_comment`) to each repo's `feedback` branch and closes the feedback PR — **dry-run by default**, signing mandatory, idempotent, emitting a verbatim `FEEDBACK_LOG.md`. Never touches the gradebook. |

### Exam build system

`reg-exam-build` is the exam assembly engine. It dispatches on its input:

- **Single-source mode** (`reg-exam-build <file>.tex`) — compile one exam into `<exam>.pdf` + `<exam>_key.pdf`. Both share a content-hash serial in the footer. No manifest required. All existing `.tex` workflows continue unchanged.
- **Pack mode** (`reg-exam-build <exam.build.yaml>`) — read a manifest and drive the full matrix of forms × individualization × Gradescope products. This is the mode used when you have multiple form variants (A/B/C), per-student individualized copies, or need Gradescope import products.

**The 2×2 build matrix:**

| Forms | Individualized | Output |
|---|---|---|
| 1 | false | `build/A.pdf` + `build/A_key.pdf` |
| 2+ | false | Per-form `<id>.pdf` + `<id>_key.pdf` |
| 1 | true | One `<exam-slug>_combined.pdf` print PDF (per-student copies under `build/.parts/`) + `build/register.csv` |
| 2+ | true | One combined print PDF across all forms (roster order) + one `register.csv` covering the full roster split. `print_layout: per-form` restores per-form `<id>_combined.pdf` stacks. |

**Per-student tamper-evident serials:** every individualized copy carries a unique 8-hex footer ID computed from `SHA-256(source_serial + ":" + canonical_name(student_name))[:8]`. The footer on every page reads `Serial XXXXXXXX · ID YYYYYYYY`, making every printed copy self-authenticating. `reg-exam-verify` re-derives the expected ID from the register and confirms it matches — answering "is this really the paper printed for student X?" without relying on the register as ground truth.

**Grade-appeal reproducibility:** a build is fully deterministic. Given the same manifest, `.tex` sources, roster, and `assign_seed`, re-running `reg-exam-build` regenerates byte-identical content. This means a disputed paper can always be reproduced from archived sources — even weeks after the exam. See [docs/design/exam-tex-format.md](docs/design/exam-tex-format.md) for the full appeals runbook.

**Gradescope products:** set `gradescope: region` or `gradescope: bubble` in the manifest to emit a `gradescope/` directory with per-form template PDFs, answer-key PDFs, and outline CSVs ready for Gradescope import. See [docs/gradescope-workflow.md](docs/gradescope-workflow.md).

### Term lifecycle

```
reg-term-create --term fa26 --init --vault-root <root>   # write stub spec
# fill in classes/fa26.spec.yaml
reg-term-create --term fa26 --vault-root <root>           # materialize notes + manifests
# ... run the term ...
reg-exam-build exams/midterm1/exam.build.yaml
reg-syllabus stamp <syllabus-repo> --vault-root <root>                         # inject control-number serial + register row
reg-syllabus build <syllabus-repo> --pdf                                       # syllabus.html + Canvas-safe variant
reg-triage sweep --manifest <assignment>.triage.yaml --out triage/            # score class → FLAG/REVIEW/PASS
reg-gradescope-stats --eval-dir … --grading-note GRADING_NOTE.md --out-dir …   # item analysis + item_scores
reg-gradebook build --course CECS_378 --term fa26 --section 01 \
  --registry archives/fa26-01/components.yaml --roster … --out archives/fa26-01/   # vault-native ledger
reg-isa-publish --term fa26 --section 01 ...
reg-term-finalize --term fa26 --vault-root <root> --dry-run
reg-term-archive --term fa26 --vault-root <root>
reg-term-archive --check --term fa26 --vault-root <root>
```

---

## Architecture

```
lectern/
  term_create.py        term scaffolding from YAML spec
  term_finalize.py      grade reconciliation + status rollup
  term_archive.py       archive bundle orchestration
  gradebook.py          Canvas grades + roster + schema → gradebook.csv/.md
  exam_build.py         single-source .tex + pack-mode .yaml dispatch
  exam_pack.py          multi-form / individualized / Gradescope orchestration
  exam_serial.py        source serial + per-student serial computation
  exam_verify.py        register-based serial verification
  lms_grades.py         Canvas grades CSV normalization
  lms_roster.py         enrollment roster normalization (.xls → .csv)
  classroom_seed.py     GitHub Classroom roster pre-seeding
  github_bind.py        student-id → GitHub username binding
  isa_publish.py        Drive publishing (rclone/service-account backend)
  manifest_schema.py    JSONSchema validator for archive bundle manifests
  student_id.py         student ID normalization (9-digit zero-padding)
  vault_notes.py        frontmatter helpers for Markdown note management

references/
  reference_exam.tex    canonical exam skeleton (copy, rename, author, build)

examples/
  cecs-378-demo/        worked example: one full CECS 378 semester
```

**Vault awareness.** Most commands accept `--vault-root <path>` to locate course notes, class notes, and archive bundles relative to a notes root. If you do not use a notes-based workflow, pass explicit `--vault-root .` or use the modules as a library with fully explicit paths. The vault path is never hard-coded.

**Dependencies.** Python 3.11+. `pyyaml`, `jsonschema`, `vaultkit` (the companion path/slug/frontmatter utilities package). LaTeX toolchain (`pdflatex`, `pdfunite` or `qpdf`) for exam builds. `rclone` or a service-account credential for ISA publish.

---

## Install & quickstart

```bash
git clone https://github.com/agiacalone/lectern
cd lectern
./install.sh
# Writes .venv/, installs editable, creates reg-* wrappers in ~/bin.
```

Or into any Python 3.11+ environment:

```bash
pip install -e .            # core
pip install -e '.[verify]'  # + pdfplumber, for reg-exam-verify (else falls back to pdftotext)
pip install -e '.[dev]'     # + test deps (pytest, pdfplumber, …)
```

**External tools** the exam pipeline shells out to: `pdflatex` (TeX Live), and
`pdfunite` **or** `qpdf` for combining PDFs, plus `pdftotext`/`pdfinfo`
(poppler-utils) — install poppler + a TeX distribution via your package manager.

Test the install:

```bash
reg-term-create --help
reg-exam-build --help
```

### Minimal exam build (single form)

```bash
# Copy the reference skeleton and author your exam:
cp references/reference_exam.tex exams/cecs378-midterm1-fa26.tex
# ... edit the .tex ...

# Build student PDF + answer key:
reg-exam-build exams/cecs378-midterm1-fa26.tex
# → exams/cecs378-midterm1-fa26.pdf
# → exams/cecs378-midterm1-fa26_key.pdf
```

### Per-student individualized build

```bash
# Prepare roster.csv with at minimum a 'name' column:
# name,student_id
# Doe, Jane,012345678
# Smith, John,087654321

reg-exam-build --roster exams/roster.csv --combined exams/cecs378-midterm1-fa26.tex
# → one PDF per student with unique footer serial
# → cecs378-midterm1-fa26_combined.pdf (print stack)
# → cecs378-midterm1-fa26_serials.csv (register)
```

### Pack mode (multi-form + Gradescope)

```yaml
# exam.build.yaml
course: CECS 378
term: fa26
exam: Midterm 1
forms:
  - { id: A, source: cecs378-midterm1-fa26-A.tex }
  - { id: B, source: cecs378-midterm1-fa26-B.tex }
individualized: true
roster: roster.csv
assign: alternating
gradescope: region
```

```bash
reg-exam-build exam.build.yaml
# → build/  (per-student PDFs, combined stacks, register.csv)
# → gradescope/  (template PDFs, answer keys, outline CSVs, roster CSV)
```

---

## Worked example

`examples/cecs-378-demo/` walks a complete CECS 378 semester end-to-end: importing a roster and Canvas gradebook, building an A/B exam with individualized copies, publishing ISA artifacts, and producing a finalized archive bundle. See the README inside that directory.

---

## How this maps to standardized course-repository infrastructure

Lectern addresses several standardized-infrastructure concerns directly:

**Naming conventions.** The install convention for course repos follows `[dept]-[num]-[type]-[name]` (e.g., `cecs-378-lab-spellbreaker`). `reg-github-bind` and `reg-classroom-roster-seed` use the same structured naming to bind student repos to roster entries.

**GitHub Classroom binding.** `reg-classroom-roster-seed` pre-populates a Classroom roster from the enrollment list so students self-authenticate via GitHub OAuth at assignment time — no manual binding form needed. `reg-github-bind` reconciles the resulting username list back to student IDs for grade reporting.

**Reproducible, auditable exams.** Every exam artifact is produced from version-controlled source (`.tex` + `exam.build.yaml` + `roster.csv`). A Git commit of the exam directory is a complete, reproducible record — re-running the build regenerates the same PDFs with matching footer serials. This satisfies both internal audit requirements and external accreditation evidence standards.

**Autograding integration.** Code and lab autograding is performed by **[Oracle](https://github.com/agiacalone/oracle)** — a verify-by-proof oracle service paired with a sandboxed `gradebox` runner. Lectern *coordinates and records* the results: the archive bundle's `manifest.yaml` tracks template repo commits and lab names alongside exam serials and grade distributions, and ISA-published artifacts (keys, rubrics) live in a structured Drive folder matching the term/section/course hierarchy so graders can always find the authoritative rubric for a given assignment. (MC-bubble and Gradescope exam autograding are Lectern's own — see [`docs/gradescope-workflow.md`](docs/gradescope-workflow.md).)

**Gradebook as data.** `reg-gradebook` produces `gradebook.csv` — a plain CSV that is the canonical, diff-able record of every student's grades. It is never the sole copy: Canvas is the student-facing authority, the archive bundle is the institutional record, and the CSV is the analytical layer that enables DFW rollups, section-to-section comparisons, and grade-appeal lookups from the command line.

---

## Documentation

| Document | Contents |
|---|---|
| [docs/README.md](docs/README.md) | Documentation index |
| [docs/design/exam-system.md](docs/design/exam-system.md) | Multi-form exam system design: A/B variants, individualized builds, Gradescope products, defensibility |
| [docs/design/exam-tex-format.md](docs/design/exam-tex-format.md) | House `.tex` format: header block, answer key toggle, per-student serials, color conventions, appeals runbook |
| [docs/gradescope-workflow.md](docs/gradescope-workflow.md) | Using Lectern-built exams with Gradescope: region/bubble, A/B Version Sets, roster, identity verification |

---

## License

MIT. See [LICENSE](LICENSE).

Copyright (c) 2026 Anthony Giacalone.
