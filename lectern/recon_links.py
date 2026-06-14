"""Resolve a student repo's quick links (repo, docs-at-commit, feedback PR/branch)."""
from __future__ import annotations

def repo_links(*, org: str, repo: str, grading_commit: str | None,
               doc_path: str, feedback_pr: int = 1, default_branch: str = "main") -> dict[str, str]:
    base = f"https://github.com/{org}/{repo}"
    ref = grading_commit or default_branch
    return {
        "repo": base,
        "docs": f"{base}/blob/{ref}/{doc_path}",
        "feedback_pr": f"{base}/pull/{feedback_pr}",
        "feedback_branch": f"{base}/tree/feedback",
    }
