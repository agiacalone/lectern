"""Authenticity signal registry. Each signal is a named callable returning a
SignalResult. Profiles (in references/triage_profiles.yaml) weight them.

Negative-scoring model preserved from assignment-triage/grader.py: score starts
at 0 and rises as evidence of genuine human development accumulates.
"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import mean, stdev
from typing import Any


@dataclass
class SignalResult:
    points: int
    evidence: str          # plain-English, audit-friendly
    present: bool          # did the authentic signal fire?


# name -> (fn, default_weight, profiles)  ; profiles == "all" or a set of names
SIGNALS: dict[str, tuple] = {}


def signal(*, name: str, default_weight: int, profiles="all"):
    def deco(fn):
        SIGNALS[name] = (fn, default_weight, profiles)
        return fn
    return deco


# ---------------------------------------------------------------------------
# Git helpers (ported verbatim from assignment-triage/grader.py)
# ---------------------------------------------------------------------------

def _git(repo: Path, *args) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo)] + list(args),
        capture_output=True, text=True
    )
    return result.stdout.strip()


# Exclude bot commits (github-classroom[bot], github-actions[bot], etc.)
_STUDENT_FILTER = ("--perl-regexp", r"--author=^((?!\[bot\]).)*$")


def _is_bot(author: str) -> bool:
    """True if the author name matches the bot pattern (contains '[bot]')."""
    return "[bot]" in author


def _git_log(repo: Path, *args) -> str:
    """git log restricted to student commits — bots excluded."""
    return _git(repo, "log", *_STUDENT_FILTER, *args)


def _commit_dates(repo: Path) -> list[datetime]:
    out = _git_log(repo, "--format=%ct")
    if not out:
        return []
    return [datetime.fromtimestamp(int(ts), tz=timezone.utc) for ts in out.splitlines()]


def _spread_days(dates: list[datetime]) -> int:
    return len(set(d.date() for d in dates))


def _interval_cv(dates: list[datetime]) -> float:
    """Coefficient of variation of inter-commit intervals. High = irregular (natural)."""
    if len(dates) < 3:
        return 0.0
    intervals = [abs((dates[i] - dates[i + 1]).total_seconds()) for i in range(len(dates) - 1)]
    intervals = [x for x in intervals if x > 0]
    if len(intervals) < 2 or mean(intervals) == 0:
        return 0.0
    return stdev(intervals) / mean(intervals)


def _deletion_ratio(repo: Path) -> float:
    out = _git_log(repo, "--shortstat", "--format=")
    total_ins = total_del = 0
    for line in out.splitlines():
        if m := re.search(r'(\d+) insertion', line):
            total_ins += int(m.group(1))
        if m := re.search(r'(\d+) deletion', line):
            total_del += int(m.group(1))
    return (total_del / total_ins) if total_ins else 0.0


def _max_ins_ratio(repo: Path) -> float:
    """Fraction of total insertions that landed in the single largest commit."""
    out = _git_log(repo, "--shortstat", "--format=%H")
    commit_ins = []
    current = 0
    for line in out.splitlines():
        line = line.strip()
        if not line:
            commit_ins.append(current)
            current = 0
        elif m := re.search(r'(\d+) insertion', line):
            current = int(m.group(1))
    if current:
        commit_ins.append(current)
    total = sum(commit_ins)
    return (max(commit_ins) / total) if total and commit_ins else 0.0


def _session_churn(repo: Path, session_gap_hours: int = 4) -> int:
    """Count files modified in 3+ distinct sessions."""
    out = _git_log(repo, "--format=%ct", "--name-only")
    file_times: dict[str, list[int]] = {}
    current_ts = None
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.isdigit():
            current_ts = int(line)
        elif current_ts is not None:
            file_times.setdefault(line, []).append(current_ts)

    count = 0
    for timestamps in file_times.values():
        if len(timestamps) < 3:
            continue
        timestamps.sort()
        sessions = 1
        for i in range(1, len(timestamps)):
            if (timestamps[i] - timestamps[i - 1]) > session_gap_hours * 3600:
                sessions += 1
        if sessions >= 3:
            count += 1
    return count


def _started_early(dates: list[datetime], assigned_date: datetime, due_date: datetime) -> bool:
    """True if any commit happened before the last 20% of the assignment window."""
    if not dates:
        return False
    window = (due_date - assigned_date).total_seconds()
    threshold = assigned_date.timestamp() + window * 0.80
    return any(d.timestamp() < threshold for d in dates)


def _cleanups(repo: Path, window_hours: int = 24, deletion_ratio_threshold: float = 3.0) -> int:
    """Count commits that look like LLM cleanup: deletion-heavy commit occurring
    within window_hours after a large insertion commit.

    Pattern: student pastes generated code (big insertion), then quickly removes
    comments, dead code, or formatting artifacts (big deletion, few insertions).
    """
    out = _git_log(repo, "--shortstat", "--format=%ct")
    if not out:
        return 0

    # Build list of (timestamp, insertions, deletions) per commit
    commits = []
    current_ts = None
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.isdigit():
            current_ts = int(line)
        else:
            ins = int(m.group(1)) if (m := re.search(r'(\d+) insertion', line)) else 0
            dels = int(m.group(1)) if (m := re.search(r'(\d+) deletion', line)) else 0
            if current_ts is not None:
                commits.append((current_ts, ins, dels))
                current_ts = None

    count = 0
    for i, (ts, ins, dels) in enumerate(commits):
        # Deletion-heavy commit (far more deletions than insertions)
        if ins == 0 or dels / max(ins, 1) < deletion_ratio_threshold:
            continue
        # Check if a large insertion commit preceded it within the window
        for j in range(i + 1, len(commits)):
            prev_ts, prev_ins, _ = commits[j]
            if (ts - prev_ts) > window_hours * 3600:
                break
            if prev_ins > 50:  # meaningful insertion threshold
                count += 1
                break

    return count


# ---------------------------------------------------------------------------
# RepoFacts — run all extractors once; signal functions receive this object
# ---------------------------------------------------------------------------

@dataclass
class LedgerEntry:
    sha: str
    iso: str
    author: str
    subject: str
    is_bot: bool


def _build_ledger(repo: Path) -> list[LedgerEntry]:
    """Return every commit (including bots) as an ordered audit record."""
    out = _git(repo, "log", "--reverse", "--format=%h\t%aI\t%an\t%s")
    if not out:
        return []
    entries = []
    for line in out.splitlines():
        parts = line.split("\t", 3)
        if len(parts) < 4:
            continue
        sha, iso, author, subject = parts
        entries.append(LedgerEntry(
            sha=sha,
            iso=iso,
            author=author,
            subject=subject,
            is_bot=_is_bot(author),
        ))
    return entries


@dataclass
class RepoFacts:
    path: Path
    dates: list[datetime]
    del_ratio: float
    dump_pct: float
    churn: int
    cleanups: int
    ledger: list

    @classmethod
    def from_repo(cls, path: Any) -> "RepoFacts":
        path = Path(path)
        dates = _commit_dates(path)
        return cls(
            path=path,
            dates=dates,
            del_ratio=_deletion_ratio(path),
            dump_pct=_max_ins_ratio(path),
            churn=_session_churn(path),
            cleanups=_cleanups(path),
            ledger=_build_ledger(path),
        )


# ---------------------------------------------------------------------------
# Signals (ported from assignment-triage/grader.py score_repo blocks)
# ---------------------------------------------------------------------------

@signal(name="commit_count", default_weight=15, profiles="all")
def commit_count_signal(facts: RepoFacts, cfg: dict) -> SignalResult:
    w = cfg.get("weights", {}).get("commit_count", 15)
    expected = cfg.get("assignment", {}).get("expected_commits", 5)
    count = len(facts.dates)
    if count >= max(expected * 0.5, 2):
        return SignalResult(w, f"{count} commits (expected ~{expected})", True)
    return SignalResult(0, f"only {count} commits (expected ~{expected})", False)


@signal(name="spread_days", default_weight=20, profiles="all")
def spread_days_signal(facts: RepoFacts, cfg: dict) -> SignalResult:
    days = _spread_days(facts.dates)
    need = cfg.get("thresholds", {}).get("min_spread_days", 3)
    w = cfg.get("weights", {}).get("spread_days", 20)
    if days >= need:
        return SignalResult(w, f"work spread across {days} days", True)
    return SignalResult(0, f"all work within {days} day(s) (need {need})", False)


@signal(name="started_early", default_weight=15, profiles="all")
def started_early_signal(facts: RepoFacts, cfg: dict) -> SignalResult:
    w = cfg.get("weights", {}).get("started_early", 15)
    assignment = cfg.get("assignment", {})
    assigned_str = assignment.get("assigned_date")
    due_str = assignment.get("due_date")
    if not assigned_str or not due_str:
        # Cannot evaluate without assignment dates — signal absent
        return SignalResult(0, "assignment dates not provided (started_early skipped)", False)
    assigned = datetime.fromisoformat(assigned_str).replace(tzinfo=timezone.utc)
    due = datetime.fromisoformat(due_str).replace(tzinfo=timezone.utc)
    if _started_early(facts.dates, assigned, due):
        return SignalResult(w, "started before final stretch of deadline", True)
    return SignalResult(0, "no commits before final 20% of assignment window", False)


@signal(name="interval_cv", default_weight=10, profiles="all")
def interval_cv_signal(facts: RepoFacts, cfg: dict) -> SignalResult:
    w = cfg.get("weights", {}).get("interval_cv", 10)
    cv = _interval_cv(facts.dates)
    if cv > 0.5:
        return SignalResult(w, f"irregular commit intervals (CV={cv:.2f})", True)
    return SignalResult(0, f"uniform commit intervals (CV={cv:.2f})", False)


@signal(name="deletions", default_weight=15, profiles="all")
def deletions_signal(facts: RepoFacts, cfg: dict) -> SignalResult:
    w = cfg.get("weights", {}).get("deletions", 15)
    if facts.del_ratio > 0.05:
        return SignalResult(w, f"deletions present ({facts.del_ratio:.0%} of insertions)", True)
    return SignalResult(0, f"few/no deletions ({facts.del_ratio:.0%} of insertions)", False)


@signal(name="file_churn", default_weight=10, profiles="all")
def file_churn_signal(facts: RepoFacts, cfg: dict) -> SignalResult:
    w = cfg.get("weights", {}).get("file_churn", 10)
    if facts.churn >= 1:
        return SignalResult(w, f"{facts.churn} file(s) revised across multiple sessions", True)
    return SignalResult(0, "no files revised across multiple sessions", False)


@signal(name="no_dump", default_weight=15, profiles="all")
def no_dump_signal(facts: RepoFacts, cfg: dict) -> SignalResult:
    w = cfg.get("weights", {}).get("no_dump", 15)
    dump = facts.dump_pct
    if dump < 0.70:
        return SignalResult(w, f"no single-commit dump (largest commit: {dump:.0%} of insertions)", True)
    return SignalResult(0, f"single commit contains {dump:.0%} of all insertions", False)


@signal(name="crunch", default_weight=10, profiles={"term-project"})
def crunch_signal(facts: RepoFacts, cfg: dict) -> SignalResult:
    """ADVISORY: rewards effort SUSTAINED across the assignment window vs compressed
    near the deadline. Term-project only. Rushing is not misconduct — this is a
    screening signal, never a Part A fact."""
    w = cfg.get("weights", {}).get("crunch", 10)
    assignment = cfg.get("assignment", {})
    assigned_str = assignment.get("assigned_date")
    due_str = assignment.get("due_date")
    if not assigned_str or not due_str:
        return SignalResult(0, "assignment dates not provided (crunch skipped)", False)
    if not facts.dates:
        return SignalResult(0, "no commits found (crunch skipped)", False)
    assigned = datetime.fromisoformat(assigned_str).replace(tzinfo=timezone.utc)
    due = datetime.fromisoformat(due_str).replace(tzinfo=timezone.utc)
    window = (due - assigned).total_seconds()
    if window <= 0:
        return SignalResult(0, "degenerate assignment window (crunch skipped)", False)
    boundary = assigned + timedelta(seconds=window * 0.80)
    # Normalize boundary to UTC timestamp for comparison
    boundary_ts = boundary.timestamp()
    total = len(facts.dates)
    in_last_fifth = sum(1 for d in facts.dates if d.timestamp() >= boundary_ts)
    last_fifth = in_last_fifth / total
    if last_fifth < 0.6:
        return SignalResult(
            w,
            f"effort sustained across the window ({last_fifth:.0%} of commits in final 20%)",
            True,
        )
    return SignalResult(
        0,
        f"effort compressed near deadline ({last_fifth:.0%} of commits in final 20%)",
        False,
    )


@signal(name="cleanup_commits", default_weight=0, profiles="all")
def cleanup_commits_signal(facts: RepoFacts, cfg: dict) -> SignalResult:
    w = cfg.get("weights", {}).get("cleanup_commits", 0)
    if w > 0:
        if facts.cleanups == 0:
            return SignalResult(w, "no cleanup-after-paste commits detected", True)
        return SignalResult(
            0,
            f"{facts.cleanups} cleanup commit(s) detected (deletion-heavy commit after large insertion)",
            False,
        )
    # Weight is 0 — registered but not scoring
    return SignalResult(0, f"cleanup_commits weight=0 (not scoring); {facts.cleanups} detected", False)
