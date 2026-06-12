"""Pure functions for the syllabus control-number serial.

A repo-tree SHA-256 (sibling to exam_serial.py, different algorithm): hash every
git-tracked file in sorted-path order, after stripping the primary syllabus md's
own serial/revision-of frontmatter lines and the rendered footer line so the
serial never fingerprints itself. 8 hex, uppercase.
See <vault>/plans/specs/2026-06-09-syllabus-generation-design.md.
"""
from __future__ import annotations
import hashlib
import re
import subprocess
from pathlib import Path

_STRIP_FM = re.compile(rb"(?m)^(serial|revision-of):.*\n?")
_STRIP_FOOTER = re.compile(rb"(?m)^\*Syllabus version [0-9A-F]{8} \xc2\xb7 [0-9-]+\*\s*\n?")


def primary_md(repo: Path) -> str:
    for name in ("syllabus.md", "README.md"):
        if (Path(repo) / name).is_file():
            return name
    raise SystemExit(f"syllabus: no syllabus.md or README.md in {repo}")


def _tracked_files(repo: Path, ref: str | None) -> list[str]:
    if ref:
        cmd = ["git", "-C", str(repo), "ls-tree", "-r", "--name-only", ref]
    else:
        cmd = ["git", "-C", str(repo), "ls-files"]
    out = subprocess.run(cmd, capture_output=True, text=True, check=True).stdout
    return sorted(p for p in out.splitlines() if p)


def _read_file(repo: Path, path: str, ref: str | None) -> bytes:
    if ref:
        return subprocess.run(["git", "-C", str(repo), "show", f"{ref}:{path}"],
                              capture_output=True, check=True).stdout
    return (Path(repo) / path).read_bytes()


def compute_serial(repo: Path, ref: str | None = None) -> str:
    repo = Path(repo)
    pm = primary_md(repo)
    h = hashlib.sha256()
    for path in _tracked_files(repo, ref):
        data = _read_file(repo, path, ref)
        if path == pm:
            data = _STRIP_FM.sub(b"", data)
            data = _STRIP_FOOTER.sub(b"", data)
            data = data.rstrip(b"\n") + b"\n"   # normalize trailing newlines
        h.update(path.encode("utf-8") + b"\0" + data)
    return h.hexdigest()[:8].upper()
