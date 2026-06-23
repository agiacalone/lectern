# lectern — Documentation Index

## Design docs

| Document | Description |
|---|---|
| [design/exam-system.md](design/exam-system.md) | Multi-form exam system: A/B variants, individualized per-student builds, Gradescope products, defensibility and grade-appeal reproducibility |
| [design/exam-tex-format.md](design/exam-tex-format.md) | House exam `.tex` format: header block doctrine, answer key toggle, color conventions, per-student serials, backward-compat preamble patch, grade-appeals runbook |
| [design/lab-digest.md](design/lab-digest.md) | Layer-2 writeup digest: rubric schema, the LLM grading contract, deterministic merge with guardrails (partial-credit warding, total recompute) |
| [design/lab-report.md](design/lab-report.md) | Layer-3 instructor report + feedback delivery: deterministic report rendering, agate charts, grading recommendations, signed feedback-branch delivery |
| [design/lms-suite-integration.md](design/lms-suite-integration.md) | LMS suite (Lectern · Scriptorium · Oracle) integration: seam contracts (reading-list, autograde, question-bank), the release compatibility matrix, cross-component testing |

## Workflow docs

| Document | Description |
|---|---|
| [gradescope-workflow.md](gradescope-workflow.md) | Step-by-step for taking a lectern-built exam into Gradescope: region/bubble setup, A/B Version Sets, roster import, per-student serial identity verification |

## Quick pointers

- **Exam build reference skeleton:** `references/reference_exam.tex` — copy, rename, author, then build with `reg-exam-build`.
- **Worked example:** `examples/cecs-378-demo/` — one complete semester, including roster import, gradebook, A/B exam build, ISA publish, and term archive.
- **Command reference:** see the `reg-*` table in `README.md`.
