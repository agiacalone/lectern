---
title: "Authenticity Review — CECS 326 §99, Lab 02 — Semaphores"
subtitle: "Student: Barbara Gordon"
author: "Anthony Giacalone · Lecturer, Computer Engineering & Computer Science, CSULB"
date: "2026-06-12"
---

> **Synthetic example — fictional students, fabricated repositories; not a real authenticity review.**

**How to read this document.** It is in two tiers, and they do not carry equal
weight:

> **Part A — Verified record (audit-grade).** Immutable git facts, pinned by commit
> hash and independently reproducible. These are facts, not inferences.
>
> **Part B — Advisory triage signal (heuristic; not proof).** A screening score that
> prioritizes work for human review. It is not evidence of anything on its own and is
> not the basis for any grade or finding.

**Bottom line.** The verified record (Part A) contains the git facts that withstand
audit. The advisory screen (Part B) is a heuristic signal bounded by the limitations
in Part C. Nothing in Part B is used adversely against the student without independent
human review.

---

# Part A — Verified record (audit-grade, independently reproducible)

Every fact below is derivable by a third party with repository access by running the
commands in A.4 against the pinned commit. No interpretation is required to confirm them.


## A.1 Provenance (pins exactly what was examined)

| Field | Value |
|---|---|
| Repository | `cecs-326-sp26-99-lab-02-semaphores-barbara-gordon` (org `Giacalone-CECS`) |
| Repo HEAD examined | `d46f5a0` |
| Grading commit (deliverables) | `89c43df` |
| Examined by | Anthony Giacalone, 2026-06-12 |
| Tooling (Part B only) | `assignment-triage` @ `PINNED`; engine `grader.py` |
| Profile | short-project (signal weights declared in A.5) |
| Course / Section | CECS 326 §99 — Lab 02 — Semaphores |
| Student | Barbara Gordon (`barbara-gordon`) |


## A.2 Commit ledger (verbatim `git log`)

Author `barbara-gordon`. `[bot]` rows are GitHub Classroom scaffolding (excluded from the Part B screen). Times ISO-8601 author date. Messages trimmed to one line for layout.

```
209348c    2026-05-06T19:42             barbara-gordon        initial skeleton
0e1efcc    2026-05-07T22:13             barbara-gordon        stub out barbarian thread
b7bb0fb    2026-05-09T16:05             barbara-gordon        add wizard and rogue stubs
f1ae61f    2026-05-10T23:51             barbara-gordon        implement semaphore waits in barbarian and wizard
49f5111    2026-05-12T11:27             barbara-gordon        fix deadlock: revert nested-lock attempt in barbarian
52d03e7    2026-05-13T20:08             barbara-gordon        wire up rogue and add Makefile
89c43df    2026-05-14T18:33             barbara-gordon        debug: initialize mutex semaphore in main
d46f5a0    2026-05-15T21:19             barbara-gordon        add README with build instructions
```

## A.3 Published requirement and deliverable facts

**Deliverable: makefile** (match pattern: `makefile`, required: True, auto-zero: True)

- Present at grading ref: **Yes**
- Matched paths: `Makefile`
- First added commit: `52d03e7` 2026-05-13T20:08:00-07:00
- Auto-zero status: Does not trigger

## A.4 Reproduce Part A

### makefile

```
# Presence at grading ref:
cd <repo> && git ls-tree -r --name-only 89c43df0e5b9229ad048ed85d1f5f0f5a76fc5f4 | grep -iE '(^|/)makefile$'

# First added commit:
cd <repo> && git log --reverse --diff-filter=A --format='%h%x09%aI' --name-only | grep -iE '(^|/)makefile$'
```

## A.5 Screen configuration (for reproducibility of Part B)

Thresholds: score >= 60, score <= 20. Weights: (defaults). Schema version: 1. Engine SHA: `PINNED`.

---

# Part B — Advisory triage signal (heuristic; not proof, not a grade input)

`assignment-triage` is a screening heuristic. By its own design it is "100% triage — a flag is a prompt to look, not a verdict — no student is penalized without human review." It awards points for behavioral signals that are characteristic of (but not unique to) genuine human development. The thresholds and weights are hand-set starting points, not statistically calibrated, and the tool publishes no error rate. A score is therefore advisory only and is **not proof** of anything on its own. It is sound to use it to corroborate that there is no integrity concern; it would not be sound to treat any score as proof or to base an adverse finding on it without independent human review.

Running the screen across the repository's commit history produced the following result for **Barbara Gordon** (`barbara-gordon`):

- **Score:** 90
- **Bucket:** clear pass (score 90 >= 60)
- **Reasoning:** 8 commits (expected ~5) | work spread across 8 days | started before final stretch of deadline | deletions present (17% of insertions) | 2 file(s) revised across multiple sessions | no single-commit dump (largest commit: 31% of insertions) | MISSING: uniform commit intervals (CV=0.21)

These are advisory signals only. See Part C for limitations.

---

# Part C — Limitations and responsible use

- **Heuristic, not validated.** Weights and thresholds are hand-calibrated starting points with no published false-positive / false-negative rate. The score is a prioritization aid, never proof.
- **Triage, not verdict.** Used here only to clear a concern (the safe error direction). It must never be the sole basis for an adverse academic-integrity finding; that requires independent human review.
- **Two commit views, one report.** The advisory screen (Part B) considers the full commit history, including any commits after the deadline; the verified record (Part A) pins deliverable facts to the grading commit. Post-deadline commits can only raise an advisory score, never lower it.
- **Commit timestamps are self-reported.** Git author and committer dates are set client-side and are, in principle, forgeable. For contested timelines, GitHub server-side push/event timestamps are the stronger source and are the recommended hardening step.
- **Instructor context is not modeled.** The tool has no knowledge of a student's prior work or caliber; the instructor supplies that judgment.
- **Versioning.** Report schema v1; signal set v1; advisory signal set per the pinned engine SHA `PINNED`. Future signal sets append; each report pins the engine and configuration so results remain reproducible and interpretable as the methodology evolves.

*Prepared by Anthony Giacalone (instructor) on 2026-06-12. Part A is independently verifiable from the repository; Part B is advisory and bounded as described in Part C.*