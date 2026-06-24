# CECS 378 — Worked Lectern Demo

This directory walks through the **complete lectern workflow** for one section of
*Introduction to Computer Security Principles* (CECS 378), using synthetic students
and an illustrative exam.  Every command shown below is real and runnable.

Files in this directory:

| File | Purpose |
|------|---------|
| `term.spec.yaml` | Term-spec fed to `reg-term-create` |
| `roster.csv` | 10 synthetic students (`0401001xx` IDs) |
| `cecs-378-su26-01-syllabus-20001/` | Synthetic syllabus repo for `reg-syllabus` (source + stamped + rendered HTML) |
| `exam1.tex` | Illustrative Exam 1 source (60 pts; 5 MC + 5 T/F + 3 SA; fresh demo questions) |
| `exam.build.yaml` | Pack-mode manifest for `reg-exam-build` (`gradescope: region`) |
| `cecs-378-question-bank.md` | Synthetic exam-source question bank for `reg-qbank` |
| `exam_reading_lists.yaml` | Manifest for `reg-exam-readinglist` |
| `lectures/` | Scriptorium lecture-main(s) consumed by `reg-exam-readinglist` |
| `canvas_grades_raw.csv` | Synthetic Canvas export (raw format) |
| `gradebook-schema.yaml` | Column/weight schema for `reg-gradebook` |
| `gradebook.csv` | Sample consolidated gradebook (pre-built output) |
| `archive-snippet/manifest.yaml` | What `reg-term-archive` writes at end-of-term |
| `build/` | Exam PDFs produced by `reg-exam-build exam.build.yaml` |
| `gradescope/` | Gradescope region products: templates, answer keys, `A_outline.csv`, roster |
| `GRADING_NOTE.md` | Per-form answer-key + rubric crib emitted by the `gradescope:` build |
| `gradescope-stats/` | Synthetic Gradescope evaluations + `reg-gradescope-stats` item analysis |
| `exam1/products/` | Per-exam reading-list study guide from `reg-exam-readinglist` |
| `gradebook-out/` | `gradebook.csv` + `gradebook.md` from `reg-gradebook import` |

---

## Stage A — Scaffold the term

### 1. Write the stub spec

```sh
reg-term-create --term su26 --init --vault-root /path/to/vault
```

This writes `classes/su26.spec.yaml` with placeholder fields.  Replace it with
`term.spec.yaml` from this directory (or hand-edit the stub).

**`term.spec.yaml` (excerpt):**

```yaml
term: su26
term-name: Summer 2026
year: 2026
semester-code: su
instructor: A. Instructor
start: 2026-06-02
end: 2026-07-25
finals-week-start: 2026-07-27
finals-week-end: 2026-07-31
grade-submission-deadline: 2026-08-07

sections:
  - course: CECS 378
    section: "01"
    class-number: 20001
    room: ECS-403
    meets: "MWF 09:00-10:50"
    enrolled: 10
    final-exam-date: 2026-07-28
```

### 2. Materialize vault files

```sh
reg-term-create --term su26 --vault-root /path/to/vault
```

Creates (idempotently — existing files are skipped):

```
classes/su26.md                              ← semester note
classes/378-478/378-01-su26.md              ← section class note
classes/378-478/archives/su26-01/manifest.yaml  ← skeleton manifest
```

Also wires a link under `## ☷ Sections taught` in the course MOC file if present.

---

## Stage B — Build the exam

### 3. Single-form mode (quick check / print run)

```sh
cd examples/cecs-378-demo
reg-exam-build exam1.tex
```

**Output:**

```
  source serial: C0162D5D
  + exam1.pdf
  + exam1_key.pdf
```

The source serial is a deterministic hash of the `.tex` content.  Both PDFs carry it
in the footer (`Serial C0162D5D`).  The key PDF has a red banner:
`★  ANSWER KEY  ---  NOT FOR DISTRIBUTION  ★`.

### 4. Pack mode — individualized per-student build

```sh
reg-exam-build exam.build.yaml
```

**`exam.build.yaml`:**

```yaml
course: CECS 378
term: su26
exam: Exam 1

forms:
  - { id: A, source: exam1.tex }

individualized: true
roster: roster.csv
assign: alternating
points: 60
gradescope: region
```

**Output:**

```
  forms: A
  + build/  (10 student PDF(s))
  + build/cecs-378-demo_combined.pdf  (single print PDF, roster order)
  + build/register.csv
  + gradescope/  (region)
```

The `gradescope: region` target also writes a `gradescope/` folder (per-form
`A_template.pdf`, `A_answer_key.pdf`, `A_outline.csv`, `gradescope_roster.csv`)
plus a human-readable `GRADING_NOTE.md` crib next to the manifest. See
[Gradescope workflow](../../docs/gradescope-workflow.md).

Each student receives a PDF with their name and ID pre-printed on the identity block.
The footer carries both the source serial and a per-student serial
(`Serial C0162D5D · ID <student-serial>`).

**`build/register.csv` (produced — actual output from this build):**

```
name,form,canonical_name,source_serial,student_serial,output_pdf
Bruce Wayne,A,bruce wayne,C0162D5D,B4CAD278,.parts/A_bruce-wayne_B4CAD278.pdf
Dick Grayson,A,dick grayson,C0162D5D,591F93BC,.parts/A_dick-grayson_591F93BC.pdf
Barbara Gordon,A,barbara gordon,C0162D5D,6D46E263,.parts/A_barbara-gordon_6D46E263.pdf
Selina Kyle,A,selina kyle,C0162D5D,0E198195,.parts/A_selina-kyle_0E198195.pdf
Oswald Cobblepot,A,oswald cobblepot,C0162D5D,3CA532BA,.parts/A_oswald-cobblepot_3CA532BA.pdf
Harvey Dent,A,harvey dent,C0162D5D,46D9B97F,.parts/A_harvey-dent_46D9B97F.pdf
Pamela Isley,A,pamela isley,C0162D5D,DE77C0EA,.parts/A_pamela-isley_DE77C0EA.pdf
Edward Nashton,A,edward nashton,C0162D5D,FEA593F6,.parts/A_edward-nashton_FEA593F6.pdf
Kate Kane,A,kate kane,C0162D5D,CDDBED64,.parts/A_kate-kane_CDDBED64.pdf
Jason Todd,A,jason todd,C0162D5D,C42728F0,.parts/A_jason-todd_C42728F0.pdf
```

`build/A_combined.pdf` is the full class print stack (alphabetical by canonical name),
ready to hand to the copy room.

#### What an A/B split looks like

Add a second form to get two exam variants:

```yaml
forms:
  - { id: A, source: 378-exam1-su26-A.tex }
  - { id: B, source: 378-exam1-su26-B.tex }
assign: alternating    # or seeded-random
```

Students are assigned alternating forms; `register.csv` gains a `form` column so
you know which paper belongs to which variant.

#### Grade-appeals: verify a submitted paper

```sh
reg-exam-verify --serial C0162D5D --student-serial 3D3754D3 --register build/register.csv
```

Returns the student name and form, confirming the paper is authentic and unaltered.

---

## Stage C — Import roster and grades

### 5. Normalize the LMS roster

The MyCSULB Faculty Center exports a roster as a `.xls` file (actually malformed HTML).
The importer parses it and emits a clean CSV.

```sh
reg-lms-roster-import class-roster-cecs-378-01-20001.xls \
    --out roster.csv \
    --term su26
```

For this demo, `roster.csv` is already in its normalized form:

```
name,student_id
Bruce Wayne,040100101
Dick Grayson,040100102
Barbara Gordon,040100103
...
```

### 6. Normalize Canvas grades

Export the gradebook from Canvas → download → `grades.csv`.  The raw export has three
header rows (column headers / manual-posting flags / points-possible) before the first
student row, plus ISA accounts ending in `SA`.

```sh
reg-lms-grades-import canvas_grades_raw.csv --out grades.csv
```

**Console output:**

```
→ grades.csv (10 students normalized)
```

Side files produced alongside `grades.csv`:
- `grades.filtered.csv` — ISA accounts removed from the main table
- `grades.points-possible.json` — per-assignment max points
- `grades.raw.csv` — provenance copy of the original Canvas export

---

## Stage D — Consolidate the gradebook

### 7. Run the gradebook importer

```sh
reg-gradebook import \
    --course CECS_378 \
    --term su26 \
    --section 01 \
    --canvas-csv grades.csv \
    --roster-csv roster.csv \
    --schema gradebook-schema.yaml \
    --out gradebook-out/
```

**Console output:**

```
→ gradebook-out/gradebook.csv (10 rows)
→ gradebook-out/gradebook.md
```

`gradebook-schema.yaml` defines which Canvas columns map to which grade groups and
their weights (labs 40% / exams 60%) and the letter-grade cut points.

**`gradebook.csv` (selected columns, head -4):**

```
student_id,display_name,weighted_score,canvas_final_score,canvas_final_grade,letter_grade,grade_source
040100101,Bruce Wayne,89.47,89.75,B,B,canvas
040100102,Dick Grayson,77.60,79.50,C,C,canvas
040100103,Barbara Gordon,95.40,95.25,A,A,canvas
```

`letter_grade` is the truth-of-record: it prefers the Canvas Override Grade when
set, then the Canvas-computed Final Grade, then the schema-derived cut as fallback.
`grade_source` tells you which path was taken (`override` / `canvas` / `schema` /
`withdrawn`).

**Grade distribution for this cohort:**

```
A: 2  (Kane, Gordon)
B: 3  (Wayne, Dent, Isley)
C: 2  (Grayson, Nashton)
D: 1  (Kyle)
F: 2  (Cobblepot, Todd)
DFW rate: 30%
```

`gradebook.md` is a DataviewJS view wired into the vault — it renders the table live
from `gradebook.csv` without duplicating data.

---

## Stage E — Term archive

### 8. Build the section archive bundle

At end of term, after all grades are entered in Canvas:

```sh
reg-term-archive \
    --course "CECS 378" \
    --course-dir 378-478 \
    --term su26 \
    --section 01 \
    --vault-root /path/to/vault \
    --roster-xls class-roster-cecs-378-01-20001.xls \
    --canvas-csv canvas_grades_raw.csv \
    --schema gradebook-schema.yaml \
    --exam-dir exams/exam1_su26/build
```

This produces `classes/378-478/archives/su26-01/` containing:

```
manifest.yaml          ← machine-readable record of everything
README.md              ← human-readable summary (rendered below)
roster.csv             ← normalized MyCSULB roster
grades.csv             ← joined roster+Canvas grades
gradebook.csv          ← schema-weighted grades + letter grades
gradebook.md           ← DataviewJS vault view
exams/
  exam1.tex            ← source (provenance)
  exam1.pdf            ← student exam
  exam1_key.pdf        ← answer key
  exam1_serials.csv    ← per-student serial register
```

`archive-snippet/manifest.yaml` in this demo shows the full schema of that file.

### 9. Validate drift

After the archive is built, the `--check` flag re-validates it at any time:

```sh
reg-term-archive --check \
    --course "CECS 378" \
    --course-dir 378-478 \
    --term su26 \
    --section 01 \
    --vault-root /path/to/vault
```

**Output (clean run):**

```
✓ 8  ✗ 0
```

Checks performed: manifest schema validation, all referenced files exist, exam source
serials match the archived `.tex` (drift detection), grade distribution matches the
archived `gradebook.csv`.

### 10. Term-wide rollup

```sh
reg-term-archive --term su26 --vault-root /path/to/vault
```

Walks every `classes/*/archives/su26-*/` directory and validates all bundles:

```
  [OK] classes/378-478/archives/su26-01  ok=8 fail=0
  [OK] classes/378-478/archives/su26-02  ok=8 fail=0

2 bundle(s) inspected for term su26
```

---

## Stage F — Companion tools

These commands round out the term, all runnable against this demo directory.

### 11. Syllabus — stamp + build (`reg-syllabus`)

The syllabus lives in its own GitHub Classroom repo (named
`cecs-378-su26-01-syllabus-20001`). `stamp` injects a tamper-evident
control-number serial; `build` renders the HTML + a Canvas-RCE-safe variant.

```sh
reg-syllabus stamp cecs-378-su26-01-syllabus-20001 --vault-root /path/to/vault
reg-syllabus build  cecs-378-su26-01-syllabus-20001
```

```
stamped cecs-378-su26-01-syllabus-20001: serial F6F1264A
built: syllabus.html, syllabus_canvas.html
```

`stamp` writes `serial: F6F1264A` into the syllabus frontmatter + a footer line,
and appends a row to `<vault>/notes/syllabus-serial-register.md`. `build` emits
`syllabus.html` (full styling) and `syllabus_canvas.html` (inline-only, safe to
paste into a Canvas page).

### 12. Question bank — validate + emit (`reg-qbank`)

`cecs-378-question-bank.md` is the exam-source bank: one bare-mapping YAML record
per fenced ```` ```yaml ```` block (`mc` / `tf` / `fib` / `code`; non-`fib` types
carry a `none` outcome).

```sh
reg-qbank validate cecs-378-question-bank.md      # → OK — 4 question(s) valid.
reg-qbank emit cecs-378-question-bank.md          # canonical summary (or --json)
```

### 13. Exam reading list (`reg-exam-readinglist`)

Consolidates the topics an exam covers into a single study guide, driving the
**Scriptorium** CLI (the Lectern→Scriptorium seam). Reads `exam_reading_lists.yaml`
and the lecture-main(s) under `lectures/`.

```sh
reg-exam-readinglist --manifest exam_reading_lists.yaml --no-pdf
```

```
  ✓ exam1: exam1/products/exam1_reading_list.md
```

### 14. Item analysis (`reg-gradescope-stats`)

After grading in Gradescope, export the per-question evaluations and run a
per-distractor item analysis.

```sh
reg-gradescope-stats \
    --eval-dir gradescope-stats/evals \
    --grading-note gradescope-stats/GRADING_NOTE.md \
    --out-dir gradescope-stats/out \
    --course "CECS 378" --term su26 --section 01 --exam "Exam 1"
```

```
→ gradescope-stats/out : item_analysis.json, ITEM_ANALYSIS.md, item_analysis.html, item_scores_A.csv (10 questions, 1 forms)
```

`ITEM_ANALYSIS.md` reports per-question difficulty (*p*), per-distractor selection
counts, and flags **dead** distractors (chosen by nobody) and possible **miskeys**
(a distractor chosen more than the key).

> **Known format gap.** `reg-exam-build` emits a *summary-table* `GRADING_NOTE.md`
> (`| Q | Name | Pts | Type | Answer | Rubric |`), but `reg-gradescope-stats`
> consumes the richer *per-question* form (`#### <Form>·Q<n> · <name> · <pts> · <TYPE>`
> with `| Pts | Key | Rubric item |` tables). They do not yet match, so this stage
> uses a hand-authored stats-compatible note at `gradescope-stats/GRADING_NOTE.md`.
> Bridging the two formats is a tracked follow-up.

---

## Commands requiring live infrastructure

These lectern commands are part of the workflow but need external systems, so they
are documented here rather than run in this self-contained demo:

- **`reg-classroom-roster-seed`** — pre-seed a GitHub Classroom roster from the
  normalized roster CSV (needs a Classroom org).
- **`reg-github-bind`** — bind student GitHub usernames to roster entries from a
  Google Form / Classroom roster / org scrape (needs GitHub).
- **`reg-c50-classroom-add`** — Classroom-50 successor wiring (needs the Classroom-50 org).
- **`reg-isa-publish`** — publish ISA grading artifacts (keys, rubrics, print stacks)
  to a shared Drive folder via rclone / service account (needs Google Drive).
- **`reg-triage`** — git-history authenticity triage over a lab's student-repo
  population: `sweep` → FLAG/REVIEW/PASS, `report` → two-tier audit (needs cloned
  student repos / an org to scrape).
- **`reg-term-finalize`** — reconcile grade distributions, flip section statuses to
  finalized, roll up enrollment-weighted aggregates (needs the populated vault term tree).

---

## Exam question topics covered

The 13 illustrative questions in `exam1.tex` (60 pts: 5 MC + 5 T/F + 3 SA) cover:

| # | Type | Topic | Points |
|---|------|-------|--------|
| 1 | MC | Symmetric-key cipher definition | 4 |
| 2 | MC | Hash function collision resistance | 4 |
| 3 | MC | RSA encryption (recipient public key) | 4 |
| 4 | MC | Stack buffer overflow — saved return address | 4 |
| 5 | MC | Principle of least privilege | 4 |
| 6 | T/F | AES is a symmetric cipher | 2 |
| 7 | T/F | Hash maps to a fixed-length output | 2 |
| 8 | T/F | RSA confidentiality uses the recipient's public key | 2 |
| 9 | T/F | NX stack does not by itself stop ROP | 2 |
| 10 | T/F | Least privilege limits blast radius | 2 |
| 11 | SA | Hybrid encryption rationale | 10 |
| 12 | SA | Buffer overflow mitigations: canary, NX, ASLR | 10 |
| 13 | SA | DAC vs. MAC access control models | 10 |

T/F questions use the stacked `(a) True / (b) False` house standard so Gradescope's
region detection finds the choices. These are **illustrative demo questions** written
for this example — they do not reproduce any live exam bank.

---

## Safety notes

- All student names and IDs in this demo are **entirely synthetic**.
  IDs are in the `040100101`–`040100110` range (no overlap with any real CSULB student
  ID space, which is in the `02xxxxxxx` range).
- `exam1.tex`, `cecs-378-question-bank.md`, the syllabus, and the
  `gradescope-stats/` evaluations all contain fresh synthetic content written for
  this demo; none reproduce any live or past CECS 378 material, grades, or roster.
- The `@student.csulb.edu` emails in the synthetic Gradescope export are fabricated
  for the demo students and resolve to no real accounts.
- No internal infrastructure hostnames, real email addresses, real course sections,
  or real Drive paths appear in any demo file.
