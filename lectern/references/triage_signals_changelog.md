# Triage Signals Changelog

## v1
Initial signal set (8 signals):
- `commit_count` — detects suspiciously low commit velocity
- `spread_days` — measures work distribution across calendar days
- `started_early` — flags repo created before assignment release
- `interval_cv` — coefficient of variation on commit intervals
- `deletions` — penalizes repos with no deletions (suspicious wholesale rewrites)
- `file_churn` — tracks file-level churn (add/remove/modify)
- `no_dump` — detects repos with no bulk data/config dumps
- `cleanup_commits` — detects deletion-heavy commits that follow a large-insertion commit within 24 h (the paste-then-cleanup pattern)

See `lectern/triage_signals.py` for implementation and threshold logic.

## v2
- Added `crunch` (term-project only, advisory): rewards effort sustained across the assignment window vs deadline compression. Signal fires when fewer than 60% of commits fall in the final 20% of the assignment window. Rushing is not misconduct — evidence wording is neutral ("sustained"/"compressed"). Does not score in single-sitting or short-project profiles.

## Report schema v2: guard files (not a signal)
Added guard-file integrity as a **Part A fact**, reported and never scored. The
signal set is unchanged at v2: `guardfile_forensics` does not register in
`SIGNALS`, awards no points, and cannot move a bucket. Editing or deleting an
instructor-authored file (`AGENTS.md` by default) is a visible, deliberate act
with innocuous explanations as well as concerning ones, so it is surfaced with
the commit and a reproduce command, for a human to read.

Structure changes that force the schema bump:
- `results.csv` gains a `guard` column; `TRIAGE.md` gains a Guard column and a
  "Guard files" roll-up.
- The per-student report gains section **A.6 Guard-file integrity**.
- The recon bundle's `cohort.csv` gains a `guard` column and `FACTS.md` a
  "Guard files" section.
- Manifests gain `guard_files:`, defaulting to `["AGENTS.md"]`. An entry may be
  `{path, sha256}` to compare against the file **as distributed**, which catches
  an edit made inside a squashed initial commit.
