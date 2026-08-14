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
            # Identifier precedence. `username` must outrank `github_id` because
            # a Classroom 50 roster.csv uses BOTH columns with different meanings
            # than a legacy GitHub Classroom roster does: `username` is the login
            # and `github_id` is the immutable NUMERIC id. Legacy rosters put the
            # login in `github_id` (see examples/.../.cohort-spec.json), so that
            # stays in the chain as the last resort and old behavior is unchanged
            # whenever `username` is absent. Reading `github_id` first would build
            # repo names like `<prefix>-1548364` instead of `<prefix>-agiacalone`.
            gid = (row.get("github_username") or row.get("username")
                   or row.get("github_id") or "").strip()
            if not gid:
                continue
            name = (row.get("student_name") or row.get("canonical_name")
                    or row.get("name") or "").strip()
            if not name:
                # Classroom 50 splits the name across two columns.
                name = " ".join(p for p in (
                    (row.get("first_name") or "").strip(),
                    (row.get("last_name") or "").strip(),
                ) if p)
            refs.append(RepoRef(github_id=gid, student=name, repo=f"{repo_prefix}{gid}"))
    return refs
