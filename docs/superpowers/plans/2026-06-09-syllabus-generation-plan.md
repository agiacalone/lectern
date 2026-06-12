# Syllabus Generation (`reg-syllabus`) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A lectern `reg-syllabus` capability that stamps a syllabus repo with a control-number serial (repo-tree hash), appends a register row, and builds the distribution HTML — systematizing today's ad-hoc per-repo scripts.

**Architecture:** `lectern/syllabus_serial.py` computes the serial (a pure repo-tree SHA-256, sibling to `exam_serial.py`); `lectern/syllabus.py` does `stamp` (inject serial into the primary md + footer, append register row) and `build` (pandoc → HTML + Canvas variant, PDF opt-in), with a `reg-syllabus` CLI. The eisvogel/CSS templates ship as `lectern/references/`.

**Tech Stack:** Python 3.14 (lectern venv), `git` (tracked-file enumeration), `pandoc` (+ `weasyprint`/`chromium` for opt-in PDF), Markdown syllabi in GitHub repos.

> **GPG / repos:** signed commits can't run from the harness; stage only, the human commits in a real terminal. Develop in `lectern-dev` (branch `feat/syllabus-generation`); release clean to public `lectern` after. Test interpreter: `/home/anthony/.local/share/personal-assistant/venv/bin/python -m pytest` from the repo root.

---

## File Structure

- **Create** `lectern/syllabus_serial.py` — `primary_md`, `_tracked_files`, `_read_file`, `compute_serial`. One job: the deterministic serial.
- **Create** `lectern/syllabus.py` — `stamp`, `build`, register-append helpers, `main()` CLI.
- **Create** `lectern/references/syllabus.css`, `lectern/references/eisvogel.latex` — lifted verbatim from `~/git/cecs-378-su26-01-syllabus-10660/`.
- **Create** `tests/test_syllabus_serial.py`, `tests/test_syllabus.py`, plus an inline git-repo fixture builder.
- **Create** `~/bin/reg-syllabus` wrapper.

---

## Task 1: `syllabus_serial.py` — the control-number serial

**Files:** Create `lectern/syllabus_serial.py`, `tests/test_syllabus_serial.py`

- [ ] **Step 1: Test helper + failing test**

```python
# tests/test_syllabus_serial.py
import subprocess, pathlib
from lectern.syllabus_serial import compute_serial, primary_md

def _git_repo(tmp_path, files: dict) -> pathlib.Path:
    r = tmp_path / "repo"; r.mkdir()
    for name, content in files.items():
        (r / name).write_text(content)
    subprocess.run(["git", "init", "-q"], cwd=r, check=True)
    subprocess.run(["git", "add", "-A"], cwd=r, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-qm", "init"], cwd=r, check=True)
    return r

def test_serial_is_deterministic_8hex(tmp_path):
    r = _git_repo(tmp_path, {"README.md": "---\nserial: AAAAAAAA\n---\n# Syllabus\nbody\n"})
    s1 = compute_serial(r); s2 = compute_serial(r)
    assert s1 == s2 and len(s1) == 8 and s1 == s1.upper()

def test_serial_ignores_its_own_serial_line(tmp_path):
    r1 = _git_repo(tmp_path / "a", {"README.md": "---\nserial: AAAAAAAA\n---\nbody\n"})
    r2 = _git_repo(tmp_path / "b", {"README.md": "---\nserial: ZZZZZZZZ\n---\nbody\n"})
    assert compute_serial(r1) == compute_serial(r2)   # serial line stripped before hashing

def test_serial_changes_on_body_edit(tmp_path):
    r1 = _git_repo(tmp_path / "a", {"README.md": "---\nserial: X\n---\nbody one\n"})
    r2 = _git_repo(tmp_path / "b", {"README.md": "---\nserial: X\n---\nbody TWO\n"})
    assert compute_serial(r1) != compute_serial(r2)

def test_primary_md_prefers_syllabus_then_readme(tmp_path):
    r = _git_repo(tmp_path, {"README.md": "x", "syllabus.md": "y"})
    assert primary_md(r) == "syllabus.md"
```

- [ ] **Step 2: Run → FAIL** (`...venv/bin/python -m pytest tests/test_syllabus_serial.py -v`) — module missing.

- [ ] **Step 3: Implement** `lectern/syllabus_serial.py`:

```python
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
        h.update(path.encode("utf-8") + b"\0" + data)
    return h.hexdigest()[:8].upper()
```

- [ ] **Step 4: Run → PASS.**
- [ ] **Step 5: Stage** `git add lectern/syllabus_serial.py tests/test_syllabus_serial.py` (no commit — see header).

---

## Task 2: `stamp` — inject serial into frontmatter + footer

**Files:** Create `lectern/syllabus.py`; add to `tests/test_syllabus.py`

- [ ] **Step 1: Failing test**

```python
# tests/test_syllabus.py
import subprocess, pathlib
from lectern.syllabus import stamp
from lectern.syllabus_serial import compute_serial

def _git_repo(tmp_path, readme):
    r = tmp_path / "cecs-378-su26-01-syllabus-10660"; r.mkdir()
    (r / "README.md").write_text(readme)
    subprocess.run(["git","init","-q"], cwd=r, check=True)
    subprocess.run(["git","add","-A"], cwd=r, check=True)
    subprocess.run(["git","-c","user.email=t@t","-c","user.name=t","commit","-qm","i"], cwd=r, check=True)
    return r

def test_stamp_injects_serial_and_footer(tmp_path):
    vault = tmp_path / "vault"; (vault / "notes").mkdir(parents=True)
    (vault / "notes" / "syllabus-serial-register.md").write_text("# Syllabus Serial Register\n")
    r = _git_repo(tmp_path, "---\nserial: OLD\n---\n# Syllabus\nbody\n")
    serial = stamp(r, vault, today="2026-06-09")
    text = (r / "README.md").read_text()
    assert f"serial: {serial}" in text
    assert f"*Syllabus version {serial} · 2026-06-09*" in text
    assert serial != "OLD" and len(serial) == 8

def test_stamp_idempotent_on_unchanged_tree(tmp_path):
    vault = tmp_path / "vault"; (vault / "notes").mkdir(parents=True)
    (vault / "notes" / "syllabus-serial-register.md").write_text("# Syllabus Serial Register\n")
    r = _git_repo(tmp_path, "---\nserial: X\n---\nbody\n")
    s1 = stamp(r, vault, today="2026-06-09")
    # committing the stamped state, re-stamp → same serial (strip makes it stable)
    subprocess.run(["git","add","-A"], cwd=r, check=True)
    subprocess.run(["git","-c","user.email=t@t","-c","user.name=t","commit","-qm","stamp"], cwd=r, check=True)
    s2 = stamp(r, vault, today="2026-06-09")
    assert s1 == s2
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Implement** the stamp half of `lectern/syllabus.py`:

```python
"""reg-syllabus — stamp a syllabus repo with its control-number serial and build
the distribution HTML. See the syllabus design spec + [[notes/syllabus-doctrine]]."""
from __future__ import annotations
import argparse
import re
import subprocess
from datetime import date
from pathlib import Path

from lectern.syllabus_serial import compute_serial, primary_md

_FM_BLOCK = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
_FOOTER_RE = re.compile(r"(?m)^\*Syllabus version [0-9A-F]{8} · [0-9-]+\*\s*$\n?")
_REPO_NAME = re.compile(r"cecs-(?P<course>\d+)-(?P<term>[a-z]{2}\d{2})-(?P<section>\d+)-syllabus-(?P<crn>\w+)")


def _set_frontmatter(text: str, serial: str, revision_of: str | None) -> str:
    m = _FM_BLOCK.match(text)
    body_fm = m.group(1) if m else ""
    lines = [ln for ln in body_fm.splitlines()
             if not ln.startswith(("serial:", "revision-of:"))]
    lines.append(f"serial: {serial}")
    if revision_of:
        lines.append(f"revision-of: {revision_of}")
    new_fm = "---\n" + "\n".join(lines).strip("\n") + "\n---\n"
    return new_fm + (text[m.end():] if m else text)


def _set_footer(text: str, serial: str, today: str) -> str:
    text = _FOOTER_RE.sub("", text).rstrip("\n")
    return text + f"\n\n*Syllabus version {serial} · {today}*\n"


def stamp(repo, vault_root, revision_of: str | None = None, today: str | None = None) -> str:
    repo = Path(repo)
    today = today or date.today().isoformat()
    serial = compute_serial(repo)
    pm = repo / primary_md(repo)
    text = pm.read_text(encoding="utf-8")
    text = _set_frontmatter(text, serial, revision_of)
    text = _set_footer(text, serial, today)
    pm.write_text(text, encoding="utf-8")
    _append_register(Path(vault_root), repo, serial, today, revision_of)
    return serial
```

(Defer `_append_register` to Task 3 — for now stub it: `def _append_register(*a, **k): pass`, then replace.)

- [ ] **Step 4: Run → PASS.** **Step 5: Stage.**

---

## Task 3: register append

**Files:** Modify `lectern/syllabus.py`; add test to `tests/test_syllabus.py`

- [ ] **Step 1: Failing test**

```python
def test_register_appends_one_row_per_serial(tmp_path):
    vault = tmp_path / "vault"; (vault / "notes").mkdir(parents=True)
    reg = vault / "notes" / "syllabus-serial-register.md"
    reg.write_text("# Syllabus Serial Register\n")
    r = _git_repo(tmp_path, "---\nserial: X\n---\nbody\n")
    serial = stamp(r, vault, today="2026-06-09")
    text = reg.read_text()
    assert "## Live (Su26 forward)" in text
    assert f"| 378 | 01 | su26 | 10660 | {serial} | 2026-06-09 |" in text
    # idempotent on serial: stamp same tree again → still one row
    subprocess.run(["git","add","-A"], cwd=r, check=True)
    subprocess.run(["git","-c","user.email=t@t","-c","user.name=t","commit","-qm","s"], cwd=r, check=True)
    stamp(r, vault, today="2026-06-09")
    assert reg.read_text().count(f"| {serial} |") == 1
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Implement** `_append_register` (replace the stub):

```python
_REG_HEADER = ("\n## Live (Su26 forward)\n\n"
               "| Course | Section | Term | CRN | Serial | Date | Revision-of |\n"
               "| --- | --- | --- | --- | --- | --- | --- |\n")


def _append_register(vault_root: Path, repo: Path, serial: str,
                     today: str, revision_of: str | None) -> None:
    reg = vault_root / "notes" / "syllabus-serial-register.md"
    text = reg.read_text(encoding="utf-8") if reg.exists() else "# Syllabus Serial Register\n"
    if f"| {serial} |" in text:
        return                                   # idempotent on serial
    if "## Live (Su26 forward)" not in text:
        text = text.rstrip("\n") + "\n" + _REG_HEADER
    m = _REPO_NAME.search(repo.name)
    c = m.groupdict() if m else {"course": "?", "term": "?", "section": "?", "crn": "?"}
    row = (f"| {c['course']} | {c['section']} | {c['term']} | {c['crn']} "
           f"| {serial} | {today} | {revision_of or ''} |\n")
    reg.write_text(text.rstrip("\n") + "\n" + row, encoding="utf-8")
```

- [ ] **Step 4: Run → PASS.** **Step 5: Stage.**

---

## Task 4: `build` — pandoc HTML + Canvas variant + opt-in PDF

**Files:** Modify `lectern/syllabus.py`; create `lectern/references/{syllabus.css,eisvogel.latex}`; add test

- [ ] **Step 1: Lift the templates.**

```bash
cp ~/git/cecs-378-su26-01-syllabus-10660/syllabus.css lectern/references/syllabus.css
cp ~/git/cecs-378-su26-01-syllabus-10660/eisvogel.latex lectern/references/eisvogel.latex
```

- [ ] **Step 2: Failing test** (`@needs_pandoc` — skip if pandoc absent):

```python
import shutil, pytest
needs_pandoc = pytest.mark.skipif(shutil.which("pandoc") is None, reason="pandoc not installed")

@needs_pandoc
def test_build_emits_html_with_serial_footer(tmp_path):
    vault = tmp_path / "vault"; (vault / "notes").mkdir(parents=True)
    (vault / "notes" / "syllabus-serial-register.md").write_text("# R\n")
    r = _git_repo(tmp_path, "---\nserial: X\n---\n# Syllabus\n\n## Policies\nbody\n")
    serial = stamp(r, vault, today="2026-06-09")
    from lectern.syllabus import build
    build(r)
    html = (r / "syllabus.html").read_text()
    canvas = (r / "syllabus_canvas.html").read_text()
    assert serial in html and "Serial" in html
    assert "<style" not in canvas and "style=" in canvas   # Canvas-safe: inline only
```

- [ ] **Step 3: Run → FAIL.**

- [ ] **Step 4: Implement** `build` + `_read_serial` + `_build_canvas`. Port the inline-style
  logic from `~/git/cecs-378-su26-01-syllabus-10660/gen_canvas.py` verbatim into
  `_build_canvas` (it is existing, working code — the same regex passes: strip
  frontmatter/comments/anchor-nav/`<details>`, inject inline `style=` on structural
  elements using the ink/accent/muted/hair/panel palette + web-safe font stack).

```python
import importlib.resources as _res

_CSS = Path(__file__).parent / "references" / "syllabus.css"
_EISVOGEL = Path(__file__).parent / "references" / "eisvogel.latex"


def _read_serial(pm: Path) -> str:
    m = re.search(r"(?m)^serial:\s*(\S+)", pm.read_text(encoding="utf-8"))
    return m.group(1) if m else ""


def build(repo, pdf: bool = False) -> list[Path]:
    repo = Path(repo)
    pm = repo / primary_md(repo)
    serial = _read_serial(pm)
    html = repo / "syllabus.html"
    footer = f'<footer class="serial">Serial · {serial or "—"}</footer>'
    subprocess.run(
        ["pandoc", str(pm), "--from", "gfm", "--to", "html5", "--standalone",
         "--embed-resources", "--css", str(_CSS),
         "--metadata", "lang=en", f"--include-after-body={_write_tmp(footer)}",
         "-o", str(html)], check=True)
    canvas = repo / "syllabus_canvas.html"
    _build_canvas(pm, canvas, serial)            # ported from gen_canvas.py
    out = [html, canvas]
    if pdf:
        out.append(_build_pdf(repo, html))       # weasyprint/chromium, else clear error
    return out
```

  `_write_tmp(footer)` writes the footer fragment to a NamedTemporaryFile and returns
  its path (pandoc `--include-after-body` needs a file). `_build_pdf` tries
  `weasyprint <html> <pdf>` then `chromium --headless --print-to-pdf`, else
  `raise SystemExit("syllabus: no weasyprint/chromium for --pdf; print the HTML")`.

- [ ] **Step 5: Run → PASS (or SKIP if no pandoc).** **Step 6: Stage** (incl. the two reference files).

---

## Task 5: CLI + `reg-syllabus` wrapper

**Files:** Modify `lectern/syllabus.py`; create `~/bin/reg-syllabus`; add test

- [ ] **Step 1: Failing test**

```python
def test_cli_stamp_then_build(tmp_path, monkeypatch):
    vault = tmp_path / "vault"; (vault / "notes").mkdir(parents=True)
    (vault / "notes" / "syllabus-serial-register.md").write_text("# R\n")
    r = _git_repo(tmp_path, "---\nserial: X\n---\n# S\nbody\n")
    from lectern.syllabus import main
    assert main(["stamp", str(r), "--vault-root", str(vault), "--date", "2026-06-09"]) == 0
    assert "serial:" in (r / "README.md").read_text()
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Implement** `main()`:

```python
def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="reg-syllabus", description="Syllabus stamp + build.")
    sub = p.add_subparsers(dest="cmd", required=True)
    ps = sub.add_parser("stamp", help="Compute + inject the control-number serial; append register row.")
    ps.add_argument("repo", type=Path)
    ps.add_argument("--vault-root", type=Path, required=True)
    ps.add_argument("--revision-of", default=None)
    ps.add_argument("--date", default=None)
    pb = sub.add_parser("build", help="Render HTML + Canvas variant (PDF opt-in).")
    pb.add_argument("repo", type=Path)
    pb.add_argument("--pdf", action="store_true")
    a = p.parse_args(argv)
    if a.cmd == "stamp":
        s = stamp(a.repo, a.vault_root, revision_of=a.revision_of, today=a.date)
        print(f"stamped {a.repo.name}: serial {s}")
    else:
        outs = build(a.repo, pdf=a.pdf)
        print("built: " + ", ".join(o.name for o in outs))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run → PASS.**

- [ ] **Step 5: Create `~/bin/reg-syllabus`:**

```bash
printf '#!/usr/bin/env bash\nexec "/home/anthony/.local/share/personal-assistant/venv/bin/python" -m lectern.syllabus "$@"\n' > ~/bin/reg-syllabus
chmod +x ~/bin/reg-syllabus
```

- [ ] **Step 6: Full suite** `...venv/bin/python -m pytest tests/test_syllabus_serial.py tests/test_syllabus.py -v` — green. **Stage.**

---

## Task 6: First real run (the demo artifact)

- [ ] `reg-syllabus stamp ~/git/cecs-378-su26-01-syllabus-10660 --vault-root <vault>` — confirm the serial in `README.md` frontmatter + footer + a register row.
- [ ] `reg-syllabus build ~/git/cecs-378-su26-01-syllabus-10660` — confirm `syllabus.html` + `syllabus_canvas.html` with the serial footer.
- [ ] Eyeball the HTML; this is the Chair-demo artifact.

> The syllabus repo's own `git commit` (with the stamped serial) is the as-distributed anchor — Anthony commits that in his terminal.

## Self-Review

- **Spec coverage:** serial (repo-tree, strip-self) → T1; stamp frontmatter+footer → T2; register append → T3; build HTML+Canvas+PDF-opt-in + ship templates → T4; CLI+wrapper → T5; first run → T6. All spec sections mapped.
- **Placeholders:** the stub `_append_register` in T2 is explicitly replaced in T3; `_build_canvas` is a verbatim port of named existing code (`gen_canvas.py`) — not a placeholder.
- **Type consistency:** `compute_serial(repo, ref=None)`, `primary_md(repo)`, `stamp(repo, vault_root, revision_of, today)`, `build(repo, pdf)`, `_append_register(vault_root, repo, serial, today, revision_of)`, `main(argv)` used consistently across tasks.
