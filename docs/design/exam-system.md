# Multi-Form Exam System — Design

**Status:** implemented in `lectern/exam_build.py` + `lectern/exam_pack.py`

This document describes the design of lectern's exam build system: how it produces
multiple hand-authored form variants (A/B/C), per-student individualized copies,
and Gradescope import products — and why the system is designed the way it is.

---

## 1. Summary

A single exam can be produced as one or more hand-authored forms (A/B/C variants
for adjacency-copy protection) and, orthogonally, as plain or per-student-individualized
copies (unique serials for proxy detection and leak forensics). These two dimensions
**compose** into a 2×2 matrix. The same build emits Gradescope import products for
whichever grading workflow the exam uses.

The orchestration is **manifest-driven**: a per-exam `exam.build.yaml` file declares
the forms, mode, roster, form-assignment policy, and Gradescope target.
`reg-exam-build` dispatches on the input type — a `.tex` file uses the existing
single-source behavior; a `.yaml` file enters "pack mode". A dedicated `exam_pack`
module owns orchestration; per-form compilation reuses the existing, tested
`build_variant` / `build_roster` functions.

**No content generation.** Forms are hand-authored. lectern orchestrates building,
splitting, serializing, and packaging — it never writes exam questions.

---

## 2. Why this design

### 2.1 Open formats, front to back

Every input and output in the exam pipeline is plain-text or standard PDF:

- **`.tex`** — the exam source. Authored by hand, committed to Git, buildable with any
  standard LaTeX installation. The content of an exam is its `.tex` file. The answer
  key is the same file compiled with an `\answersmode` flag.
- **`exam.build.yaml`** — the build manifest. Declares which forms to build, whether
  to individualize, what roster to use, and what Gradescope products to emit. Committed
  alongside the `.tex` files; together they fully specify a build.
- **`roster.csv`** — student name and optional student-ID columns. A plain CSV.
- **`register.csv`** — the output record: which student got which form, and what their
  printed serial was. Another plain CSV.
- **`_outline.csv`** — per-question points, type, and answer. Machine-readable, suitable
  for import into any grading tool.

None of this requires a proprietary format. The entire exam archive — source, manifest,
roster, register, compiled PDFs — can be reproduced, verified, or inspected with
standard open-source tools.

### 2.2 Defensibility is the primary design requirement

> Every design decision below is in service of one property: **given a graded exam
> and a student's grade appeal, we can reproduce the exact paper that student received,
> prove which form and serial it was, show the canonical answer key and point values it
> was graded against, and demonstrate that all forms were equivalent in coverage and
> weight.**

Grade appeals are the dominant challenge surface for high-stakes exams. The system
is designed so that every question asked on a challenge — "was this really my exam?",
"was my version harder?", "was this question ever taught?" — can be answered with
documented, reproducible evidence rather than instructor recollection.

---

## 3. The build matrix

`reg-exam-build` dispatches on its input:

```
reg-exam-build <input>
   ├── input *.tex  → build_variant / build_roster   (single-source mode, unchanged)
   └── input *.yaml → exam_pack.run(manifest)         (pack mode)
                         ├── per-form: build_variant or build_roster  (reused)
                         ├── roster split + form assignment
                         ├── register consolidation (with form column)
                         └── Gradescope product emission
```

The four cells of the matrix, each reusing existing tested code:

| `forms` | `individualized` | What is produced | Reuses |
|---|---|---|---|
| 1 | false | `build/A.pdf` + `build/A_key.pdf` | `build_variant` |
| 2+ | false | Per-form `<id>.pdf` + `<id>_key.pdf` | `build_variant` × N |
| 1 | true | Per-student stack + register + combined | `build_roster` |
| 2+ | true | Roster split by assignment policy; one serialized copy per student; per-form combined stacks; one `register.csv` with a `form` column | `build_roster` × N (per assigned sub-roster) |

---

## 4. Manifest schema — `exam.build.yaml`

The manifest lives in the exam directory beside the form `.tex` files. It is the
canonical, version-controlled specification for a build.

```yaml
course: CECS 378            # required — provenance and labeling
term: fa26                  # required
exam: Midterm 1             # required — human label

forms:                      # required; 1 entry = single exam, 2+ = A/B/C
  - { id: A, source: cecs378-midterm1-fa26-A.tex }
  - { id: B, source: cecs378-midterm1-fa26-B.tex }

individualized: false       # default false; true = per-student serials + pre-filled NAME/ID
roster: roster.csv          # required when individualized: true; CSV with a 'name' column
                            # and an optional 'student_id' column to pre-fill the ID line

assign: alternating         # form-assignment policy when individualized AND len(forms) > 1:
                            #   alternating  — round-robin by sorted name (default, balanced ±1)
                            #   seeded-random — deterministic shuffle keyed by assign_seed
                            #   every-form   — every student gets a copy of every form
assign_seed: "fa26m1"       # required when assign: seeded-random; recorded in the register

gradescope: region          # region | bubble | none (default none)
points: 50                  # optional total, for outline cross-check
```

### Validation rules (fail fast, before any compile)

| Rule | Error |
|---|---|
| `forms` non-empty, unique `id` values, each `source` exists | hard error before compile |
| `individualized: true` requires `roster` present with a `name` column | reuses `_read_roster` error |
| `individualized: true` requires each form `.tex` to have per-student macros | prefixed with form ID |
| `assign: seeded-random` requires `assign_seed` | hard error |
| `gradescope: bubble` with non-MC items detected | warning (still emits MC rows) |

All validation runs before any compilation. No partial output is written on error.

---

## 5. Form assignment

When `individualized: true` and multiple forms exist, every student is assigned to
exactly one form. Three policies:

- **`alternating`** (default): sort the roster by canonical name; round-robin A, B, A, B.
  Balanced within ±1 student. Stable and seed-free.
- **`seeded-random`**: deterministically shuffle the roster using `assign_seed` (any
  string), then round-robin. Same seed always produces the same split. The seed is
  recorded in the register header so the split can be reproduced.
- **`every-form`**: skip the split; each student gets a serialized copy of every form
  (register rows = len(forms) × roster size). Used for makeup / alternate-time exams.

The split writes a per-form sub-roster, then calls `build_roster` for each form against
its sub-roster, then concatenates the registers with a `form` column added.

---

## 6. Per-student serials — the tamper-evidence layer

Each individualized copy carries two identifiers in the page-1 footer:

```
Serial XXXXXXXX · ID YYYYYYYY
```

**`Serial`** (source serial) — an 8-hex SHA-256 hash of the canonicalized `.tex`
content. Same for every copy of the same form. Changes if the exam source is edited
after the fact — making post-hoc tampering self-evident.

**`ID`** (student serial) — an 8-hex hash of `source_serial + ":" + canonical_name`:

```
student_serial = SHA-256(source_serial + ":" + canonical_name(student_name))[:8].upper()
```

`canonical_name` strips diacritics, lowercases, collapses whitespace, and drops
trailing suffixes (`Jr`, `III`, etc.). The same canonicalization is used by
`reg-exam-verify`, so verification round-trips reliably.

**What this enables:**

- Any page of any printed exam identifies its student: the footer's `ID` resolves to
  exactly one roster row via `reg-exam-verify`.
- A paper whose footer ID does not hash from that student's name is immediately flagged
  — whether from a copy/swap, a printing error, or a forgery attempt.
- The source serial changes if the `.tex` is edited — so an archived exam whose serial
  matches the register is a reproducibility guarantee.

**Verification:**

```bash
# Single-paper check:
reg-exam-verify --student "Doe, Jane" --register build/register.csv

# Bulk check of a print run:
reg-exam-verify --register build/register.csv --dir build/
# exits 0 on all-clean, 1 on any mismatch with diagnostics
```

The verifier is self-contained: it extracts `Serial` + `ID` from the PDF's own
footer, recomputes the expected ID from the source serial + the student name,
and compares. The register is a convenience cross-check; the PDF is self-authenticating.

---

## 7. Defensibility and grade appeals

The audit trail that makes every exam defensible at grade-appeal:

1. **Deterministic reproduction.** Manifest + `.tex` files + roster + `assign_seed`
   fully determine every artifact. Re-running `reg-exam-build exam.build.yaml`
   regenerates byte-identical content (serials, split, form assignments — the only
   non-deterministic element is the compile-time timestamp in the footer, which does
   not affect any forensic ID). The manifest and `.tex` files are committed to Git;
   nothing about the build is improvised.

2. **Per-student, per-form record.** The `register.csv` maps
   `name → form → source_serial → student_serial → output_pdf`. Given a scanned
   paper, its footer `Serial + ID` resolve — via `reg-exam-verify` — to exactly one
   roster row and one form.

3. **Answer-key provenance.** Each form ships its own `*_key.pdf` (the key it was
   graded against) and `*_outline.csv` (per-question points + correct answer). A
   `PROVENANCE.md` in the exam directory maps each item to its source material
   (lecture slides, textbook sections, reading assignments) — so "this question was
   never taught" appeals are answerable with a citation.

4. **Form-equivalence evidence.** When multiple forms (A/B) are used, the fairness
   argument — "my version was harder" — is answered by comparing the per-form
   `_outline.csv` files (same point total, same topic distribution) and the
   `PROVENANCE.md` difficulty and topic tags.

5. **Tamper-evidence via serial.** The `source_serial` is the content hash of the
   form. If a form `.tex` is edited after administration, its serial changes — a
   reproduced exam that does not match the archived serial is self-evidently not
   what was administered.

---

## 8. Gradescope products

Setting `gradescope: region` or `gradescope: bubble` in the manifest causes
`reg-exam-build` to write a `gradescope/` subdirectory alongside `build/`.

### Region target (fixed-template, rubric grading)

For exams with short-answer, fill-in-the-blank, or code questions:

| File | Purpose |
|---|---|
| `<form>_template.pdf` | The **blank, un-serialized** form. Uploaded to Gradescope as the assignment template (the "negative" used for AI region detection). Never the key; never a serialized copy. |
| `<form>_answer_key.pdf` | Instructor reference key. Not uploaded; kept locally. |
| `<form>_outline.csv` | `q_num, points, type, answer` — speeds building the Gradescope outline and entering answer keys. |

### Bubble target (MC autograde)

For pure multiple-choice exams:

| File | Purpose |
|---|---|
| `<form>_bubble_key.csv` | `version, q_num, answer, points` — maps to Gradescope's per-version answer-key page (supports up to 5 versions). |
| `<form>_outline.csv` | Same structure as region mode. |

A `gradescope_roster.csv` (`First Name, Last Name, SID, Email`) is emitted whenever
a roster is present. The `Email` column is blank — lectern's roster CSV carries no
email addresses. Gradescope matches submissions primarily by email, so LMS/LTI sync
(Canvas → Gradescope) is the recommended roster path; `gradescope_roster.csv` is a
convenience fallback.

### Multi-form builds and Gradescope Version Sets

Gradescope's Multi-version Assignment feature maps naturally onto A/B builds: each
form becomes its own assignment version with its own template and answer key. See
[docs/gradescope-workflow.md](../gradescope-workflow.md) for the full step-by-step.

---

## 9. Output layout

```
exams/<exam-slug>/
  exam.build.yaml              # manifest — committed to Git
  cecs378-midterm1-fa26-A.tex  # form source — committed
  cecs378-midterm1-fa26-B.tex  # form source — committed
  PROVENANCE.md                # per-item source citations — committed
  roster.csv                   # enrolled students — committed (or gitignored per policy)
  build/                       # derived artifacts — gitignored
    A.pdf  A_key.pdf  B.pdf  B_key.pdf
    cecs378-midterm1-fa26-A_doe-jane_YYYYYYYY.pdf   # individualized copies
    A_combined.pdf  B_combined.pdf                  # per-form print stacks
    register.csv                                     # name, form, serials, output_pdf
  gradescope/                  # Gradescope import products — gitignored
    A_template.pdf  A_answer_key.pdf  A_outline.csv
    B_template.pdf  B_answer_key.pdf  B_outline.csv
    gradescope_roster.csv
```

The `.tex`, `.yaml`, `PROVENANCE.md`, and `roster.csv` are version-controlled.
The `build/` and `gradescope/` directories contain derived artifacts that are
reproducible from the committed sources.

---

## 10. Architecture

`exam_pack.py` is orchestration-only:

- `ExamManifest` dataclass — parsed and validated manifest
- `load_manifest(path)` — parse + validate (all §4 rules checked before compile)
- `assign_forms(names, forms, policy, seed)` — pure, deterministic, unit-testable
- `run(manifest, workdir)` — drive the full matrix and emit products
- `emit_region_products()`, `emit_bubble_products()`, `emit_gradescope_roster()`
- `parse_outline_from_tex(tex)` — extract `q_num, points, type, answer` from `.tex`
  structure (scans `\textit{(N pts)}`, `\correctchoice`, `\textbf{Answer:}`)

`exam_pack` introduces no new LaTeX constructs and no new serial math. Both
rely entirely on the existing `exam_build` / `exam_serial` foundations.

`reg-exam-build` CLI: detects input suffix. `.yaml` / `.yml` → `exam_pack.run`.
Otherwise: current single-source `.tex` path, fully backward-compatible.

---

## 11. Testing

`tests/test_exam_pack.py` covers:

- Manifest parse + each validation error in §4
- `assign_forms` determinism: alternating balance (±1), seeded-random same-seed-same-split, every-form cardinality
- All four matrix cells produce the expected file sets
- Register has a `form` column and the correct row count per cell
- `parse_outline_from_tex` extracts correct points/answers/types from the fixture `.tex`
- Region + bubble + roster product schemas
- Bubble non-MC warning path

Existing `test_exam_build`, `test_exam_serial`, and `test_exam_verify` serve as the
backward-compatibility guard. All must remain green.
