"""Read the lab autograde contract (grading/result.json) into typed results."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable
import base64, json, re, subprocess

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

def _graded_runs(runs: list[dict]) -> list[dict]:
    """Drop runs that never graded anything. A run cancelled before it got a runner
    (Actions out of minutes, 2026-10-05) is still status=completed but has no log
    and no artifact; taking it as "the latest run" silently loses a real result."""
    return [r for r in runs if r.get("conclusion") not in ("cancelled", "skipped")]


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


def _default_download(org: str, repo: str, run_id, artifact: str, member: str) -> str | None:
    """Download a named run artifact and return the text of `member` inside it.
    Uses `gh run download` (extracts the artifact's files to a temp dir)."""
    import subprocess, tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory(prefix="recon-art-") as d:
        proc = subprocess.run(
            ["gh", "run", "download", str(run_id), "-R", f"{org}/{repo}",
             "-n", artifact, "-D", d],
            capture_output=True, text=True)
        if proc.returncode != 0:
            return None
        f = Path(d) / member
        if not f.exists():  # artifact may store the file flat or nested — search for it
            hits = list(Path(d).rglob(Path(member).name))
            if not hits:
                return None
            f = hits[0]
        return f.read_text(encoding="utf-8", errors="replace")


def fetch_autograde_artifact(org: str, repo: str, *, workflow: str = "autograde.yml",
                             branch: str = "main", artifact: str = "grading-result",
                             member: str = "grading/result.json",
                             gh: Callable[[list[str]], str] = _default_gh,
                             download=_default_download) -> AutogradeResult | None:
    """Read result.json from the latest completed run's CI **artifact** (the durable,
    Classroom-independent contract home — students cannot delete run artifacts).
    Returns None if no completed run or the artifact/file is absent."""
    try:
        runs_raw = gh(["api",
                       f"/repos/{org}/{repo}/actions/workflows/{workflow}/runs"
                       f"?branch={branch}&status=completed&per_page=10"])
        runs = _graded_runs(json.loads(runs_raw).get("workflow_runs") or [])
    except (RuntimeError, ValueError, TypeError):
        return None
    if not runs:
        return None
    run = runs[0]
    text = download(org, repo, run.get("id"), artifact, member)
    if text is None:
        return None
    r = parse_result_json(text)
    if r is not None and not r.commit:
        r.commit = run.get("head_sha")
    return r


def scrape_autograde(org: str, repo: str, workflow: str, steps: list[dict], *,
                     branch: str = "main",
                     gh: Callable[[list[str]], str] = _default_gh) -> AutogradeResult | None:
    """Legacy fallback for labs without the result.json contract: read the latest
    completed workflow run's **logs** and map per-challenge PASS/FAIL lines to points.

    ``steps`` is a list of dicts: {"name": "Ward I", "key": "ward1", "points": 10,
    "optional": False}. A challenge earns its points iff a ``PASS <key>`` line appears
    in the run log. **Do NOT use the jobs-API step conclusions**: the Spellbreaker
    autograder marks ward steps ``continue-on-error: true``, which masks every step's
    API ``conclusion`` as "success" regardless of the real outcome — so conclusions
    are useless. The grader prints authoritative ``PASS <key>`` / ``FAIL <key>: ...``
    lines to the log, which is what we parse. honor_ok is False when the grader
    reports a missing/incorrect honor flag.
    Returns None if no completed run or the log can't be read."""
    try:
        runs_raw = gh(["api",
                       f"/repos/{org}/{repo}/actions/workflows/{workflow}/runs"
                       f"?branch={branch}&status=completed&per_page=10"])
        runs = _graded_runs(json.loads(runs_raw).get("workflow_runs") or [])
    except (RuntimeError, ValueError, TypeError):
        return None
    if not runs:
        return None
    run = runs[0]
    run_id, head_sha = run.get("id"), run.get("head_sha")
    try:
        log = gh(["run", "view", str(run_id), "-R", f"{org}/{repo}", "--log"])
    except RuntimeError:
        return None
    honor_ok = "honor flag missing" not in log
    chals: dict[str, Challenge] = {}
    for s in steps:
        key = s["key"]
        pts = int(s.get("points", 0))
        passed = bool(re.search(rf"\bPASS {re.escape(key)}\b", log))
        chals[key] = Challenge(key=key, passed=passed,
                               points=pts if passed else 0, max=pts)
    total = sum(c.points for c in chals.values())
    max_pts = sum(c.max for c in chals.values())
    return AutogradeResult(honor_ok=honor_ok, points=total, max=max_pts,
                           challenges=chals, commit=head_sha)


def fetch_gradebox(out_dir, github_id: str, *, exact_score: list | None = None,
                   commit: str | None = None) -> AutogradeResult | None:
    """Read one student's gradebox result (``<out_dir>/<github_id>/result.json``).

    gradebox grades on the instructor's host, so this needs no Actions minutes and
    no network. Each scored test becomes a challenge. ``exact_score`` is an optional
    list of regexes tried in order against the tests' stdout; the first capture
    group that matches replaces the banded total (capped at the spec's max), for
    labs whose program prints its own exact score."""
    from pathlib import Path
    p = Path(out_dir) / github_id / "result.json"
    if not p.is_file():
        return None
    try:
        d = json.loads(p.read_text())
    except (OSError, ValueError):
        return None
    mx = int(d.get("max", 0))
    chals: dict[str, Challenge] = {}
    bp = d.get("build_points")
    if bp is None and d.get("build_passed"):
        # Older gradebox results lack build_points: it is whatever the score holds
        # beyond the passed tests.
        passed = sum(int(t.get("points") or 0) for t in d.get("tests") or [] if t.get("passed"))
        bp = max(int(d.get("score", 0)) - passed, 0)
    if bp:
        bp = int(bp)
        chals["build"] = Challenge("build", bool(d.get("build_passed")),
                                   bp if d.get("build_passed") else 0, bp)
    for t in d.get("tests") or []:
        pts = int(t.get("points") or 0)
        if pts <= 0:
            continue
        ok = bool(t.get("passed"))
        chals[t["name"]] = Challenge(t["name"], ok, pts if ok else 0, pts)
    points = int(d.get("score", 0))
    if exact_score:
        text = "\n".join(t.get("stdout") or "" for t in d.get("tests") or [])
        for pat in exact_score:
            m = re.search(pat, text)
            if m:
                points = min(int(m.group(1)), mx)
                break
    return AutogradeResult(honor_ok=True, points=points, max=mx,
                           challenges=chals, commit=commit)
