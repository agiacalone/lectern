# LMS Suite Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add integration documentation + a cross-component integration test (hosted in Lectern, the hub) that enforces the three LMS-suite seam contracts and a coordinated release-compatibility matrix.

**Architecture:** Lectern is the integration home. A new `tests/integration/` suite, gated behind a `suite` pytest marker, validates: the live Lectern→Scriptorium reading-list seam (subprocess, skip-gated), the golden Oracle→Lectern `result.json` seam, and the known-incompatible Scriptorium→Lectern question-bank seam (strict-xfail gap-guard). A `SUITE.md` compatibility matrix plus a `lectern/suite_check.py` checker pin the coordinated release. A single `docs/design/lms-suite-integration.md` documents all three seams.

**Tech Stack:** Python 3.11–3.13, `pytest`, PyYAML (already a dependency via `recon_manifest`), Node.js (for the live Scriptorium seam only).

## Global Constraints

- **Public Python matrix stays green with zero new required dependencies.** The `suite` marker is opt-in (`pytest -m suite`); default `pytest -q` must not run or require these tests' extras (Node, Scriptorium, Oracle).
- **Oracle's private code never enters the public repo or CI.** Its seam is the `result.json` JSON contract only.
- **`reg-*` commands are `~/bin` wrappers** that `exec <venv>/python -m lectern.<module>`. New command = a `lectern/<module>.py` with `main(argv)` + a hand-installed `~/bin` wrapper. Do not add `[project.scripts]`.
- **Golden fixtures carry a provenance header** (producing tool · version · regen command) and a regen entry point; drift is a deliberate, reviewed update.
- **Commit style:** GPG-signed (`git commit -S`); end messages with the two standard trailers (Co-Authored-By + Claude-Session).
- **Repo is canonical; the vault copy is a review mirror.** Edits sync to both.

---

### Task 1: `SUITE.md` compatibility matrix + `suite_check` checker

**Files:**
- Create: `SUITE.md`
- Create: `lectern/suite_check.py`
- Test: `tests/test_suite_check.py`
- Modify: `pyproject.toml` (register `suite` pytest marker)

**Interfaces:**
- Produces:
  - `lectern.suite_check.load_matrix(suite_md: Path) -> dict` — parse the ` ```yaml ` block in `SUITE.md`.
  - `lectern.suite_check.in_range(version: str, spec: str) -> bool` — semver(major,minor,patch) range check; supports `>=`,`>`,`<=`,`<`,`==`, comma-joined clauses (AND).
  - `lectern.suite_check.resolve_version(component: str, *, root: Path | None = None) -> str | None` — installed version or `None` if absent.
  - `@dataclass CheckResult(component: str, installed: str | None, spec: str, ok: bool, skipped: bool)`.
  - `lectern.suite_check.check(matrix: dict, *, roots: dict[str, Path] | None = None) -> list[CheckResult]`.
  - `lectern.suite_check.main(argv: list[str] | None = None) -> int` — prints a table, returns non-zero on any non-skipped mismatch.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_suite_check.py
from pathlib import Path
import textwrap
import pytest
from lectern import suite_check as sc

SUITE_MD = textwrap.dedent('''\
    # LMS Suite
    ```yaml
    suite: "LMS Suite"
    release: "v0.1.0-rc1"
    components:
      lectern:     ">=0.5.0,<0.6"
      scriptorium: ">=0.1.0,<0.2"
      oracle:      ">=0.3.0,<0.4"
    seam_contracts:
      reading_list: 1
      autograde: 1
      question_bank: 0
    ```
    ''')

def test_load_matrix(tmp_path):
    p = tmp_path / "SUITE.md"; p.write_text(SUITE_MD)
    m = sc.load_matrix(p)
    assert m["components"]["lectern"] == ">=0.5.0,<0.6"
    assert m["seam_contracts"]["question_bank"] == 0

@pytest.mark.parametrize("ver,spec,ok", [
    ("0.5.0", ">=0.5.0,<0.6", True),
    ("0.5.9", ">=0.5.0,<0.6", True),
    ("0.6.0", ">=0.5.0,<0.6", False),
    ("0.4.9", ">=0.5.0,<0.6", False),
    ("0.3.2", ">=0.3.0,<0.4", True),
])
def test_in_range(ver, spec, ok):
    assert sc.in_range(ver, spec) is ok

def test_resolve_scriptorium_from_package_json(tmp_path):
    (tmp_path / "package.json").write_text('{"name":"scriptorium","version":"0.1.0"}')
    assert sc.resolve_version("scriptorium", root=tmp_path) == "0.1.0"

def test_resolve_absent_component_returns_none(tmp_path):
    assert sc.resolve_version("oracle", root=tmp_path / "nope") is None

def test_check_flags_out_of_range(tmp_path):
    p = tmp_path / "SUITE.md"; p.write_text(SUITE_MD)
    matrix = sc.load_matrix(p)
    # scriptorium present but too new; oracle absent (skipped); lectern present in-range
    scrip = tmp_path / "scrip"; scrip.mkdir()
    (scrip / "package.json").write_text('{"version":"0.2.5"}')
    results = sc.check(matrix, roots={"scriptorium": scrip, "oracle": tmp_path / "absent"})
    by = {r.component: r for r in results}
    assert by["scriptorium"].ok is False and by["scriptorium"].skipped is False
    assert by["oracle"].skipped is True and by["oracle"].ok is True  # absent → skip, not fail
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_suite_check.py -q`
Expected: FAIL (`ModuleNotFoundError: lectern.suite_check`).

- [ ] **Step 3: Implement `lectern/suite_check.py`**

```python
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
```

- [ ] **Step 4: Create `SUITE.md`** (real version pins read from each repo at write time; ranges below are the format)

```markdown
# LMS Suite — Release Compatibility Matrix

The coordinated release pins of **Lectern · Scriptorium · Oracle**. `reg-suite-check`
(→ `python -m lectern.suite_check`) verifies the installed component versions against
the ranges below; CI runs it via `tests/integration/test_seam_versions.py`.

```yaml
suite: "LMS Suite"
release: "v0.1.0-rc1"
components:
  lectern:     ">=0.5.0,<0.6"
  scriptorium: ">=0.1.0,<0.2"
  oracle:      ">=0.3.0,<0.4"
seam_contracts:
  reading_list: 1     # reg-exam-readinglist CLI arg contract
  autograde:    1     # result.json schema:1
  question_bank: 0    # KNOWN GAP — not a stable contract yet (see lms-suite-integration.md)
```

See [docs/design/lms-suite-integration.md](docs/design/lms-suite-integration.md) for the seam contracts.
```

> When creating `SUITE.md`, replace the three component ranges using each repo's real current version: lectern from its `pyproject.toml`, scriptorium from `~/git/scriptorium/package.json` (currently `0.1.0`), oracle from `/mnt/es2/opt/oracle` version file. Pin `>=<current>,<<next-minor>`.

- [ ] **Step 5: Register the `suite` marker in `pyproject.toml`**

Under `[tool.pytest.ini_options]`, add:

```toml
markers = [
    "suite: cross-component LMS-suite integration tests (opt-in: pytest -m suite)",
]
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/test_suite_check.py -q`
Expected: PASS (all parametrized cases + resolve/check).

- [ ] **Step 7: Install the `~/bin/reg-suite-check` wrapper**

```bash
printf '#!/usr/bin/env bash\nexec "/home/anthony/.local/share/personal-assistant/venv/bin/python" -m lectern.suite_check "$@"\n' > ~/bin/reg-suite-check
chmod +x ~/bin/reg-suite-check
~/bin/reg-suite-check   # smoke: prints the table, exits 0/1
```

- [ ] **Step 8: Commit**

```bash
git add lectern/suite_check.py tests/test_suite_check.py SUITE.md pyproject.toml
git commit -S -m "feat(suite): SUITE.md compatibility matrix + reg-suite-check checker"
```

---

### Task 2: Integration test scaffold + Seam B (Oracle autograde) golden test

**Files:**
- Create: `tests/integration/__init__.py` (empty)
- Create: `tests/integration/conftest.py`
- Create: `tests/integration/fixtures/autograde/result_allpass.json`
- Create: `tests/integration/fixtures/autograde/result_partial.json`
- Create: `tests/integration/fixtures/autograde/result_honorfail.json`
- Create: `tests/integration/fixtures/README.md` (provenance + regen note)
- Create: `tests/integration/test_seam_autograde.py`

**Interfaces:**
- Consumes: `lectern.recon_autograde.parse_result_json(text) -> AutogradeResult | None` (fields: `honor_ok: bool`, `points: int`, `max: int`, `challenges: dict[str, Challenge]`, `commit`). `Challenge(key, passed, points, max)`.
- Produces: `tests/integration/conftest.py::fixtures_dir` fixture → `Path` to `tests/integration/fixtures`.

- [ ] **Step 1: Write fixtures** — three `result.json` files matching the schema:1 contract.

`result_allpass.json`:
```json
{"schema":1,"assignment":"spellbreaker","commit":"a11pa55","honor_ok":true,
 "challenges":{"ward1":{"pass":true,"points":10,"max":10},
               "ward2":{"pass":true,"points":35,"max":35},
               "ward3":{"pass":true,"points":15,"max":15}},
 "points":60,"max":60}
```
`result_partial.json`:
```json
{"schema":1,"assignment":"spellbreaker","commit":"pa2741a","honor_ok":true,
 "challenges":{"ward1":{"pass":true,"points":10,"max":10},
               "ward2":{"pass":false,"points":0,"max":35},
               "ward3":{"pass":true,"points":15,"max":15}},
 "points":25,"max":60}
```
`result_honorfail.json`:
```json
{"schema":1,"assignment":"spellbreaker","commit":"d15h0n0","honor_ok":false,
 "challenges":{"ward1":{"pass":true,"points":10,"max":10}},
 "points":10,"max":60}
```

`tests/integration/fixtures/README.md`:
```markdown
# Integration fixtures — provenance

Golden inputs for the LMS-suite seam tests. **Do not hand-edit; regenerate.**

| Fixture | Producing tool | Contract | Regen |
|---|---|---|---|
| `autograde/result_*.json` | Oracle gradebox `result.json` (schema:1) | autograde v1 | authored by hand from Oracle's documented schema; mirror of `oracle/examples/sample-outputs/result.json` |
| `qbank/scriptorium_bank.md` | Scriptorium `question-bank.js` | question_bank (gap) | `node <scriptorium>/generate.js ... --artifact question-bank` |
| `qbank/lectern_bank.md` | Lectern `reg-qbank` YAML-fenced format | qbank-lectern | hand-authored to lectern/qbank.py schema |
| `readinglist/` | Scriptorium `exam-reading-list-cli.js` | reading_list v1 | `tests/integration/regen.sh` |
```

- [ ] **Step 2: Write `conftest.py`**

```python
from pathlib import Path
import pytest

@pytest.fixture
def fixtures_dir() -> Path:
    return Path(__file__).parent / "fixtures"
```

- [ ] **Step 3: Write the failing test**

```python
# tests/integration/test_seam_autograde.py
"""Seam B (golden): Oracle result.json -> Lectern AutogradeResult contract."""
import json
import pytest
from lectern.recon_autograde import parse_result_json

pytestmark = pytest.mark.suite


def test_allpass_contract(fixtures_dir):
    r = parse_result_json((fixtures_dir / "autograde/result_allpass.json").read_text())
    assert r is not None
    assert r.honor_ok is True
    assert r.points == 60 and r.max == 60
    assert set(r.challenges) == {"ward1", "ward2", "ward3"}
    assert r.challenges["ward2"].passed is True
    assert r.commit == "a11pa55"


def test_partial_zeroes_failed_ward(fixtures_dir):
    r = parse_result_json((fixtures_dir / "autograde/result_partial.json").read_text())
    assert r.points == 25
    assert r.challenges["ward2"].passed is False
    assert r.challenges["ward2"].points == 0


def test_honor_gate_surfaced(fixtures_dir):
    r = parse_result_json((fixtures_dir / "autograde/result_honorfail.json").read_text())
    assert r.honor_ok is False


def test_malformed_json_returns_none():
    assert parse_result_json("{not json") is None
```

- [ ] **Step 4: Run to verify** — both that it's collected under the marker and passes.

Run: `python -m pytest tests/integration/test_seam_autograde.py -m suite -q`
Expected: PASS (4 tests). Then `python -m pytest -q` (default) and confirm these do NOT run.

- [ ] **Step 5: Commit**

```bash
git add tests/integration/
git commit -S -m "test(suite): seam B — Oracle result.json autograde contract (golden)"
```

---

### Task 3: Seam C (question-bank) golden round-trip + gap-guard

**Files:**
- Create: `tests/integration/fixtures/qbank/lectern_bank.md`
- Create: `tests/integration/fixtures/qbank/scriptorium_bank.md`
- Create: `tests/integration/test_seam_qbank.py`

**Interfaces:**
- Consumes: `lectern.qbank.load_bank(path) -> dict[str, Question]`, `lectern.qbank.validate(bank) -> None`.

- [ ] **Step 1: Author `lectern_bank.md`** (lectern YAML-fenced format — two questions)

````markdown
# Demo bank (Lectern format)

```yaml
- id: m01
  type: mc
  points: 2
  stem: "Which key encrypts an RSA message for a recipient?"
  outcomes:
    - { key: a, text: "The sender's private key", credited: false, points: 0 }
    - { key: b, text: "The recipient's public key", credited: true, points: 2 }
    - { key: c, text: "A shared session key", credited: false, points: 0 }
    - { key: none, text: "No answer / multiple marks", credited: false, points: 0 }
- id: t01
  type: tf
  points: 2
  stem: "AES is a symmetric cipher."
  outcomes:
    - { key: "true", text: "True", credited: true, points: 2 }
    - { key: "false", text: "False", credited: false, points: 0 }
```
````

- [ ] **Step 2: Author `scriptorium_bank.md`** (Scriptorium markdown-monolith format — the incompatible shape)

```markdown
# Demo Question Bank

## m01
- type: mc
- difficulty: 1
- prompt: |
    Which key encrypts an RSA message for a recipient?
- options:
    - A. The sender's private key
    - B. The recipient's public key
    - C. A shared session key
- answer: B

## t01
- type: tf
- difficulty: 1
- prompt: |
    AES is a symmetric cipher.
- answer: true
```

- [ ] **Step 3: Write the test (round-trip passes; gap-guard strict-xfails)**

```python
# tests/integration/test_seam_qbank.py
"""Seam C: Lectern bank round-trips; Scriptorium bank does NOT parse (known gap)."""
import pytest
from lectern.qbank import load_bank, validate

pytestmark = pytest.mark.suite


def test_lectern_bank_loads_and_validates(fixtures_dir):
    bank = load_bank(fixtures_dir / "qbank/lectern_bank.md")
    validate(bank)                       # raises on any contract violation
    assert set(bank) == {"m01", "t01"}
    assert bank["m01"].type == "mc"
    assert any(o.credited for o in bank["m01"].outcomes)


@pytest.mark.xfail(strict=True,
                   reason="KNOWN GAP: Scriptorium markdown-monolith bank is not parseable "
                          "by lectern.qbank (expects YAML-fenced). Closing the gap flips this.")
def test_scriptorium_bank_is_not_yet_consumable(fixtures_dir):
    bank = load_bank(fixtures_dir / "qbank/scriptorium_bank.md")
    # If an adapter ever lands, this assert starts passing and the strict xfail fails loudly,
    # forcing this test to be updated to the new contract.
    assert bank and all(q.outcomes for q in bank.values())
```

- [ ] **Step 4: Run to verify**

Run: `python -m pytest tests/integration/test_seam_qbank.py -m suite -q`
Expected: 1 PASS + 1 XFAIL (no failures). Confirm `load_bank` on the lectern fixture genuinely loads — if `validate` rejects it, fix the fixture to match `qbank.py` (do not weaken the test).

- [ ] **Step 5: Commit**

```bash
git add tests/integration/test_seam_qbank.py tests/integration/fixtures/qbank/
git commit -S -m "test(suite): seam C — qbank round-trip + strict-xfail gap-guard"
```

---

### Task 4: Seam A (reading-list) live Scriptorium test

**Files:**
- Create: `tests/integration/fixtures/readinglist/topic_demo/topic_demo_lecture_main.md`
- Create: `tests/integration/fixtures/readinglist/exam_reading_lists.yaml`
- Create: `tests/integration/regen.sh`
- Create: `tests/integration/test_seam_readinglist.py`

**Interfaces:**
- Consumes (external): `node <scriptorium>/exam-reading-list-cli.js --exam-name … --slug … --course … --term … --out <dir> --mains <main.md>`.
- Produces: `tests/integration/_scriptorium.py` helper? No — keep discovery inline in the test.

- [ ] **Step 1: Author a minimal Scriptorium lecture-main fixture** — `topic_demo_lecture_main.md` with frontmatter + at least one `#question`/`#concept` block, valid to Scriptorium's parser. (Model on `~/git/scriptorium/examples/file_systems_abstraction_lecture_main.md`; keep to ~30 lines: frontmatter `title/course/topic-slug/term`, one `#objective`, one `#vocab`, two `#concept [slide:: N]` blocks, one `#question [type:: mc] [answer:: b]` with options.)

- [ ] **Step 2: Author the manifest** `exam_reading_lists.yaml`:

```yaml
course: "CECS 378"
term: su26
lectures_dir: .
exams:
  - { slug: demo_exam, name: "Demo Exam", topics: [topic_demo] }
```

- [ ] **Step 3: Write `regen.sh`** (regenerates the reading-list golden)

```bash
#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
SCRIP="${LECTERN_SCRIPTORIUM_DIR:-$HOME/git/scriptorium}"
OUT="$HERE/fixtures/readinglist/topic_demo/products"
mkdir -p "$OUT"
node "$SCRIP/exam-reading-list-cli.js" --exam-name "Demo Exam" --slug demo_exam \
  --course "CECS 378" --term su26 --out "$OUT" \
  --mains "$HERE/fixtures/readinglist/topic_demo/topic_demo_lecture_main.md"
cp "$OUT/demo_exam_reading_list.md" "$HERE/fixtures/readinglist/demo_exam_reading_list.golden.md"
echo "regenerated golden"
```

- [ ] **Step 4: Write the skip-gated live test**

```python
# tests/integration/test_seam_readinglist.py
"""Seam A (live): Lectern -> Scriptorium reading-list CLI. Skip-gated."""
import os
import re
import shutil
import subprocess
from pathlib import Path
import pytest

pytestmark = pytest.mark.suite

SCRIP = Path(os.environ.get("LECTERN_SCRIPTORIUM_DIR", os.path.expanduser("~/git/scriptorium")))
CLI = SCRIP / "exam-reading-list-cli.js"
HAVE_NODE = shutil.which("node") is not None

requires_scriptorium = pytest.mark.skipif(
    not (HAVE_NODE and CLI.is_file()),
    reason="node + scriptorium exam-reading-list-cli.js not available",
)


def _normalize(md: str) -> str:
    # Drop volatile lines (timestamps, absolute paths) before comparison.
    out = []
    for line in md.splitlines():
        if re.search(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}", line):  # ISO timestamp
            continue
        line = line.replace(str(SCRIP), "<SCRIPTORIUM>")
        out.append(line.rstrip())
    return "\n".join(out).strip()


@requires_scriptorium
def test_readinglist_seam_runs_and_matches_golden(tmp_path, fixtures_dir):
    main = fixtures_dir / "readinglist/topic_demo/topic_demo_lecture_main.md"
    out = tmp_path / "products"; out.mkdir()
    subprocess.run(
        ["node", str(CLI), "--exam-name", "Demo Exam", "--slug", "demo_exam",
         "--course", "CECS 378", "--term", "su26", "--out", str(out),
         "--mains", str(main)],
        check=True, capture_output=True, text=True,
    )
    produced = (out / "demo_exam_reading_list.md")
    assert produced.is_file(), "CLI did not emit the reading list"
    golden = fixtures_dir / "readinglist/demo_exam_reading_list.golden.md"
    assert _normalize(produced.read_text()) == _normalize(golden.read_text())
```

- [ ] **Step 5: Generate the golden + run**

```bash
chmod +x tests/integration/regen.sh && tests/integration/regen.sh
python -m pytest tests/integration/test_seam_readinglist.py -m suite -q
```
Expected: PASS if node+scriptorium present; SKIP otherwise. If the Scriptorium parser rejects the fixture lecture-main, fix the fixture to satisfy the parser (consult `~/git/scriptorium/references/style-guide.md`), then re-run `regen.sh`.

- [ ] **Step 6: Commit**

```bash
git add tests/integration/test_seam_readinglist.py tests/integration/regen.sh tests/integration/fixtures/readinglist/
git commit -S -m "test(suite): seam A — live Scriptorium reading-list seam (skip-gated)"
```

---

### Task 5: `test_seam_versions.py` — wire the compatibility checker

**Files:**
- Create: `tests/integration/test_seam_versions.py`

**Interfaces:**
- Consumes: `lectern.suite_check.load_matrix`, `.check`; repo `SUITE.md`.

- [ ] **Step 1: Write the test**

```python
# tests/integration/test_seam_versions.py
"""Suite version matrix: installed components must satisfy SUITE.md (absent => skip)."""
from pathlib import Path
import pytest
from lectern import suite_check as sc

pytestmark = pytest.mark.suite

SUITE_MD = Path(__file__).resolve().parents[2] / "SUITE.md"


def test_suite_md_parses():
    m = sc.load_matrix(SUITE_MD)
    assert "components" in m and "lectern" in m["components"]


def test_installed_components_satisfy_matrix():
    matrix = sc.load_matrix(SUITE_MD)
    results = sc.check(matrix)
    mismatches = [r for r in results if not r.ok and not r.skipped]
    assert not mismatches, f"version mismatch vs SUITE.md: {mismatches}"
```

- [ ] **Step 2: Run**

Run: `python -m pytest tests/integration/test_seam_versions.py -m suite -q`
Expected: PASS. If `lectern`'s own version is outside the `SUITE.md` range, correct the `SUITE.md` pin (it must reflect reality), not the test.

- [ ] **Step 3: Run the whole suite together**

Run: `python -m pytest -m suite -q`
Expected: all green (reading-list PASS or SKIP; autograde PASS; qbank PASS+XFAIL; versions PASS). Then `python -m pytest -q` and confirm the count is unchanged from before this plan (suite tests excluded by default).

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_seam_versions.py
git commit -S -m "test(suite): seam — version compatibility matrix check"
```

---

### Task 6: Integration documentation + README cross-links

**Files:**
- Create: `docs/design/lms-suite-integration.md`
- Modify: `README.md` (suite section → link the integration doc)

**Interfaces:** none (docs).

- [ ] **Step 1: Write `docs/design/lms-suite-integration.md`** with these sections (content drawn from the spec §2 contracts and the just-built tests/fixtures — every example must match a real fixture):
  1. **Suite map** — Lectern (hub) · Scriptorium · Oracle; language/test stack; license posture (2× MIT, Oracle PolyForm/private); an ASCII hub-and-spoke diagram.
  2. **Seam A — Reading-list** — direction, the `exam-reading-list-cli.js` arg contract, the `exam_reading_lists.yaml` schema, the worked fixture, state ✅, owner (Scriptorium emits, Lectern drives).
  3. **Seam B — Autograde** — the `result.json` schema:1 (challenges/honor_ok/points/max), the `AutogradeResult` mapping, fetch fallbacks, state ✅, note that Oracle's code is private and the JSON is the public surface.
  4. **Seam C — Question-bank gap** — the two divergent formats side by side (link the two fixtures), the `sa`-type coverage difference, why it diverged, impact, and the tracked closure plan; reference the strict-xfail guard.
  5. **Release coupling** — link `SUITE.md` + `reg-suite-check`; explain the contract-version integers.
  6. **Running the integration test** — `pytest -m suite`, the skip-gating, `regen.sh`.
  7. **`SUITE.md` format + version-spec grammar (`suite_check` as a parser)** — document `suite_check.py` as the parser it is: the `SUITE.md` matrix schema (`components`/`seam_contracts` keys), and the **version-constraint mini-language** it parses — operators `>=`, `>`, `<=`, `<`, `==`; comma = logical AND of clauses; versions normalized to a `(major, minor, patch)` semver tuple (extra/missing components truncated/zero-padded); a component absent on disk resolves to `None` → SKIP (not fail). Give the accepted grammar and 2–3 worked `in_range` examples.

- [ ] **Step 1b: Document `suite_check.py` as a parser (module docstring)** — expand the module docstring in `lectern/suite_check.py` to state, in one compact block, the same version-constraint grammar (operators, comma=AND, semver-tuple normalization, absent→None→SKIP) so the parser is self-documenting at the source. Docs-only change; run `python -m pytest tests/test_suite_check.py -q` after to confirm no behavior change.

- [ ] **Step 2: Add a cross-link in `README.md`** — in the suite/overview section, add: `See [docs/design/lms-suite-integration.md](docs/design/lms-suite-integration.md) for how Lectern, Scriptorium, and Oracle integrate.`

- [ ] **Step 3: Verify links resolve** — `grep -o "docs/design/lms-suite-integration.md" README.md` returns a hit; the doc's fixture references exist on disk.

- [ ] **Step 4: Commit**

```bash
git add docs/design/lms-suite-integration.md README.md
git commit -S -m "docs(suite): integration guide — three seam contracts + release coupling"
```

---

### Task 7: Drift fix — `reg-exam-readinglist` wrapper default skill dir

**Files:**
- Modify: `~/bin/reg-exam-readinglist` (live wrapper; **not in the repo** — no commit)

**Interfaces:** none.

- [ ] **Step 1: Patch the default** — change `SKILL_DEFAULT` from `~/.claude/skills/lecture-materials-assistant` to prefer `scriptorium`, keeping the old path as a fallback:

```python
_SCRIP = os.path.expanduser("~/.claude/skills/scriptorium")
_ALIAS = os.path.expanduser("~/.claude/skills/lecture-materials-assistant")
SKILL_DEFAULT = _SCRIP if os.path.isdir(_SCRIP) else _ALIAS
```

- [ ] **Step 2: Smoke-test** — `reg-exam-readinglist --help` runs; if a manifest is handy, a `--no-pdf` dry run resolves the CLI under the new default.

- [ ] **Step 3: Record** — this file is not in the repo; note in the integration doc's follow-ups that the wrapper should be sourced from the repo (spec §10 #2). No commit.

---

### Task 8: CI — opt-in `suite` integration job

**Files:**
- Modify: `.github/workflows/ci.yml` (add a separate job) — or Create `.github/workflows/suite.yml`

**Interfaces:** none.

- [ ] **Step 1: Add a `suite` job** that does not gate the existing matrix:

```yaml
  suite-integration:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with: { path: lectern }
      - uses: actions/checkout@v4
        with: { repository: agiacalone/scriptorium, path: scriptorium }
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - uses: actions/setup-node@v4
        with: { node-version: "20" }
      - run: pip install -e lectern[dev]
      - run: npm --prefix scriptorium ci || npm --prefix scriptorium install
      - name: Run suite integration tests
        working-directory: lectern
        env:
          LECTERN_SCRIPTORIUM_DIR: ${{ github.workspace }}/scriptorium
        run: python -m pytest -m suite -q
```

> Oracle is private and absent here — its seam is golden-fixture only, so `test_seam_versions.py` SKIPs oracle and the autograde test runs from committed fixtures. No secrets required.

- [ ] **Step 2: Validate YAML locally** — `python -c "import yaml,sys; yaml.safe_load(open('.github/workflows/ci.yml'))"` (or the new file) exits 0.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/
git commit -S -m "ci(suite): opt-in cross-component integration job (node + scriptorium)"
```

---

## Self-Review

**Spec coverage:**
- §2 seam contracts → Tasks 2/3/4 (B/C/A) + Task 6 docs. ✓
- §3 integration doc → Task 6. ✓
- §4 shared demo fixture → fixtures created in Tasks 2–4 (live under `tests/integration/fixtures`; the demo-course double-duty is satisfied by these canonical fixtures, with a follow-up to symlink/copy into `examples/` if desired). ✓ (Note: plan keeps fixtures under `tests/integration/fixtures` as the single source; the `examples/cecs-378-demo` wiring is left to the separate Phase-1 demo build to avoid coupling two deliverables.)
- §5 drift guards → Task 7 (wrapper) + provenance headers (Task 2 README). ✓
- §6 SUITE.md + checker → Task 1. ✓
- §7 RC gating → Task 5 (`-m suite` green) + Task 1 checker. ✓
- §8 file list → all files appear across Tasks 1–8. ✓

**Placeholder scan:** No TBD/TODO; all test + impl code is concrete. The one deferred item (closing the qbank gap) is explicitly a tracked follow-up, encoded as a strict-xfail, not a placeholder.

**Type consistency:** `CheckResult`, `in_range`, `resolve_version`, `check`, `load_matrix`, `main` consistent across Tasks 1/5. `parse_result_json`/`AutogradeResult`/`Challenge` match `recon_autograde`. `load_bank`/`validate` match `qbank.py`. `fixtures_dir` fixture defined once (Task 2 conftest) and reused (Tasks 3/4).

**Deviation from spec noted:** spec §4 envisioned the `examples/cecs-378-demo` course as the literal fixture; the plan instead keeps canonical fixtures under `tests/integration/fixtures/` (hermetic, no coupling to the in-progress demo build) and leaves demo-course wiring to Phase 1. This keeps the integration deliverable independently testable per the task-sizing rule.

## Execution Handoff

Per the standing directive ("work until implemented and tested"), execute via **superpowers:subagent-driven-development** — fresh subagent per task, two-stage review between tasks — then run `pytest -m suite` and the default suite to green.
