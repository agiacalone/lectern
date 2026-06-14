"""Read the lab autograde contract (grading/result.json) into typed results."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable
import base64, json, subprocess

@dataclass
class Challenge:
    key: str; passed: bool; points: int; max: int

@dataclass
class AutogradeResult:
    honor_ok: bool; points: int; max: int
    challenges: dict[str, Challenge]
    commit: str | None = None
    @property
    def all_failed(self) -> bool:
        return all(not c.passed for c in self.challenges.values())

def parse_result_json(text: str) -> AutogradeResult | None:
    try:
        d = json.loads(text)
    except (ValueError, TypeError):
        return None
    chals = {k: Challenge(key=k, passed=bool(v.get("pass")),
                          points=int(v.get("points", 0)), max=int(v.get("max", 0)))
             for k, v in (d.get("challenges") or {}).items()}
    return AutogradeResult(honor_ok=bool(d.get("honor_ok")),
                           points=int(d.get("points", 0)), max=int(d.get("max", 0)),
                           challenges=chals, commit=d.get("commit"))

def _default_gh(args: list[str]) -> str:
    proc = subprocess.run(["gh", *args], capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "gh failed")
    return proc.stdout

def fetch_autograde(org: str, repo: str, result_path: str, *,
                    branch: str = "main",
                    gh: Callable[[list[str]], str] = _default_gh) -> AutogradeResult | None:
    """Read result.json from the repo's default branch via the contents API.
    Returns None if absent (lab not conforming / no run yet)."""
    try:
        raw = gh(["api",
                  f"/repos/{org}/{repo}/contents/{result_path}?ref={branch}",
                  "--jq", ".content"])
    except RuntimeError:
        return None
    try:
        text = base64.b64decode(raw).decode("utf-8", "replace")
    except Exception:
        return None
    return parse_result_json(text)


def scrape_autograde(org: str, repo: str, workflow: str, steps: list[dict], *,
                     branch: str = "main",
                     gh: Callable[[list[str]], str] = _default_gh) -> AutogradeResult | None:
    """Legacy fallback for labs without the result.json contract: read the latest
    completed workflow run's job-step conclusions and map them to challenge points.

    ``steps`` is a list of dicts: {"name": "Ward I", "key": "ward1", "points": 10,
    "optional": False}. A step whose CI conclusion == "success" earns its points.
    honor_ok is inferred: the honor gate makes ALL wards fail, so any passing ward
    implies the flag was present (heuristic — noted as advisory).
    Returns None if no completed run or the jobs payload can't be read."""
    try:
        runs_raw = gh(["api",
                       f"/repos/{org}/{repo}/actions/workflows/{workflow}/runs"
                       f"?branch={branch}&status=completed&per_page=1"])
        runs = json.loads(runs_raw).get("workflow_runs") or []
    except (RuntimeError, ValueError, TypeError):
        return None
    if not runs:
        return None
    run = runs[0]
    run_id, head_sha = run.get("id"), run.get("head_sha")
    try:
        jobs_raw = gh(["api", f"/repos/{org}/{repo}/actions/runs/{run_id}/jobs"])
        jobs = json.loads(jobs_raw).get("jobs") or []
    except (RuntimeError, ValueError, TypeError):
        return None
    conclusion_by_name: dict[str, str] = {}
    for job in jobs:
        for st in job.get("steps") or []:
            conclusion_by_name[st.get("name", "")] = st.get("conclusion", "")
    chals: dict[str, Challenge] = {}
    for s in steps:
        passed = conclusion_by_name.get(s["name"]) == "success"
        pts = int(s.get("points", 0))
        chals[s["key"]] = Challenge(key=s["key"], passed=passed,
                                    points=pts if passed else 0, max=pts)
    total = sum(c.points for c in chals.values())
    max_pts = sum(c.max for c in chals.values())
    honor_ok = any(c.passed for c in chals.values())
    return AutogradeResult(honor_ok=honor_ok, points=total, max=max_pts,
                           challenges=chals, commit=head_sha)
