---
name: lectern
description: Course/teaching operations for a CSULB lecturer — the Registrar. Term + section lifecycle (create/finalize/archive), gradebook consolidation, exam build/verify with per-student serials, ISA Drive publishing, GitHub Classroom binding, LMS roster/grade import. Trigger on grading close-out, starting a new term, building/verifying exams, importing rosters or grades, publishing to ISAs, or any reg-* command.
---

# Lectern — Course Operations Skill

Lectern is the operational/records counterpart to `lecture-materials-assistant`
(which generates lecture content). It owns "the Registrar": the lifecycle and
records of running courses. All tools are vault-aware via an explicit
`--vault-root` argument — no hard-coded vault paths and no external vault package
(the one `slugify` helper is vendored into `lectern/_text.py`).

## Wrappers (reg-*)

| Wrapper | Module | Purpose |
|---|---|---|
| `reg-term-create` | term_create | Scaffold a term from a YAML term-spec (semester note + class notes + manifest skeletons + MOC wiring), idempotent; `--init` writes a stub spec |
| `reg-term-finalize` | term_finalize | Reconcile grade distributions + flip statuses to finalized + roll up enrollment-weighted aggregates; `--dry-run`, `--allow-missing` |
| `reg-term-archive` | term_archive | Per-section archive bundle orchestrator + `--check` drift validator |
| `reg-gradebook` | gradebook | Consolidate normalized grades+roster into gradebook.csv/.md |
| `reg-exam-build` | exam_build | Assemble exam PDF(s) — single-source `.tex` or pack-mode `.yaml` (multi-form, individualized, Gradescope products) |
| `reg-exam-verify` | exam_verify | Verify a student exam serial against the registry |
| `reg-exam-readinglist` | (standalone → lecture-materials) | Generate consolidated per-exam reading-list study guides from an exam→topics manifest |
| `reg-lms-grades-import` | lms_grades | Normalize a Canvas grades.csv export |
| `reg-lms-roster-import` | lms_roster | Normalize a CSULB faculty-center roster export |
| `reg-classroom-roster-seed` | classroom_seed | Seed a GitHub Classroom roster from a normalized roster |
| `reg-github-bind` | github_bind | Bind student GitHub IDs to roster entries |
| `reg-isa-publish` | isa_publish | Publish ISA grading artifacts to Drive (rclone/gdrive backend) |
| `reg-gradescope-stats` | gradescope_stats | Per-outcome **item analysis** from Gradescope *Export Evaluations* — per-distractor stats joined to grading-note `form·Qn·slot` keys (dead/over-key distractors, miskey alarm); emits `ITEM_ANALYSIS.md` newspaper broadsheet + `item_scores` matrix |
| `reg-triage` | triage | Git-history **authenticity triage** for GitHub Classroom submissions: `init` scaffolds a manifest, `sweep` scores a class into FLAG/REVIEW/PASS (CSV + Markdown broadsheet; org-`scrape` repo discovery post-Classroom), `report` emits a two-tier audit doc with a sanitized `--release` variant, `rhythm` flags cross-assignment commit-rhythm shifts. 100% triage — no student penalized without human review |
| `reg-syllabus` | syllabus | Generate course syllabi from Markdown with a tamper-evident control-number serial: `stamp` injects a repo-tree SHA-256 + register row, `build` renders `syllabus.html` + a Canvas-RCE-safe `syllabus_canvas.html` (`--pdf` opt-in, print only) |
| `reg-lab-recon` | recon | Sweep a lab's student-repo population into a deterministic **recon bundle** (Part A facts): per-repo autograde points (parsed from CI logs), honor gate, commit triage, structural writeup facts → `cohort.csv` + `FACTS.md` + a two-tier cohort-intelligence `REPORT.md`. Advisory; no student graded without human review |
| `reg-lab-digest` | lab_digest | **Layer-2 writeup digest** over a recon bundle: `emit` a grading work-list (writeups + rubric YAML + output schema), then `merge` model-graded results into the cohort sheet as advisory writeup scores + rationale comments. LLM grading runs in the **harness via a contract** (no API dep in lectern); deterministic guardrails — partial-ward zeroing from autograde truth, total recompute, confidence gating. Results carry both an internal `comment` and a sanitized `student_comment`. **Never writes the gradebook** |
| `reg-lab-report` | lab_report | **Layer-3 instructor report + feedback delivery.** `render` → the canonical `REPORT.md` (distribution + agate charts, grade table, four-bucket grading recommendations, Canvas entry sheet) deterministically from the recon bundle + digest cohort. `deliver` → a sanitized, GPG-signed `FEEDBACK.md` to each repo's `feedback` branch, closes the feedback PR, **then merges `feedback` into `main`** (signed; direct-add fallback for unrelated-history repos) so it shows on the student's default branch; **`--dry-run` by default**, signing mandatory, idempotent (feedback + main independently; `--no-merge-main` opts out), emits a verbatim `FEEDBACK_LOG.md`. Feedback source is either the digest cohort (`--cohort`) or — **note-authoritative** — the grading-round note itself (`--from-note <REPORT.md>`), parsing per-student blocks so hand-authored feedback is delivered verbatim, never re-derived (N generic components). Trigger after grading a lab to produce the instructor report and/or post feedback to students |

Library modules (no wrapper): `exam_serial`, `manifest_schema`, `student_id`,
`drive_auth`, `isa_publish_schema`. Triage engine: `triage_signals`, `triage_engine`, `triage_manifest`, `triage_rhythm`, `triage_scrape`, `triage_version`. Plus `syllabus_serial`, `qbank`.

## Exam reading-list study guides (`reg-exam-readinglist`)

A quiz/exam is a short exam; an **exam reading-list** is the consolidated, per-exam
study guide — the multi-topic companion to the single-topic lecture reading lists,
mapping each covered handout's Cornell cues to their textbook sections (the
`final_third_reading_list` pattern).

`reg-exam-readinglist` is a standalone wrapper (run via the lectern
venv) that drives the **lecture-materials** exam-reading-list generator
(`exam-reading-list-cli.js` → `generators/exam-reading-list.js`), then renders a
PDF (pandoc + lualatex). Cue→source rows are built from each topic's
`_lecture_main.md` (`[cue::]` + `[citation::]` on `#blank`s, `#vocab` citations,
the `## Self-Quiz`, and the `## References`) — so the guide stays a *view* of the
lecture mains; regenerate after the mains change.

**Option A — exam→topics manifest.** Each course's exams declare their coverage in
`classes/<course>/exams/exam_reading_lists.yaml`:

```yaml
course: "CECS 326"
term: sp26
lectures_dir: ../lectures
# Optional — for non-OS courses, override the hardcoded Tanenbaum defaults:
textbook: "Stallings & Brown, *Computer Security: Principles and Practice*, 4th ed."
citation_key: "Stallings"   # surname matched in [citation::] fields to pull chapters
exams:
  - { slug: midterm_1, name: "Midterm 1", topics: [intro_to_operating_systems, processes_and_threads] }
  - { slug: final_third, name: "Final", topics: [input_and_output, file_systems_abstraction, virtualization] }
  # Optional per-exam curation callout (regeneration-safe — lives in the manifest, not the .md):
  # - { slug: final_third, name: "Final", note_title: "Cues newer than the textbook", note: "…", topics: [...] }
```

`textbook` / `citation_key` default to Tanenbaum & Bos / `tanenbaum` (CECS 326). Set
them per-course so the [!source] block names the right book and chapter numbers come
from that author's `[citation::]` fields. Canonical chapters are read from each main's
`## References` textbook line (e.g. `…, Ch 2 (…), Ch 20 (…), Ch 21`), falling back to
inline-citation scanning. A per-exam `note` (+ optional `note_title`) renders a
`[!warning]` callout under the source block — use it for "content newer than the
textbook" style guidance without hand-editing the generated file.

Run:

```sh
reg-exam-readinglist --manifest classes/<course>/exams/exam_reading_lists.yaml          # all exams
reg-exam-readinglist --manifest <path> --exam midterm_1                                  # one exam
reg-exam-readinglist --manifest <path> --no-pdf                                          # md only
```

Output is organized like a lecture topic — its own dir with a `products/` subdir:
`classes/<course>/exams/<slug>/products/<slug>_reading_list.{md,pdf}`. Editing exam
coverage = edit the manifest's `topics` and re-run. (First built for CECS 326,
2026-05-31; extended for CECS 378 — `textbook`/`citation_key`/`note` — same day. The
per-topic lecture reading lists are still produced by the lecture-materials
`reading-list` artifact.)

## Teaching workflow

See the project README for term-end/mid-term rituals.
Vault is the proprietary record; Canvas is student-facing + ISA grade entry;
Drive is ISA distribution only; GitHub Classroom binds students to repos.

### Term lifecycle (start → close)

1. `reg-term-create --term <t> --init --vault-root <V>` — write a stub
   `classes/<t>.spec.yaml`.
2. Fill in the term-spec: term boundaries, grade-submission deadline, and one
   `sections:` entry per section (course, section, class-number, room, meets,
   enrolled, final-exam-date).
3. `reg-term-create --term <t> --vault-root <V>` — materialize the semester note,
   per-section class notes + manifest skeletons, and MOC wiring (idempotent; safe
   to re-run as enrollment firms up — existing files are skipped).
4. …run the term (gradebook imports, exams, ISA publishing)…
5. `reg-term-finalize --term <t> --vault-root <V> --dry-run` — preview
   reconciliation + status flips, then drop `--dry-run` to commit.

## Exam build modes (single / A·B / individualized)

`reg-exam-build` dispatches on its first argument:

- **Legacy single-source mode** — `reg-exam-build <file>.tex`: compiles one `.tex`
  into `<exam>.pdf` + `<exam>_key.pdf` with a shared source serial in the footer.
  No manifest required. Unchanged from pre-pack behavior; all existing `.tex` workflows
  continue to work exactly as before.

- **Pack mode** — `reg-exam-build <exam.build.yaml>`: reads a manifest and drives the
  full matrix of forms × individualization × Gradescope products. Outputs land under
  `build/` (and `gradescope/` when a Gradescope target is set).

### Pack manifest schema

```yaml
# exam.build.yaml
course: CECS 378          # required — naming + register/provenance
term: su26                # required
exam: Exam 1              # required — human label

forms:                    # required; 1 entry = single exam, 2+ = A/B/C…
  - { id: A, source: 378-exam1-su26-A.tex }
  - { id: B, source: 378-exam1-su26-B.tex }

individualized: true      # default false; true = per-student serials + pre-filled NAME/ID
roster: roster.csv        # required when individualized; CSV needs a `name` column,
                          # plus an OPTIONAL `student_id` column to pre-fill the ID line

assign: alternating       # alternating (default) | seeded-random | every-form
assign_seed: "378su26e1"  # required when assign: seeded-random (any string)

gradescope: region        # region | bubble | none (default none)
points: 50                # optional total, for the outline aid / cross-check
```

### Forms × individualized matrix

| `forms` | `individualized` | What you get |
|---|---|---|
| 1 | false | `build/A.pdf` + `build/A_key.pdf` — equivalent to legacy `.tex` mode |
| 2+ | false | Per-form `<id>.pdf` + `<id>_key.pdf`; no per-student outputs |
| 1 | true | One `<exam-slug>_combined.pdf` print PDF (per-student copies under `build/.parts/`) + `build/register.csv` |
| 2+ | true | One combined print PDF across all forms (roster order) + one `register.csv` (roster split across forms), sorted by `canonical_name`. `print_layout: per-form` → legacy per-form stacks. |

`build/register.csv` columns: `name, form, canonical_name, source_serial, student_serial, output_pdf`.

### Pre-filled identity block (individualized builds)

Individualized builds pre-print each student's **name** on the NAME line and their
**student ID** on the STUDENT ID# line — the student only adds the DATE. The text
sits *on* the rule (not floating above it). This requires the exam `.tex` to use the
identity-block doctrine (`\fieldline` + `\identityinstruction`, `\studentname` /
`\studentid` / `\studentserial` defined via `\@ifundefined`+`\def`, not
`\providecommand`); see `notes/exam-tex-doctrine.md`. Injection chain:

- `reg-exam-build` reads the roster's optional `student_id` column and injects
  `\def\studentname`, `\def\studentid`, `\def\studentserial` per student.
- In pack mode the per-form sub-roster carries `name,student_id` so the ID survives
  the A/B split.
- A roster with **no** `student_id` column still works — name prints, ID line stays
  blank for hand-entry (backward-compatible).
- The masthead instruction auto-swaps: pre-filled exams say *“VERIFY YOUR NAME AND
  STUDENT ID … THEN ADD TODAY'S DATE”*; blank copies keep *“PRINT CLEARLY. UNNAMED
  EXAMS CANNOT BE RETURNED OR GRADED.”* The footer `Serial · ID` (source serial +
  per-student serial) is retained for forensics/appeals regardless.

### Gradescope products (`gradescope/` subdirectory)

Produced only when `gradescope:` is `region` or `bubble`. **region** → per-form
`<id>_template.pdf` (the *blank* form — the AI-grading "negative", never the key),
`<id>_answer_key.pdf`, `<id>_outline.csv`; **bubble** → `<id>_bubble_key.csv` (≤5
versions) + outline; plus `gradescope_roster.csv` (Email column blank — see README
caveat; prefer LMS/LTI sync). Full details in README `### Gradescope products`.

> **How to grade the result in Gradescope** — step-by-step (region/bubble setup, A/B
> Version Sets, roster, the per-student-serial identity/appeals integration):
> `notes/gradescope-exam-workflow.md`.

### Grade-appeals reproduction

Every build is deterministically reproducible (`reg-exam-build exam.build.yaml`) and the
register + footer Serial/ID resolve any paper to one student + one form via
`reg-exam-verify`. Full runbook: `notes/exam-tex-doctrine.md`.
