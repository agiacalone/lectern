# reg-lab-recon — Layer 2 report synthesis

> **Superseded (see `docs/design/lab-report.md`).** The canonical instructor `REPORT.md`
> is now produced deterministically by **`reg-lab-report render`** (lectern Layer 3),
> which consumes the recon bundle + the digest-merged cohort. This agent-driven
> synthesis workflow is retained for ad-hoc/exploratory narrative passes, but the
> reproducible report is the tool. Feedback delivery to students is `reg-lab-report deliver`.

Layer 1 (`reg-lab-recon`) produces a deterministic **facts bundle**. Layer 2 turns it into the
dual-purpose `REPORT.md` via subagent fan-out. No new Python — this is a Claude workflow.

## 1. Run Layer 1
```
reg-lab-recon --manifest <lab>.recon.yaml --roster github-usernames.csv --out recon/<lab>/
```
Produces `recon/<lab>/`: `repos/<id>.json`, `cohort.csv`, `FACTS.md`, `bundle.json`.

## 2. Fan-out (one subagent per repos/*.json)
Each subagent reads a student's record + its `docs[].raw_path` WRITEUP and returns advisory only:
`{github_id, writeup_score_draft (/30), writeup_rationale, how_it_went, notable[]}`.
Rubric for the grimoire read: per-ward technical depth, ≥1 source per ward, clarity ("how the ward
fell, not that it did").

## 3. Synthesize
Roll per-repo records + `cohort.csv` into `templates/recon-report.md` → `recon/<lab>/REPORT.md`:
- **Aggregate narrative** — completion distribution + most-failed challenge, computed from `cohort.csv` (facts).
- **➊ Grade table** — `Auto` = facts; `Writeup (advisory)` + `Proposed` = advisory, await confirm.
- **➋ Investigation queue** — every FLAG/REVIEW + all-failed/honor-gate, each with reproduce command
  and the feedback-PR link.
- **Appendix** — per student: autograde · commit story · doc digest · links.

## 4. Honesty firewall
Facts (CI conclusions, commit counts, hashes) and advisory (writeup reads, narrative, triage score)
stay visibly separated. A FLAG is a prompt to look, never a verdict.

## 5. Apply or investigate
- ➊ confirm the grade table → feed `reg-gradebook` (component file).
- ➋ open the feedback PR per flagged repo to read/leave inline comments.

## 6. Per-student feedback — scaffold → LLM fill → deliver (standard practice)
`reg-lab-report render` always emits a **`## Per-student feedback & grades`** section, so
`REPORT.md` is a complete "report + feedback" document. Each student block is a **grading
scaffold**, not just a record:

- **Graded** (cohort row has a `student_comment`) → renders the grade + the verbatim
  student-facing comment as a block quote, plus a stripped `<!-- internal -->` note.
- **Ungraded submission** (writeup present, no comment yet) → renders a `> _Comments:_`
  **placeholder** with a `__` grade. This is the hand-off point.
- **Non-submission** → `> _no submission_`, nothing to grade.

**The comment prose is filled by LLM agentic grading, never scripted.** Lectern deliberately
does not generate feedback text — it scaffolds the placeholders and the `reg-lab-digest`
fan-out (one agent per writeup, contract in [`lab-digest-grader-prompt.md`](lab-digest-grader-prompt.md))
fills each `student_comment` against the rubric. `merge` writes those comments back into
`cohort.csv`, and the next `render` promotes each placeholder to a filled block.

Delivery is note-authoritative and placeholder-safe: `reg-lab-report deliver --from-note REPORT.md`
(or `--cohort cohort.csv`) ships each student's block quote verbatim to their `FEEDBACK.md` and
**skips any block still holding the `_Comments:_` placeholder** — so an unfinished grading pass
never ships blanks. Full close-out sequence: the grading-close-out runbook.
