"""Per-repo record: container + JSON (de)serialization (facts only — Part A)."""
from __future__ import annotations
from dataclasses import dataclass, asdict, field
from lectern.recon_autograde import AutogradeResult, Challenge
from lectern.recon_git import GitRecon
from lectern.recon_docs import DocRecon

@dataclass
class RepoRecord:
    github_id: str; student: str; repo: str; grading_commit: str | None = None
    autograde: AutogradeResult | None = None
    git: GitRecon | None = None
    docs: dict[str, DocRecon] = field(default_factory=dict)
    links: dict = field(default_factory=dict)

def record_to_dict(r: RepoRecord) -> dict:
    return {
        "github_id": r.github_id, "student": r.student, "repo": r.repo,
        "grading_commit": r.grading_commit,
        "links": dict(r.links),
        "autograde": None if r.autograde is None else {
            "honor_ok": r.autograde.honor_ok, "points": r.autograde.points,
            "max": r.autograde.max, "commit": r.autograde.commit,
            "all_failed": r.autograde.all_failed,
            "challenges": {k: asdict(c) for k, c in r.autograde.challenges.items()}},
        "git": None if r.git is None else asdict(r.git),
        "docs": {k: asdict(v) for k, v in r.docs.items()},
    }

def record_from_dict(d: dict) -> RepoRecord:
    ag = d.get("autograde")
    autograde = None
    if ag is not None:
        autograde = AutogradeResult(
            honor_ok=ag["honor_ok"], points=ag["points"], max=ag["max"], commit=ag.get("commit"),
            challenges={k: Challenge(**c) for k, c in ag.get("challenges", {}).items()})
    git = GitRecon(**d["git"]) if d.get("git") else None
    docs = {k: DocRecon(**v) for k, v in (d.get("docs") or {}).items()}
    return RepoRecord(github_id=d["github_id"], student=d["student"], repo=d["repo"],
                      grading_commit=d.get("grading_commit"), autograde=autograde, git=git,
                      docs=docs, links=d.get("links") or {})
