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
