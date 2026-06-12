"""Cross-assignment commit-rhythm screening — v1.

A student's commit-time-of-day pattern tends to be personal; a large shift in
that pattern between assignments is worth a HUMAN look (could indicate different
authorship), but is NEVER proof — schedules legitimately change.  The output is
an ADVISORY note in the spirit of Part B.
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lectern.triage_signals import RepoFacts


# ---------------------------------------------------------------------------
# Fingerprint: 24-bucket hour histogram, L1-normalized
# ---------------------------------------------------------------------------

def commit_fingerprint(facts: "RepoFacts") -> list[float]:
    """Return a 24-element list representing the hourly commit distribution.

    Each bucket is the fraction of commits whose author hour equals that index
    (0 = midnight, 9 = 9 AM, …).  The list sums to 1.0 when there are commits;
    all-zero when the repo has no commits.

    Uses the raw ISO author date from the ledger (with its original UTC offset),
    so the hour reflects the student's local working hour rather than UTC.
    Bot commits (github-classroom[bot] etc.) are excluded from the fingerprint
    so they don't distort the student's personal rhythm.
    """
    buckets = [0] * 24
    for entry in facts.ledger:
        if entry.is_bot:
            continue
        local_hour = datetime.fromisoformat(entry.iso).hour
        buckets[local_hour] += 1
    total = sum(buckets)
    if total == 0:
        return [0.0] * 24
    return [b / total for b in buckets]


# ---------------------------------------------------------------------------
# Divergence: max pairwise total-variation distance
# ---------------------------------------------------------------------------

def rhythm_divergence(fingerprints: list[list[float]]) -> float:
    """Return the maximum pairwise total-variation distance over all pairs.

    TV(p, q) = 0.5 * sum(|p_i - q_i|).

    Returns 0.0 for 0 or 1 fingerprint (nothing to compare).
    All-zero fingerprints (no commits) yield tv=0 against each other — safe.
    """
    if len(fingerprints) < 2:
        return 0.0
    max_tv = 0.0
    for i in range(len(fingerprints)):
        for j in range(i + 1, len(fingerprints)):
            p, q = fingerprints[i], fingerprints[j]
            tv = 0.5 * sum(abs(pi - qi) for pi, qi in zip(p, q))
            if tv > max_tv:
                max_tv = tv
    return max_tv


# ---------------------------------------------------------------------------
# Report rendering
# ---------------------------------------------------------------------------

def _dominant_hours(fp: list[float], top_n: int = 2) -> str:
    """Return a short string naming the top 1-2 commit hours."""
    indexed = sorted(enumerate(fp), key=lambda x: -x[1])
    candidates = [(h, v) for h, v in indexed if v > 0][:top_n]
    if not candidates:
        return "no commits"
    return ", ".join(f"{h:02d}:xx" for h, _ in candidates)


def _band(divergence: float) -> str:
    if divergence < 0.4:
        return "consistent personal rhythm across assignments"
    elif divergence <= 0.7:
        return "some shift in working pattern"
    else:
        return "notable shift in working pattern — worth a human look"


def render_rhythm_report(
    student: str,
    repo_labels: list[str],
    fingerprints: list[list[float]],
    divergence: float,
) -> str:
    """Return a Markdown advisory note.

    Always contains the words "advisory" and "not proof".
    """
    lines = [
        f"# Commit-Rhythm Advisory — {student}",
        "",
        "> **Advisory note:** This document is a screening aid, not proof of any"
        " misconduct. A shift in commit-time pattern is never proof of wrongdoing"
        " — schedules legitimately change (new job, travel, illness, finals"
        " crunch). This report is advisory only.",
        "",
        "## Per-Assignment Dominant Commit Hours",
        "",
    ]

    for label, fp in zip(repo_labels, fingerprints):
        dom = _dominant_hours(fp)
        lines.append(f"- **{label}**: dominant hour(s): {dom}")

    lines += [
        "",
        "## Rhythm Divergence",
        "",
        f"Max pairwise total-variation distance: **{divergence:.2f}**",
        "",
        f"Interpretation: *{_band(divergence)}*",
        "",
        "---",
        "",
        "*Schedules legitimately change. This is a screening aid only and is"
        " not proof of any irregularity. Human review is required before any"
        " action is taken.*",
    ]

    return "\n".join(lines) + "\n"
