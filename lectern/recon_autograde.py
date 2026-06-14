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
