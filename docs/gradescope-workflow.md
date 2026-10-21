# Using lectern-Built Exams with Gradescope

Step-by-step for taking a `reg-exam-build` exam into Gradescope for grading —
single form, A/B variants, and per-student-individualized, plus the
identity-verification integration for grade appeals.

Companion docs: [design/exam-system.md](design/exam-system.md) (system design,
build matrix, defensibility) and [design/exam-tex-format.md](design/exam-tex-format.md)
(the `.tex` format, per-student serials, appeals runbook).

---

## TL;DR

1. Build with a `gradescope:` target in the manifest — lectern writes a `gradescope/` folder.
2. Create a Gradescope assignment per form; for A/B, link them as a **Version Set**.
3. Upload each form's `<form>_template.pdf` (the blank form) as the template.
4. Build the outline and answer key using `<form>_outline.csv` as the crib.
5. Scan each form's paper stack separately; upload each to its own version.
6. The footer `Serial + ID` on every paper resolves to one student and one form
   via `reg-exam-verify` — the audit hook for grade appeals.

---

## 1. What lectern produces

Set `gradescope: region` or `gradescope: bubble` in `exam.build.yaml`, then run
`reg-exam-build exam.build.yaml`. Outputs land in two directories next to the manifest:

- **`build/`** — the printable exams: per-form blank `<id>.pdf`, key `<id>_key.pdf`,
  one `<exam-slug>_combined.pdf` (the single print deliverable — every student, all
  forms, roster order; per-student copies kept under `build/.parts/`), and
  `register.csv` (which student got which form and what serial). *(Set
  `print_layout: per-form` for the legacy per-form `<id>_combined.pdf` stacks.)*
- **`gradescope/`** — the import products covered in this document.
- **`GRADING_NOTE.md`** — the grading note (next to the manifest). One Markdown
  file per exam: exam identity, the Gradescope setup steps, and for every
  question **one rubric row per possible outcome**, with its points. Gradescope
  imports no key or rubric, so this is the work order a grader enters and then
  grades from. It is self-contained enough to hand to a TA/ISA who did not
  author the exam. See §1a.

### 1a. The grading note (`GRADING_NOTE.md`)

Question **names** and **rubric criteria** come from `% name:` / `% rubric:`
comments authored directly above each question's `\item` in the exam `.tex`:

```latex
% name: CIA — availability (backup destroyed in fire)
% rubric: Correct = (b) Availability. 2 pts, all-or-nothing.
\item \textit{(2 pts)}~A backup tape containing customer records ...
```

`% name:` is required on every question (a missing one fails the build, naming the
question number). `% rubric:` is required on `fib` and `code` questions and
optional on `mc`/`tf` (which default to "correct choice = full points, else 0").
The note collects all forms, so an A/B exam yields one note with a `## Form A` and
`## Form B` section.

**Every outcome gets a row.** Each question is a `#### <Form>·Q<n> · name · pts ·
TYPE` heading over a `| Pts | Key | Rubric item |` table. The grader enters every
row into Gradescope as a rubric item and then only decides which one applies, so a
grader who did not write the question applies points the same way, and a student
can see that every alternative was considered.

| Type | Rows |
|---|---|
| `mc` | one per choice, `(a)`…; only the `\correctchoice` carries `+N` |
| `tf` | `True` and `False`; the keyed side carries `+N` |
| `fib` | one per blank (`+N` each when the points divide evenly, else `·` and the *Scoring* caption rules), plus an `order` row for multi-blank fills unless `% order: any` precedes the question |
| `code` / written | the question's authored **Gradescope rubric** block, item for item, with its category as a `[Group]` tag (see `docs/design/exam-tex-format.md`); a code question whose answer is True/False gets the two T/F rows |

Every question also ends with a `none` row (*No answer / multiple marks*) unless
its authored rubric has its own catch-all. Credit is carried by the points: `+N`
rows credit, `0` rows do not and exist for feedback and statistics. Each row's
`form·Qn·slot` key is what `reg-gradescope-stats` joins to Gradescope's *Export
Evaluations* columns for per-distractor item analysis.

To refresh the note after editing an exam that is already printed, run
`reg-exam-build exam.build.yaml --grading-note-only`. It reads the form sources
and rewrites only `GRADING_NOTE.md`; no PDFs are rebuilt.

### Region target (fixed-template, rubric grading) — the standard

| File | Upload to Gradescope? | Purpose |
|---|---|---|
| **`<form>_template.pdf`** | Yes — as the assignment template | The blank, un-serialized form. Gradescope uses the template as a "negative" to subtract instructor ink and isolate student handwriting. |
| **`<form>_answer_key.pdf`** | No (instructor reference) | The annotated key with green correct answers and grey failure modes. |
| **`<form>_outline.csv`** | No (crib sheet) | `q_num, points, type, answer` — speeds building the Gradescope outline and entering the answer key in the UI. |
| **`gradescope_roster.csv`** | Optional fallback | `First Name, Last Name, SID, Email`. See §5. |

**Critical:** the template must be the **blank form**, not the answer key and not
a serialized student copy. Uploading a filled-in key as the template will break
Gradescope's AI region detection. The per-student footer serial varies per copy,
but it sits outside answer regions, so the canonical blank `<form>_template.pdf`
is the correct upload regardless of whether the exam was individualized.

### Bubble target (MC autograde)

For a pure multiple-choice exam, set `gradescope: bubble`. lectern emits:

- `<form>_bubble_key.csv` — `version, q_num, answer, points` matching
  Gradescope's per-version answer-key page (supports up to 5 versions).
- `<form>_outline.csv` — same structure as region mode.

**Bubble mode drops non-MC items.** Fill-in-the-blank and code questions cannot
autograde on a bubble sheet. lectern prints a warning listing affected question
numbers. If your exam has any FIB or code items, use the `region` target instead.

---

## 2. Region workflow — single form

1. **Create assignment** in Gradescope: select *Exam (variable length / fixed template)*.
2. **Upload template:** `gradescope/A_template.pdf`. (Blank form — never the key.)
3. **Build the outline:** add one question region per item; set point values from
   `A_outline.csv` (the `points` column).
4. **Enter the answer key / rubric:** enter the correct answer per question from
   `A_outline.csv` (the `answer` column); cross-check against `A_answer_key.pdf`.
   Add rubric items for partial credit.
5. **Scan and upload** the completed exams. Gradescope matches by Name/ID region.
6. **Grade**, then publish and sync to the LMS.

**Note:** Gradescope does not import the outline as a file — the outline/rubric is
built in-UI by drawing regions on the template and entering the key. The
`_outline.csv` is the crib that makes steps 3–4 fast and accurate. If Gradescope
adds a rubric import endpoint in the future, the CSV is already in the right shape.

---

## 3. A/B variants — Exam Version Set

Gradescope's [Multi-version Assignment](https://guides.gradescope.com/hc/en-us/articles/22253350665997-Creating-Multi-version-Assignments)
feature is designed exactly for this: each form has its own template and its own
answer key, so shuffled choices and different questions grade correctly under the
same assignment umbrella.

1. Create **two assignments**: *Exam 1 — Form A* and *Exam 1 — Form B*.
2. Upload `A_template.pdf` to Form A, `B_template.pdf` to Form B. Build each
   outline and answer key from its own `*_outline.csv`.
3. **Link the two assignments as a Version Set** in Gradescope so grade download,
   publish, regrade, and LMS sync are unified.
4. Upload **each form's scanned stack to its own version.** `build/register.csv`
   tells you which students received which form (e.g., 13 students on A, 13 on B).
   The footer serial on each paper confirms the form.

Because each version carries its own key, form A and form B can have entirely
different questions and answer orderings — the constraint of one shared key
disappears. The fact that the two `_outline.csv` files have different `answer`
columns is the mechanical anti-adjacency protection.

---

## 4. Per-student serials and identity verification

Every individualized copy prints a unique footer: `Serial <source> · ID <student>`.
This layer is orthogonal to Gradescope (Gradescope matches by Name/ID region) but
provides the forensic foundation for grade appeals:

**Confirm which form and which student a paper is:**

```bash
reg-exam-verify --register build/register.csv --dir build/
# → N checks, 0 mismatches
```

A swapped, forged, or misprinted paper will fail verification. To check a single
paper by name:

```bash
reg-exam-verify --student "Doe, Jane" --register build/register.csv
```

**Reproduce a student's exact paper for an appeal:**

```bash
reg-exam-build exam.build.yaml
```

The build is fully deterministic — same manifest, sources, roster, and
`assign_seed` always produce the same output. Pull the archived exam directory
from the term archive bundle, re-run, and the per-student PDF will match
what was printed, with matching footer IDs.

Full appeals procedure: [design/exam-tex-format.md — Grade-appeals reproduction runbook](design/exam-tex-format.md#grade-appeals-reproduction-runbook).

---

## 5. Roster

Gradescope matches submissions primarily by **email**, which lectern's roster CSV
does not carry. The emitted `gradescope_roster.csv` leaves the `Email` column blank.

**Recommended path:** sync the roster from the LMS via LTI/Canvas — it brings
current enrollment, emails, and matches Gradescope's preferred identifier.

**Fallback:** import `gradescope_roster.csv` (`First Name, Last Name, SID`) and
either fill the Email column manually or rely on SID matching. UTF-8 is preserved
for accented names.

### Getting totals back into lectern

Gradescope has no public API for instructors, and a Canvas token does not reach
it. The supported connection is Gradescope's Canvas tool (LTI 1.3), which many
campuses install for every course. Link the Gradescope course to its Canvas
course, then use **Post Grades to Canvas** on the assignment's *Review Grades*
page. That sends each student's total to the linked Canvas assignment, and
`reg-canvas grades-export` reads it like any other column
([canvas-api.md](canvas-api.md)).

> [!NOTE]
> Only totals cross over. Item analysis with `reg-gradescope-stats` still needs
> the per-question *Export Evaluations* download.

> [!WARNING]
> Pick one route per assignment. If Gradescope posts an exam's totals, do not
> also push that column with `reg-canvas grades-push`, or each will overwrite
> the other. A student's resubmission also removes their posted grade, so post
> again after the last resubmission or regrade.

---

## 6. Print and distribute

- Print the single `build/<exam-slug>_combined.pdf` (duplex-ready, even-page padded;
  every student's copy, all forms, in roster order) — one file, one print job. Hand
  out down the roster; each paper's visible form label + footer serial keep it
  self-identifying. *(Legacy `print_layout: per-form`: print `build/<form>_combined.pdf`
  per form and distribute alternating by seat.)*
- Distribute **alternating by seat** (A/B/A/B...) for adjacency separation.
- **Collect each form into its own pile** after the exam so each scans into its
  own Gradescope version. The footer serial distinguishes forms — if a paper ends
  up in the wrong stack, it will fail `reg-exam-verify` and can be re-sorted before
  scanning.

By default neither form shows a visible "Form A / Form B" label on the paper
itself — only the footer serial distinguishes them, so students cannot
seek out a same-form neighbor during the exam.

---

## Reference links

- [Gradescope: Multi-version Assignments](https://guides.gradescope.com/hc/en-us/articles/22253350665997-Creating-Multi-version-Assignments)
- [Gradescope: Bubble Sheets](https://guides.gradescope.com/hc/en-us/articles/22246010755853-Creating-a-Bubble-Sheet-Assignment)
- [Gradescope: AI-assisted grading](https://guides.gradescope.com/hc/en-us/articles/24838908062093-AI-assisted-grading-and-answer-groups)
- [Gradescope: Using LTI 1.3 with Canvas as an instructor](https://guides.gradescope.com/hc/en-us/articles/23586543164173-Using-Gradescope-LTI-1-3-with-Canvas-as-an-instructor)

---

## Common mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Uploading the key as the template | Gradescope AI region detection is corrupted | Upload the blank `<form>_template.pdf` |
| Grading both forms under one assignment | Wrong answers get credit on the cross-form key | Create separate assignments per form; link as a Version Set |
| Using `bubble` for a mixed MC/SA exam | Non-MC items are silently dropped from autograde | Use `region` for any exam with SA, FIB, or code questions |
| Relying on `gradescope_roster.csv` for email matching | Gradescope can't match by SID alone in all configurations | Prefer LMS/LTI roster sync; supplement the CSV with manual email entry if needed |
