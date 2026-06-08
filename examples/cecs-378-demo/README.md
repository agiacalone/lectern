# CECS 378 — Worked Lectern Demo

This directory walks through the **complete lectern workflow** for one section of
*Introduction to Computer Security Principles* (CECS 378), using synthetic students
and an illustrative exam.  Every command shown below is real and runnable.

Files in this directory:

| File | Purpose |
|------|---------|
| `term.spec.yaml` | Term-spec fed to `reg-term-create` |
| `roster.csv` | 10 synthetic students (`0401001xx` IDs) |
| `exam1.tex` | Illustrative Exam 1 source (50 pts; fresh demo questions) |
| `exam.build.yaml` | Pack-mode manifest for `reg-exam-build` |
| `canvas_grades_raw.csv` | Synthetic Canvas export (raw format) |
| `gradebook-schema.yaml` | Column/weight schema for `reg-gradebook` |
| `gradebook.csv` | Sample consolidated gradebook (pre-built output) |
| `archive-snippet/manifest.yaml` | What `reg-term-archive` writes at end-of-term |
| `build/` | Exam PDFs produced by `reg-exam-build exam.build.yaml` |
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
  source serial: AD7D24AB
  + exam1.pdf
  + exam1_key.pdf
```

The source serial is a deterministic hash of the `.tex` content.  Both PDFs carry it
in the footer (`Serial AD7D24AB`).  The key PDF has a red banner:
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
points: 50
```

**Output:**

```
  forms: A
  + build/  (10 student PDF(s))
  + build/register.csv
```

Each student receives a PDF with their name and ID pre-printed on the identity block.
The footer carries both the source serial and a per-student serial
(`Serial AD7D24AB · ID <student-serial>`).

**`build/register.csv` (produced — actual output from this build):**

```
name,form,canonical_name,source_serial,student_serial,output_pdf
Alice Nakamura,A,alice nakamura,AD7D24AB,3D3754D3,A_alice-nakamura_3D3754D3.pdf
Bob Okonkwo,A,bob okonkwo,AD7D24AB,36765CD0,A_bob-okonkwo_36765CD0.pdf
Carmen Delgado,A,carmen delgado,AD7D24AB,62311DE6,A_carmen-delgado_62311DE6.pdf
Devon Hartley,A,devon hartley,AD7D24AB,8A8843B5,A_devon-hartley_8A8843B5.pdf
Elena Vasquez,A,elena vasquez,AD7D24AB,B20BBD3C,A_elena-vasquez_B20BBD3C.pdf
Frank Osei,A,frank osei,AD7D24AB,FA87600E,A_frank-osei_FA87600E.pdf
Grace Lindqvist,A,grace lindqvist,AD7D24AB,65A5224D,A_grace-lindqvist_65A5224D.pdf
Hiro Tanaka,A,hiro tanaka,AD7D24AB,2FAA375A,A_hiro-tanaka_2FAA375A.pdf
Ines Moreau,A,ines moreau,AD7D24AB,BF94EC30,A_ines-moreau_BF94EC30.pdf
James Kowalczyk,A,james kowalczyk,AD7D24AB,50634313,A_james-kowalczyk_50634313.pdf
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
reg-exam-verify --serial AD7D24AB --student-serial 3D3754D3 --register build/register.csv
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
Alice Nakamura,040100101
Bob Okonkwo,040100102
Carmen Delgado,040100103
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
040100101,Alice Nakamura,89.47,89.75,B,B,canvas
040100102,Bob Okonkwo,77.60,79.50,C,C,canvas
040100103,Carmen Delgado,95.40,95.25,A,A,canvas
```

`letter_grade` is the truth-of-record: it prefers the Canvas Override Grade when
set, then the Canvas-computed Final Grade, then the schema-derived cut as fallback.
`grade_source` tells you which path was taken (`override` / `canvas` / `schema` /
`withdrawn`).

**Grade distribution for this cohort:**

```
A: 2  (Moreau, Delgado)
B: 3  (Nakamura, Osei, Lindqvist)
C: 2  (Okonkwo, Tanaka)
D: 1  (Hartley)
F: 2  (Vasquez, Kowalczyk)
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

## Exam question topics covered

The 8 illustrative questions in `exam1.tex` cover:

| # | Topic | Points |
|---|-------|--------|
| 1 | Symmetric vs. asymmetric key definition | 4 |
| 2 | Hash function collision resistance | 4 |
| 3 | RSA encryption (public key use) | 4 |
| 4 | Stack buffer overflow — saved return address | 4 |
| 5 | Principle of least privilege | 4 |
| 6 | Hybrid encryption rationale (short answer) | 10 |
| 7 | Buffer overflow mitigations: canary, NX, ASLR (short answer) | 10 |
| 8 | DAC vs. MAC access control models (short answer) | 10 |

These are **illustrative demo questions** written for this example — they do not
reproduce any live exam bank.

---

## Safety notes

- All student names and IDs in this demo are **entirely synthetic**.
  IDs are in the `040100101`–`040100110` range (no overlap with any real CSULB student
  ID space, which is in the `02xxxxxxx` range).
- `exam1.tex` contains fresh questions written for this demo; it does not
  reproduce any live or past CECS 378 exam.
- No internal infrastructure hostnames, real email addresses, real course sections,
  or real Drive paths appear in any demo file.
