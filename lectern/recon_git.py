"""Commit intelligence per repo — facts only, wrapping the triage signal engine."""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
import subprocess

@dataclass
class GitRecon:
    commits: int = 0
    spread_days: float = 0.0
    force_pushes: int = 0
    largest_add: int = 0
    deletions: int = 0
    notable_messages: list[str] = field(default_factory=list)
    triage_bucket: str = ""
    triage_score: int | None = None

def _log(repo: Path, fmt: str) -> list[str]:
    out = subprocess.run(["git","-C",str(repo),"log",f"--pretty=format:{fmt}"],
                         capture_output=True, text=True)
    return [l for l in out.stdout.splitlines() if l.strip()]

def recon_git(repo: Path, *, profile: str = "short-project") -> GitRecon:
    msgs = _log(repo, "%s")
    dates = _log(repo, "%cI")
    spread = 0.0
    if len(dates) >= 2:
        from datetime import datetime
        ds = sorted(datetime.fromisoformat(d) for d in dates)
        spread = (ds[-1] - ds[0]).total_seconds() / 86400.0
    g = GitRecon(commits=len(msgs), spread_days=round(spread, 2),
                 notable_messages=msgs[:5])
    # Best-effort enrichment from the verified triage API; never fatal.
    try:
        from lectern import triage_engine as te
        from lectern.triage_signals import RepoFacts
        facts = RepoFacts.from_repo(repo)
        g.deletions = int(round(facts.del_ratio))
        g.largest_add = int(round(facts.dump_pct))
        cfg = te.load_profile(profile)
        points, _reasoning, bucket = te.score_repo(str(repo), cfg, profile=profile)
        g.triage_score = int(points)
        g.triage_bucket = str(bucket)
    except Exception:
        pass
    return g
