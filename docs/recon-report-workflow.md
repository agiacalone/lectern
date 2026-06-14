# reg-lab-recon — Layer 2 report synthesis

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
