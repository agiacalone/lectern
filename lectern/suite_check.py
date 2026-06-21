"""Verify installed LMS-suite component versions against SUITE.md ranges.

reg-suite-check (a ~/bin wrapper) execs `python -m lectern.suite_check`.
"""
from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path

import yaml

_FENCE_RE = re.compile(r"```yaml\s*\n(.*?)```", re.DOTALL)
_CLAUSE_RE = re.compile(r"(>=|<=|==|>|<)\s*(.+)")

# Default lookup roots for each non-lectern component (env override first).
_DEFAULT_ROOTS = {
    "scriptorium": ["LECTERN_SCRIPTORIUM_DIR", "~/git/scriptorium"],
    "oracle": ["LECTERN_ORACLE_DIR", "/mnt/es2/opt/oracle", "~/git/oracle"],
}


@dataclass
class CheckResult:
    component: str
    installed: str | None
    spec: str
    ok: bool
    skipped: bool


def load_matrix(suite_md: Path) -> dict:
    text = Path(suite_md).read_text(encoding="utf-8")
    m = _FENCE_RE.search(text)
    if not m:
        raise ValueError(f"{suite_md}: no ```yaml matrix block found")
    return yaml.safe_load(m.group(1))


def _ver_tuple(s: str) -> tuple[int, int, int]:
    nums = [int(n) for n in re.findall(r"\d+", s)][:3]
    while len(nums) < 3:
        nums.append(0)
    return (nums[0], nums[1], nums[2])


def in_range(version: str, spec: str) -> bool:
    v = _ver_tuple(version)
    for clause in spec.split(","):
        clause = clause.strip()
        if not clause:
            continue
        m = _CLAUSE_RE.match(clause)
        if not m:
            return False
        op, target = m.group(1), _ver_tuple(m.group(2))
        if op == ">=" and not (v >= target):
            return False
        if op == ">" and not (v > target):
            return False
        if op == "<=" and not (v <= target):
            return False
        if op == "<" and not (v < target):
            return False
        if op == "==" and not (v == target):
            return False
    return True


def _first_existing_root(component: str) -> Path | None:
    for candidate in _DEFAULT_ROOTS.get(component, []):
        val = os.environ.get(candidate) if candidate.isupper() else candidate
        if not val:
            continue
        p = Path(os.path.expanduser(val))
        if p.exists():
            return p
    return None


def resolve_version(component: str, *, root: Path | None = None) -> str | None:
    if component == "lectern":
        try:
            return metadata.version("lectern")
        except metadata.PackageNotFoundError:
            pj = Path(__file__).resolve().parent.parent / "pyproject.toml"
            m = re.search(r'(?m)^version\s*=\s*"([^"]+)"', pj.read_text()) if pj.exists() else None
            return m.group(1) if m else None
    base = root if root is not None else _first_existing_root(component)
    if base is None or not Path(base).exists():
        return None
    base = Path(base)
    pkg = base / "package.json"
    if pkg.exists():
        try:
            return json.loads(pkg.read_text()).get("version")
        except (ValueError, OSError):
            return None
    vf = base / "VERSION"
    if vf.exists():
        return vf.read_text().strip() or None
    pj = base / "pyproject.toml"
    if pj.exists():
        m = re.search(r'(?m)^version\s*=\s*"([^"]+)"', pj.read_text())
        return m.group(1) if m else None
    return None


def check(matrix: dict, *, roots: dict[str, Path] | None = None) -> list[CheckResult]:
    roots = roots or {}
    out: list[CheckResult] = []
    for component, spec in matrix.get("components", {}).items():
        installed = resolve_version(component, root=roots.get(component))
        if installed is None:
            out.append(CheckResult(component, None, spec, ok=True, skipped=True))
        else:
            out.append(CheckResult(component, installed, spec, ok=in_range(installed, spec), skipped=False))
    return out


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    suite_md = Path(argv[0]) if argv else Path(__file__).resolve().parent.parent / "SUITE.md"
    matrix = load_matrix(suite_md)
    results = check(matrix)
    bad = 0
    for r in results:
        if r.skipped:
            status = "SKIP (absent)"
        elif r.ok:
            status = "ok"
        else:
            status = "MISMATCH"
            bad += 1
        print(f"  {r.component:<12} {str(r.installed or '-'):<10} {r.spec:<16} {status}")
    print(f"\n{matrix.get('suite','suite')} {matrix.get('release','')}: "
          f"{'OK' if bad == 0 else f'{bad} mismatch(es)'}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
