"""Resolve the repo population from a roster CSV + manifest prefix."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import csv

@dataclass
class RepoRef:
    github_id: str; student: str; repo: str

def discover_repos(roster_csv: Path, *, repo_prefix: str) -> list[RepoRef]:
    refs: list[RepoRef] = []
    with Path(roster_csv).open(newline="") as f:
        for row in csv.DictReader(f):
            gid = (row.get("github_username") or row.get("github_id") or "").strip()
            if not gid:
                continue
            name = (row.get("student_name") or row.get("canonical_name")
                    or row.get("name") or "").strip()
            refs.append(RepoRef(github_id=gid, student=name, repo=f"{repo_prefix}{gid}"))
    return refs
