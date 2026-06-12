---
title: "Authenticity Review — CECS 326 §99, Lab 02 — Semaphores"
subtitle: "Student: Harley Quinn"
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
| Repository | `cecs-326-sp26-99-lab-02-semaphores-harley-quinn` (org `Giacalone-CECS`) |
| Repo HEAD examined | `dc68723` |
| Grading commit (deliverables) | `dc68723` |
| Examined by | Anthony Giacalone, 2026-06-12 |
| Tooling (Part B only) | `assignment-triage` @ `PINNED`; engine `grader.py` |
| Profile | short-project (signal weights declared in A.5) |
| Course / Section | CECS 326 §99 — Lab 02 — Semaphores |
| Student | Harley Quinn (`harley-quinn`) |


## A.2 Commit ledger (verbatim `git log`)

Author `harley-quinn`. `[bot]` rows are GitHub Classroom scaffolding (excluded from the Part B screen). Times ISO-8601 author date. Messages trimmed to one line for layout.

```
dc68723    2026-05-16T03:00             harley-quinn          add solution
```

## A.3 Published requirement and deliverable facts

**Deliverable: makefile** (match pattern: `makefile`, required: True, auto-zero: True)

- Present at grading ref: **Yes**
- Matched paths: `Makefile`
- First added commit: `dc68723` 2026-05-16T03:00:00-07:00
- Auto-zero status: Does not trigger

## A.4 Reproduce Part A

### makefile

```
# Presence at grading ref:
cd <repo> && git ls-tree -r --name-only dc6872395318243897d5d491447113722dd9c437 | grep -iE '(^|/)makefile$'

# First added commit:
cd <repo> && git log --reverse --diff-filter=A --format='%h%x09%aI' --name-only | grep -iE '(^|/)makefile$'
```

## A.5 Screen configuration (for reproducibility of Part B)

Thresholds: score >= 60, score <= 20. Weights: (defaults). Schema version: 1. Engine SHA: `PINNED`.

---

# Part B — Advisory triage signal (heuristic; not proof, not a grade input)

`assignment-triage` is a screening heuristic. By its own design it is "100% triage — a flag is a prompt to look, not a verdict — no student is penalized without human review." It awards points for behavioral signals that are characteristic of (but not unique to) genuine human development. The thresholds and weights are hand-set starting points, not statistically calibrated, and the tool publishes no error rate. A score is therefore advisory only and is **not proof** of anything on its own. It is sound to use it to corroborate that there is no integrity concern; it would not be sound to treat any score as proof or to base an adverse finding on it without independent human review.

Running the screen across the repository's commit history produced the following result for **Harley Quinn** (`harley-quinn`):

- **Score:** 0
- **Bucket:** flag bucket (score 0 <= 20)
- **Reasoning:** MISSING: only 1 commits (expected ~5) | MISSING: all work within 1 day(s) (need 3) | MISSING: assignment dates not provided (started_early skipped) | MISSING: uniform commit intervals (CV=0.00) | MISSING: few/no deletions (0% of insertions) | MISSING: no files revised across multiple sessions | MISSING: single commit contains 100% of all insertions

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