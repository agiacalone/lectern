"""Org-scrape repo discovery — the post-GitHub-Classroom seam (Classroom is
decommissioned 2026-08-28). Lists an org's repos and filters by assignment prefix."""
from __future__ import annotations
import subprocess


def filter_repos_by_prefix(names, prefix):
    """Pure: repo names that start with the assignment prefix, order preserved."""
    return [n for n in names if n.startswith(prefix)]


def discover_scrape_repos(org, prefix):
    """List <org> repos via gh and filter by prefix. Returns repo names.
    Raises RuntimeError with guidance if gh is missing."""
    try:
        out = subprocess.run(
            ["gh", "repo", "list", org, "--limit", "1000", "--json", "name",
             "--jq", ".[].name"],
            capture_output=True, text=True, check=True).stdout
    except FileNotFoundError as e:
        raise RuntimeError("gh CLI not found; install GitHub CLI to use scrape mode") from e
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"gh repo list failed for org {org}: {e.stderr}") from e
    names = [ln.strip() for ln in out.splitlines() if ln.strip()]
    return filter_repos_by_prefix(names, prefix)
