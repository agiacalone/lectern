# Pushing Vault Grades to Canvas

How to move grades from the vault (the source of truth) into Canvas for a single
assignment — a lab or an exam — without disturbing anything else in the Canvas
gradebook.

The vault is the grade source of truth; grades flow **vault → Canvas**. The clean
way to do that is a *template overlay*: you export the Canvas gradebook, lay the
vault's computed scores onto that exact file, and re-import it. Because the import
file is the export with only your changed cells touched, Canvas updates the
existing assignment and leaves everything else alone.

Companion: [design/lab-report.md](design/lab-report.md) (feedback delivery, the
GitHub side of the same grading round). Canvas's own import rules:
<https://community.instructure.com/en/kb/articles/660862-how-do-i-import-grades-in-the-gradebook>.

---

## TL;DR

```sh
# 1. In Canvas: Grades → Export → "Export Current Gradebook" → save the CSV.
# 2. Overlay the vault's scores for one component onto that export:
reg-gradebook export-canvas \
    --gradebook gradebook.csv \
    --course CECS_378 \                     # resolves the schema (or pass --schema)
    --template <the-canvas-export>.csv \
    --only lab2 \                           # the component short_name to push
    --out canvas-<lab2>-import.csv
# 3. In Canvas: Grades → Import → upload canvas-<lab2>-import.csv → review → save.
```

Step 2 changes only the cells whose value actually moved. Everything else — the
identity columns, the other assignment columns, the points/posting row — is passed
through byte-for-byte.

---

## Why a template overlay (and not a bare CSV)

Canvas matches an imported column to an existing assignment by its **id-suffixed
header**, e.g. `Lab 2 - Malicious Software (1767131)`. A bare `SIS User ID, Lab 2`
file (no id) risks creating a *new* manual assignment instead of updating the real
one. Only the Canvas export carries those ids, the student identity columns
(`Student, ID, SIS User ID, SIS Login ID, Section`), and the posting row — so the
export is the only faithful template. `export-canvas --template` overlays onto it:

- **Assignment match** — each export column header is matched to a schema
  component by stripping the ` (id)` suffix and looking up its `canvas_title`.
  `--only <short_name…>` restricts the overlay to specific components (the usual
  case: push one lab or one exam); omit it to overlay every graded component.
- **Student match** — by `SIS User ID` (zero-padded), against `gradebook.csv`.
  A student in the export but not in the gradebook (a Canvas "Test Student", a
  late add) is passed through untouched.
- **Minimal diff** — a cell is rewritten only when its value actually changed;
  numerically-equal cells keep the export's original text. The import therefore
  touches just the grades that moved, which is easy to eyeball before you upload.
- **Read-only columns** — the export's computed columns (`Current Score`,
  `Final Grade`, `Override …`) ride along unchanged; Canvas ignores them on import.

## Extra credit

Extra credit is already folded into the component score in the vault, because the
per-component score file feeds it in (e.g. a lab's `score` column = base + ACE).
So the overlay carries EC automatically — a Lab 2 base of 96 with +14 ACE lands in
Canvas as `110`. Canvas accepts scores above the assignment's points-possible, so
this is the natural single-column home for built-in extra credit. (If you keep a
*separate* Canvas EC assignment instead, push base-only by building the gradebook
from base scores, or add the EC as its own component.)

## Bare-CSV mode (no template)

Without `--template`, `export-canvas` emits the minimal `SIS User ID` + one column
per graded component (header = bare `canvas_title`, no id). This is fine for a
brand-new assignment you want Canvas to create, or a quick spot-check, but for
updating existing assignments prefer the template overlay above.

## Worked example — CECS 378 Lab 2 (Su26 §01)

Lab 2 base grades were already in Canvas; only the Task-2 ACE extra credit needed
to land. Exporting Canvas, then:

```sh
reg-gradebook export-canvas --gradebook gradebook.csv --course CECS_378 \
    --template 2026-06-28_Grades-CECS_378_Sec01.csv --only lab2 \
    --out canvas-lab2-import.csv
```

produced an import identical to the export except six cells — the six students who
earned ACE (Badberg 82→91, Bavouset 91→106, Cuevas 92→97, C. Schulte 96→110,
D. Schulte 92→104, Silaiev 71→75). Re-importing applied exactly those six changes.
