# lectern — Documentation Index

## Design docs

| Document | Description |
|---|---|
| [design/exam-system.md](design/exam-system.md) | Multi-form exam system: A/B variants, individualized per-student builds, Gradescope products, defensibility and grade-appeal reproducibility |
| [design/exam-tex-format.md](design/exam-tex-format.md) | House exam `.tex` format: header block doctrine, answer key toggle, color conventions, per-student serials, backward-compat preamble patch, grade-appeals runbook |

## Workflow docs

| Document | Description |
|---|---|
| [gradescope-workflow.md](gradescope-workflow.md) | Step-by-step for taking a lectern-built exam into Gradescope: region/bubble setup, A/B Version Sets, roster import, per-student serial identity verification |

## Quick pointers

- **Exam build reference skeleton:** `references/reference_exam.tex` — copy, rename, author, then build with `reg-exam-build`.
- **Worked example:** `examples/cecs-378-demo/` — one complete semester, including roster import, gradebook, A/B exam build, ISA publish, and term archive.
- **Command reference:** see the `reg-*` table in `README.md`.
