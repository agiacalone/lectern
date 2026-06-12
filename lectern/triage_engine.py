"""Scoring engine: iterate the signal registry, sum points, and bucket the score.

Deliberate omission — window_cap_hours:
    The upstream assignment-triage/grader.py includes a ``window_cap_hours``
    threshold (default 2 h) that hard-caps the score at ≤ 20 when ALL commits
    land within a 2-hour window.  Lectern intentionally does NOT implement this
    cap.  The cap is an adverse shortcut: it silently penalises students who
    sprint through last-minute work, which is a common and legitimate pattern on
    short deadlines.  Under lectern's "no automated adverse finding" doctrine,
    any concern surfaced by such a pattern must be surfaced through the advisory
    Part B score and Part C framing — not a silent hard cap — so a human
    reviewer makes the call.  Do not restore this cap without revisiting that
    doctrine first.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from lectern.triage_signals import SIGNALS, RepoFacts


def _profile_applies(allowed, active_profile: str) -> bool:
    """Return True if the active profile is covered by the signal's allowed-profiles spec."""
    return allowed == "all" or active_profile in allowed


def score_repo(repo_path, cfg: dict, profile: str = "short-project"):
    """Run every applicable signal, sum points, and return (score, reasoning, bucket).

    Parameters
    ----------
    repo_path : path-like
        Root of the git repository to analyse.
    cfg : dict
        Configuration dict with keys:
          ``assignment``   — assigned_date, due_date, expected_commits
          ``thresholds``   — pass, flag, min_spread_days (optional)
          ``weights``      — per-signal weight overrides (empty dict = use defaults)
    profile : str
        Active triage profile name (matched against each signal's ``profiles`` spec).
    """
    facts = RepoFacts.from_repo(repo_path)
    if not facts.dates:
        return 0, "MISSING: no commits found", "FLAG"

    cfg = {**cfg, "weights": cfg.get("weights", {})}
    found, missing, points = [], [], 0

    for name, (fn, default_weight, profiles) in SIGNALS.items():
        if not _profile_applies(profiles, profile):
            continue
        effective_weight = cfg["weights"].get(name, default_weight)
        if effective_weight == 0:
            continue
        res = fn(facts, cfg)
        points += res.points
        (found if res.present else missing).append(res.evidence)

    reasoning = " | ".join(found + [f"MISSING: {m}" for m in missing])
    thresholds = cfg.get("thresholds", {})
    bucket = triage(points, thresholds.get("pass", 60), thresholds.get("flag", 20))
    return points, reasoning, bucket


def triage(score: int, pass_t: int, flag_t: int) -> str:
    """Bucket a numeric score into PASS / REVIEW / FLAG."""
    if score >= pass_t:
        return "PASS"
    if score <= flag_t:
        return "FLAG"
    return "REVIEW"


_PROFILES = Path(__file__).parent / "references" / "triage_profiles.yaml"


def load_profile(name):
    """Load a triage profile by name from the YAML registry.

    Parameters
    ----------
    name : str
        Profile name (e.g., "single-sitting", "short-project", "term-project").

    Returns
    -------
    dict
        Profile dict with keys "thresholds" and "weights".

    Raises
    ------
    ValueError
        If the profile name is not found.
    """
    data = yaml.safe_load(_PROFILES.read_text())
    if name not in data:
        raise ValueError(f"unknown triage profile: {name}")
    return data[name]
