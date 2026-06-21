# reg-lab-digest (recon Layer-2 writeup digest) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic two-phase `reg-lab-digest emit`/`merge` that turns each student's lab writeup into an advisory `{score, comment}` against a structured rubric, merged into the recon cohort sheet — the LLM judgment runs in the harness via a contract, never in lectern.

**Architecture:** Delegate-via-contract. `emit` reads the recon bundle + a rubric YAML and writes a grading work-list (`digest_tasks.jsonl`) plus the output JSON-Schema. The harness (subagents) scores each task and writes `digest_results.jsonl`. `merge` validates those results, enforces the advisory guardrails deterministically (partial-ward zeroing, total recompute, confidence gating), and writes the scores+comments into `cohort.csv` and the REPORT ➊ table. lectern gains no LLM/API dependency.

**Tech Stack:** Python 3.11+, pyyaml, jsonschema, pytest. Follows the existing `lectern/recon_*.py` module style.

**Design spec:** `docs/design/lab-digest.md` (read it first).

## Global Constraints

- Python ≥ 3.11; deps limited to `pyyaml` + `jsonschema` (already in `pyproject.toml`). **No new runtime deps; no network/LLM calls in lectern.**
- New modules live in `lectern/` as `digest_*.py`; CLI as `lectern/lab_digest.py`; wrapper `reg-lab-digest` mirrors the other `reg-*` wrappers.
- `merge` is **advisory only**: it writes `cohort.csv` + `REPORT.md` ➊ columns and NEVER a scores CSV or `reg-gradebook` input.
- Determinism: `emit` and `merge` are pure functions of their inputs; same inputs ⇒ byte-identical outputs (sort keys, fixed field order).
- Tests use synthetic **Batman-cast** writeup fixtures (no real student text in the repo).

---

## File Structure

- `lectern/recon_docs.py` — **modify**: capture the writeup `body` (Task 1).
- `lectern/recon_record.py` — **modify**: keep `body` out of `repos/*.json` (Task 1).
- `lectern/recon_bundle.py` — **modify**: persist `writeups/<github_id>.md` (Task 1).
- `lectern/digest_rubric.py` — **create**: parse/validate rubric YAML → `Rubric` (Task 2).
- `lectern/digest_schema.py` — **create**: output JSON-Schema + `validate_result` (Task 3).
- `lectern/digest_emit.py` — **create**: bundle + rubric → tasks.jsonl (Task 4).
- `lectern/digest_merge.py` — **create**: results + bundle + rubric → cohort/REPORT (Task 5).
- `lectern/lab_digest.py` — **create**: `emit`/`merge` CLI (Task 6).
- `templates/spellbreaker.rubric.yaml` — **create**: first consumer rubric (Task 7).
- `docs/lab-digest-grader-prompt.md` — **create**: the contract's grader prompt (Task 7).
- `tests/test_digest_*.py` — **create** per task.

---

## Task 1: Persist the writeup body into the recon bundle

The bundle records only an ephemeral `raw_path` (a temp clone, deleted post-run). `emit` needs the text. Capture the body at recon time and persist it to `writeups/<github_id>.md`, keeping it out of the (lean) `repos/*.json`.

**Files:**
- Modify: `lectern/recon_docs.py` (DocRecon + recon_doc)
- Modify: `lectern/recon_record.py` (record_to_dict)
- Modify: `lectern/recon_bundle.py` (write_bundle)
- Test: `tests/test_recon_writeup_persist.py`

**Interfaces:**
- Produces: `DocRecon.body: str` (full writeup body, frontmatter-stripped); `recon_bundle.write_bundle` additionally writes `<out>/writeups/<github_id>.md` for each record whose first present doc has a body. `record_to_dict` excludes `body` from `docs`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_recon_writeup_persist.py
import json
from pathlib import Path
from lectern.recon_docs import recon_doc
from lectern.recon_record import RepoRecord, record_to_dict
from lectern.recon_bundle import write_bundle

def test_recon_doc_captures_body(tmp_path):
    p = tmp_path / "WRITEUP.md"
    p.write_text("---\nhonor: X\n---\n# Grimoire\nWard I broke via ECB determinism.\n")
    d = recon_doc(p, label="grimoire")
    assert d.present and "ECB determinism" in d.body
    assert "honor: X" not in d.body  # frontmatter stripped

def test_bundle_persists_writeup_and_keeps_json_lean(tmp_path):
    p = tmp_path / "WRITEUP.md"
    p.write_text("---\nhonor: X\n---\n# Grimoire\nWard I notes.\n")
    rec = RepoRecord(github_id="harleyq", student="Harley Quinn", repo="r",
                     docs={"grimoire": recon_doc(p, label="grimoire")})
    write_bundle([rec], tmp_path / "out", lab_name="L", total_points=30)
    assert (tmp_path / "out" / "writeups" / "harleyq.md").read_text().strip() == "# Grimoire\nWard I notes."
    j = json.loads((tmp_path / "out" / "repos" / "harleyq.json").read_text())
    assert "body" not in j["docs"]["grimoire"]   # body not bloating the JSON
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_recon_writeup_persist.py -v`
Expected: FAIL (`DocRecon` has no `body`; no `writeups/` dir).

- [ ] **Step 3: Add `body` to DocRecon + capture it**

In `lectern/recon_docs.py`, add the field and populate it (frontmatter already stripped into `body` variable):

```python
@dataclass
class DocRecon:
    label: str
    present: bool = False
    frontmatter: dict = field(default_factory=dict)
    sections: list = field(default_factory=list)
    sources: int = 0
    word_count: int = 0
    raw_path: str = ""
    body: str = ""
```

At the end of `recon_doc`, pass `body=body.strip()` into the returned `DocRecon(...)`.

- [ ] **Step 4: Keep body out of repos/*.json + persist writeups/**

In `lectern/recon_record.py`, change the docs serialization in `record_to_dict` to drop `body`:

```python
        "docs": {k: {kk: vv for kk, vv in asdict(v).items() if kk != "body"}
                 for k, v in r.docs.items()},
```

In `lectern/recon_bundle.py` `write_bundle`, after writing `repos/`, add:

```python
    wdir = out / "writeups"
    for r in records:
        doc = next((d for d in r.docs.values() if d.present and d.body), None)
        if doc:
            wdir.mkdir(parents=True, exist_ok=True)
            (wdir / f"{r.github_id}.md").write_text(doc.body, encoding="utf-8")
```

(`record_from_dict` already tolerates a missing `body` because `DocRecon(**v)` gets the default; verify the kept keys still match the dataclass fields.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_recon_writeup_persist.py tests/test_recon*.py -v`
Expected: PASS (and no regression in existing recon tests).

- [ ] **Step 6: Commit**

```bash
git add lectern/recon_docs.py lectern/recon_record.py lectern/recon_bundle.py tests/test_recon_writeup_persist.py
git commit -S -m "recon: persist writeup body to bundle/writeups/<id>.md (digest precondition)"
```

---

## Task 2: `digest_rubric` — parse + validate the rubric YAML

**Files:**
- Create: `lectern/digest_rubric.py`
- Test: `tests/test_digest_rubric.py`

**Interfaces:**
- Produces:
  - `@dataclass Section(key:str, label:str, max:int, anchors:dict, requires_cleared:str|None=None)`
  - `@dataclass Rubric(lab:str, total:int, comment_max_chars:int, sections:list[Section], bonus:list[Section], cap:int)`
  - `load_rubric(path: Path) -> Rubric` — raises `SystemExit` on invalid rubric.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_digest_rubric.py
import pytest
from pathlib import Path
from lectern.digest_rubric import load_rubric

GOOD = """
lab: "Spellbreaker"
total: 30
comment_max_chars: 140
sections:
  - {key: ward1, label: "Ward I", max: 5,  requires_cleared: ward1, anchors: {strong: a, adequate: b, weak: c, missing: d}}
  - {key: ward2, label: "Ward II", max: 10, requires_cleared: ward2, anchors: {strong: a, adequate: b, weak: c, missing: d}}
  - {key: ward3, label: "Ward III", max: 9, requires_cleared: ward3, anchors: {strong: a, adequate: b, weak: c, missing: d}}
  - {key: craft, label: "Craft", max: 6, anchors: {strong: a, adequate: b, weak: c, missing: d}}
bonus:
  - {key: omega, label: "OMEGA", max: 4, requires_cleared: ward4, anchors: {strong: a, adequate: b, weak: c, missing: d}}
cap: 30
"""

def _write(tmp_path, text):
    p = tmp_path / "r.yaml"; p.write_text(text); return p

def test_loads_valid_rubric(tmp_path):
    r = load_rubric(_write(tmp_path, GOOD))
    assert r.total == 30 and r.cap == 30 and r.comment_max_chars == 140
    assert [s.key for s in r.sections] == ["ward1","ward2","ward3","craft"]
    assert r.sections[0].requires_cleared == "ward1" and r.sections[3].requires_cleared is None
    assert [s.key for s in r.bonus] == ["omega"]

def test_rejects_core_sum_ne_total(tmp_path):
    bad = GOOD.replace("total: 30", "total: 29")
    with pytest.raises(SystemExit):
        load_rubric(_write(tmp_path, bad))

def test_rejects_duplicate_keys(tmp_path):
    bad = GOOD.replace("key: craft", "key: ward1")
    with pytest.raises(SystemExit):
        load_rubric(_write(tmp_path, bad))

def test_rejects_negative_max(tmp_path):
    bad = GOOD.replace("max: 6", "max: -1")
    with pytest.raises(SystemExit):
        load_rubric(_write(tmp_path, bad))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_digest_rubric.py -v`
Expected: FAIL (`No module named 'lectern.digest_rubric'`).

- [ ] **Step 3: Write minimal implementation**

```python
# lectern/digest_rubric.py
"""Parse + validate a lab digest rubric YAML into a Rubric (deterministic)."""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
import sys
import yaml

@dataclass
class Section:
    key: str; label: str; max: int
    anchors: dict = field(default_factory=dict)
    requires_cleared: str | None = None

@dataclass
class Rubric:
    lab: str; total: int; comment_max_chars: int
    sections: list[Section]; bonus: list[Section]; cap: int

def _section(d: dict) -> Section:
    return Section(key=str(d["key"]), label=str(d.get("label", d["key"])),
                   max=int(d["max"]), anchors=dict(d.get("anchors") or {}),
                   requires_cleared=(str(d["requires_cleared"]) if d.get("requires_cleared") else None))

def load_rubric(path: Path) -> Rubric:
    data = yaml.safe_load(Path(path).read_text()) or {}
    for k in ("lab", "total", "sections"):
        if k not in data:
            sys.exit(f"digest_rubric: missing required key '{k}'")
    sections = [_section(s) for s in data["sections"]]
    bonus = [_section(s) for s in (data.get("bonus") or [])]
    total = int(data["total"])
    cap = int(data.get("cap", total))
    keys = [s.key for s in sections + bonus]
    if len(keys) != len(set(keys)):
        sys.exit("digest_rubric: duplicate section keys")
    for s in sections + bonus:
        if s.max < 0:
            sys.exit(f"digest_rubric: negative max on '{s.key}'")
    if sum(s.max for s in sections) != total:
        sys.exit(f"digest_rubric: core section maxes ({sum(s.max for s in sections)}) != total ({total})")
    if cap < total:
        sys.exit("digest_rubric: cap must be >= total")
    return Rubric(lab=str(data["lab"]), total=total,
                  comment_max_chars=int(data.get("comment_max_chars", 140)),
                  sections=sections, bonus=bonus, cap=cap)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_digest_rubric.py -v`
Expected: PASS (all four).

- [ ] **Step 5: Commit**

```bash
git add lectern/digest_rubric.py tests/test_digest_rubric.py
git commit -S -m "digest_rubric: parse + validate rubric YAML"
```

---

## Task 3: `digest_schema` — output JSON-Schema + validator

**Files:**
- Create: `lectern/digest_schema.py`
- Test: `tests/test_digest_schema.py`

**Interfaces:**
- Consumes: `Rubric` (Task 2).
- Produces:
  - `result_schema(rubric: Rubric) -> dict` — JSON-Schema for one result object.
  - `validate_result(obj: dict, rubric: Rubric) -> list[str]` — returns a list of error strings (empty == valid). Never raises.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_digest_schema.py
from lectern.digest_rubric import load_rubric
from lectern.digest_schema import result_schema, validate_result
from tests.test_digest_rubric import GOOD, _write

def _rubric(tmp_path): return load_rubric(_write(tmp_path, GOOD))

def test_valid_result_passes(tmp_path):
    r = _rubric(tmp_path)
    obj = {"github_id":"harleyq","sections":{"ward1":5,"ward2":10,"ward3":9,"craft":6},
           "bonus":{"omega":4},"total":30,"comment":"strong","confidence":"high","abstain":False}
    assert validate_result(obj, r) == []

def test_missing_field_flagged(tmp_path):
    r = _rubric(tmp_path)
    obj = {"github_id":"x","sections":{"ward1":5,"ward2":10,"ward3":9,"craft":6}}  # no comment/confidence
    assert validate_result(obj, r)  # non-empty error list

def test_bad_confidence_enum_flagged(tmp_path):
    r = _rubric(tmp_path)
    obj = {"github_id":"x","sections":{"ward1":5,"ward2":10,"ward3":9,"craft":6},
           "bonus":{"omega":0},"total":24,"comment":"ok","confidence":"medium-ish","abstain":False}
    assert validate_result(obj, r)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_digest_schema.py -v`
Expected: FAIL (module missing).

- [ ] **Step 3: Write minimal implementation**

```python
# lectern/digest_schema.py
"""Output contract for one digest result + a non-raising validator."""
from __future__ import annotations
from jsonschema import Draft202012Validator
from lectern.digest_rubric import Rubric

def result_schema(rubric: Rubric) -> dict:
    sec_keys = [s.key for s in rubric.sections]
    bonus_keys = [s.key for s in rubric.bonus]
    return {
        "type": "object",
        "required": ["github_id", "sections", "total", "comment", "confidence", "abstain"],
        "additionalProperties": False,
        "properties": {
            "github_id": {"type": "string", "minLength": 1},
            "sections": {"type": "object", "required": sec_keys, "additionalProperties": False,
                         "properties": {k: {"type": "integer", "minimum": 0} for k in sec_keys}},
            "bonus": {"type": "object", "additionalProperties": False,
                      "properties": {k: {"type": "integer", "minimum": 0} for k in bonus_keys}},
            "total": {"type": "integer", "minimum": 0},
            "comment": {"type": "string"},
            "confidence": {"enum": ["high", "medium", "low"]},
            "abstain": {"type": "boolean"},
        },
    }

def validate_result(obj: dict, rubric: Rubric) -> list[str]:
    v = Draft202012Validator(result_schema(rubric))
    return [f"{'/'.join(map(str, e.path)) or '<root>'}: {e.message}"
            for e in sorted(v.iter_errors(obj), key=lambda e: list(e.path))]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_digest_schema.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add lectern/digest_schema.py tests/test_digest_schema.py
git commit -S -m "digest_schema: result JSON-Schema + non-raising validator"
```

---

## Task 4: `digest_emit` — bundle + rubric → tasks.jsonl

**Files:**
- Create: `lectern/digest_emit.py`
- Test: `tests/test_digest_emit.py`

**Interfaces:**
- Consumes: `load_rubric` (Task 2), `result_schema` (Task 3), the bundle layout (`repos/<id>.json` + `writeups/<id>.md`).
- Produces: `emit(bundle_dir: Path, rubric: Rubric, out_tasks: Path) -> int` — writes one JSON object per line to `out_tasks` and `digest.schema.json` beside it; returns the number of NON-skipped tasks. Each task object: `{github_id, student, writeup_text, autograde:{points,cleared,honor_ok}, skip:bool, rubric, schema}`.
- `cleared` = sorted list of challenge keys with `passed == true`. `skip == true` iff `honor_ok` is false OR no writeup body exists.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_digest_emit.py
import json
from pathlib import Path
from lectern.digest_rubric import load_rubric
from lectern.digest_emit import emit
from tests.test_digest_rubric import GOOD, _write

def _bundle(tmp_path):
    b = tmp_path / "bundle"; (b / "repos").mkdir(parents=True); (b / "writeups").mkdir()
    # Harley: full clear, honor ok, has writeup
    (b / "repos" / "harleyq.json").write_text(json.dumps({
        "github_id":"harleyq","student":"Harley Quinn","repo":"r",
        "autograde":{"honor_ok":True,"points":70,"max":70,"all_failed":False,"challenges":{
            "ward1":{"key":"ward1","passed":True,"points":10,"max":10},
            "ward2":{"key":"ward2","passed":True,"points":35,"max":35},
            "ward3":{"key":"ward3","passed":True,"points":15,"max":15},
            "ward4":{"key":"ward4","passed":True,"points":10,"max":10}}},
        "docs":{},"git":None,"links":{}}))
    (b / "writeups" / "harleyq.md").write_text("# Grimoire\nWard I broke via ECB determinism.")
    # Joker: honor fail, no writeup -> skip
    (b / "repos" / "joker.json").write_text(json.dumps({
        "github_id":"joker","student":"The Joker","repo":"r",
        "autograde":{"honor_ok":False,"points":0,"max":70,"all_failed":True,"challenges":{}},
        "docs":{},"git":None,"links":{}}))
    return b

def test_emit_writes_tasks_and_schema(tmp_path):
    r = load_rubric(_write(tmp_path, GOOD))
    out = tmp_path / "tasks.jsonl"
    n = emit(_bundle(tmp_path), r, out)
    assert n == 1  # only Harley is gradeable
    assert (out.parent / "digest.schema.json").exists()
    tasks = {json.loads(l)["github_id"]: json.loads(l) for l in out.read_text().splitlines()}
    assert tasks["harleyq"]["skip"] is False
    assert tasks["harleyq"]["autograde"]["cleared"] == ["ward1","ward2","ward3","ward4"]
    assert "ECB determinism" in tasks["harleyq"]["writeup_text"]
    assert tasks["joker"]["skip"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_digest_emit.py -v`
Expected: FAIL (module missing).

- [ ] **Step 3: Write minimal implementation**

```python
# lectern/digest_emit.py
"""emit: recon bundle + rubric -> digest_tasks.jsonl + digest.schema.json (deterministic)."""
from __future__ import annotations
import json
from dataclasses import asdict
from pathlib import Path
from lectern.digest_rubric import Rubric
from lectern.digest_schema import result_schema

def _rubric_dict(r: Rubric) -> dict:
    return {"lab": r.lab, "total": r.total, "comment_max_chars": r.comment_max_chars, "cap": r.cap,
            "sections": [asdict(s) for s in r.sections], "bonus": [asdict(s) for s in r.bonus]}

def emit(bundle_dir: Path, rubric: Rubric, out_tasks: Path) -> int:
    bundle_dir = Path(bundle_dir)
    schema = result_schema(rubric)
    (out_tasks.parent).mkdir(parents=True, exist_ok=True)
    (out_tasks.parent / "digest.schema.json").write_text(json.dumps(schema, indent=2, sort_keys=True))
    rd = _rubric_dict(rubric)
    n = 0
    lines = []
    for jf in sorted((bundle_dir / "repos").glob("*.json")):
        rec = json.loads(jf.read_text())
        gid = rec["github_id"]
        ag = rec.get("autograde") or {}
        honor_ok = bool(ag.get("honor_ok"))
        cleared = sorted(k for k, c in (ag.get("challenges") or {}).items() if c.get("passed"))
        wpath = bundle_dir / "writeups" / f"{gid}.md"
        body = wpath.read_text(encoding="utf-8") if wpath.exists() else ""
        skip = (not honor_ok) or (not body.strip())
        task = {"github_id": gid, "student": rec.get("student", gid),
                "writeup_text": body, "skip": skip,
                "autograde": {"points": int(ag.get("points", 0)), "cleared": cleared, "honor_ok": honor_ok},
                "rubric": rd, "schema": schema}
        lines.append(json.dumps(task, sort_keys=True))
        if not skip:
            n += 1
    out_tasks.write_text("\n".join(lines) + ("\n" if lines else ""))
    return n
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_digest_emit.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add lectern/digest_emit.py tests/test_digest_emit.py
git commit -S -m "digest_emit: bundle + rubric -> grading work-list + schema"
```

---

## Task 5: `digest_merge` — results + bundle + rubric → cohort/REPORT

The guardrail core. Validates each result, enforces partial-ward zeroing from the **autograde** truth, recomputes the authoritative total (capped), gates on confidence, and writes advisory columns. Never writes a scores CSV.

**Files:**
- Create: `lectern/digest_merge.py`
- Test: `tests/test_digest_merge.py`

**Interfaces:**
- Consumes: `validate_result` (Task 3), `Rubric` (Task 2), the bundle (`repos/*.json` for autograde `cleared`), `cohort.csv`.
- Produces:
  - `@dataclass Merged(github_id:str, score:int|None, comment:str, flags:list[str])`
  - `merge_results(bundle_dir: Path, rubric: Rubric, results_path: Path) -> list[Merged]` — pure (returns the merged rows; no file writes).
  - `apply_to_cohort(bundle_dir: Path, merged: list[Merged]) -> None` — adds/updates `writeup_score`, `writeup_comment`, `writeup_flags` columns in `cohort.csv` (preserving existing columns + row order).
- A `score` of `None` means withheld (low-confidence/abstain/invalid) → `needs-human-read`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_digest_merge.py
import csv, json
from pathlib import Path
from lectern.digest_rubric import load_rubric
from lectern.digest_merge import merge_results, apply_to_cohort
from tests.test_digest_rubric import GOOD, _write
from tests.test_digest_emit import _bundle

def _cohort(b):
    p = b / "cohort.csv"
    with p.open("w", newline="") as f:
        w = csv.writer(f); w.writerow(["github_id","student","points"])
        w.writerow(["harleyq","Harley Quinn","70"]); w.writerow(["riddler","The Riddler","55"])
    return p

def _bundle2(tmp_path):
    b = _bundle(tmp_path)
    # Riddler: cleared I+II+OMEGA, NOT ward3 -> ward3 must be forced to 0 on merge
    (b / "repos" / "riddler.json").write_text(json.dumps({
        "github_id":"riddler","student":"The Riddler","repo":"r",
        "autograde":{"honor_ok":True,"points":55,"max":70,"all_failed":False,"challenges":{
            "ward1":{"key":"ward1","passed":True,"points":10,"max":10},
            "ward2":{"key":"ward2","passed":True,"points":35,"max":35},
            "ward3":{"key":"ward3","passed":False,"points":0,"max":15},
            "ward4":{"key":"ward4","passed":True,"points":10,"max":10}}},
        "docs":{},"git":None,"links":{}}))
    (b / "writeups" / "riddler.md").write_text("# Grimoire\nplausible but ward3 not done")
    return b

def test_partial_ward_zeroing_and_total_recompute(tmp_path):
    r = load_rubric(_write(tmp_path, GOOD))
    b = _bundle2(tmp_path)
    res = b / "results.jsonl"
    res.write_text("\n".join([
      # Riddler: model WRONGLY credits ward3=9; merge must zero it (ward3 not cleared)
      json.dumps({"github_id":"riddler","sections":{"ward1":4,"ward2":8,"ward3":9,"craft":3},
                  "bonus":{"omega":4},"total":28,"comment":"ok","confidence":"high","abstain":False}),
      # Harley: clean full
      json.dumps({"github_id":"harleyq","sections":{"ward1":5,"ward2":10,"ward3":9,"craft":6},
                  "bonus":{"omega":4},"total":34,"comment":"strong","confidence":"high","abstain":False}),
    ]))
    merged = {m.github_id: m for m in merge_results(b, r, res)}
    # Riddler: ward3 forced 0 -> 4+8+0+3 + omega 4 = 19 (capped at 30)
    assert merged["riddler"].score == 19
    assert "partial-ward-zeroed:ward3" in merged["riddler"].flags
    # Harley: 5+10+9+6 + 4 = 34 -> capped to 30
    assert merged["harleyq"].score == 30

def test_low_confidence_withholds_score(tmp_path):
    r = load_rubric(_write(tmp_path, GOOD)); b = _bundle2(tmp_path)
    res = b / "results.jsonl"
    res.write_text(json.dumps({"github_id":"harleyq","sections":{"ward1":5,"ward2":10,"ward3":9,"craft":6},
                  "bonus":{"omega":0},"total":30,"comment":"unsure","confidence":"low","abstain":False}))
    merged = {m.github_id: m for m in merge_results(b, r, res)}
    assert merged["harleyq"].score is None and "needs-human-read" in merged["harleyq"].flags

def test_apply_to_cohort_adds_columns(tmp_path):
    r = load_rubric(_write(tmp_path, GOOD)); b = _bundle2(tmp_path); _cohort(b)
    res = b / "results.jsonl"
    res.write_text(json.dumps({"github_id":"harleyq","sections":{"ward1":5,"ward2":10,"ward3":9,"craft":6},
                  "bonus":{"omega":4},"total":34,"comment":"strong","confidence":"high","abstain":False}))
    apply_to_cohort(b, merge_results(b, r, res))
    rows = {row["github_id"]: row for row in csv.DictReader((b / "cohort.csv").open())}
    assert rows["harleyq"]["writeup_score"] == "30"
    assert rows["harleyq"]["writeup_comment"] == "strong"
    assert rows["riddler"]["writeup_score"] == ""  # no result -> blank, untouched
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_digest_merge.py -v`
Expected: FAIL (module missing).

- [ ] **Step 3: Write minimal implementation**

```python
# lectern/digest_merge.py
"""merge: validated digest results -> advisory cohort columns. Never writes scores/gradebook."""
from __future__ import annotations
import csv, json
from dataclasses import dataclass, field
from pathlib import Path
from lectern.digest_rubric import Rubric
from lectern.digest_schema import validate_result

@dataclass
class Merged:
    github_id: str
    score: int | None
    comment: str
    flags: list[str] = field(default_factory=list)

def _cleared(bundle_dir: Path, gid: str) -> set[str]:
    jf = bundle_dir / "repos" / f"{gid}.json"
    if not jf.exists():
        return set()
    ag = (json.loads(jf.read_text()).get("autograde") or {})
    return {k for k, c in (ag.get("challenges") or {}).items() if c.get("passed")}

def merge_results(bundle_dir: Path, rubric: Rubric, results_path: Path) -> list[Merged]:
    bundle_dir = Path(bundle_dir)
    out: list[Merged] = []
    for line in Path(results_path).read_text().splitlines():
        if not line.strip():
            continue
        obj = json.loads(line)
        gid = obj.get("github_id", "?")
        errs = validate_result(obj, rubric)
        if errs:
            out.append(Merged(gid, None, "", ["digest:invalid"] + errs[:1]))
            continue
        flags: list[str] = []
        cleared = _cleared(bundle_dir, gid)
        secs = dict(obj["sections"]); bonus = dict(obj.get("bonus") or {})
        for s in rubric.sections:
            if s.requires_cleared and s.requires_cleared not in cleared and secs.get(s.key, 0):
                secs[s.key] = 0; flags.append(f"partial-ward-zeroed:{s.key}")
        for s in rubric.bonus:
            if s.requires_cleared and s.requires_cleared not in cleared and bonus.get(s.key, 0):
                bonus[s.key] = 0; flags.append(f"partial-ward-zeroed:{s.key}")
        total = min(rubric.cap, sum(secs.values()) + sum(bonus.values()))
        if obj.get("total") != total:
            flags.append("digest:total-drift")
        comment = obj["comment"][:rubric.comment_max_chars]
        if obj.get("abstain") or obj.get("confidence") == "low":
            out.append(Merged(gid, None, comment, flags + ["needs-human-read"]))
        else:
            out.append(Merged(gid, total, comment, flags))
    return out

_NEW_COLS = ["writeup_score", "writeup_comment", "writeup_flags"]

def apply_to_cohort(bundle_dir: Path, merged: list[Merged]) -> None:
    path = Path(bundle_dir) / "cohort.csv"
    rows = list(csv.DictReader(path.open()))
    fields = list(rows[0].keys()) if rows else ["github_id"]
    for c in _NEW_COLS:
        if c not in fields:
            fields.append(c)
    by_id = {m.github_id: m for m in merged}
    for row in rows:
        m = by_id.get(row["github_id"])
        row["writeup_score"] = "" if (m is None or m.score is None) else str(m.score)
        row["writeup_comment"] = m.comment if m else ""
        row["writeup_flags"] = ";".join(m.flags) if m else ""
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader(); w.writerows(rows)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_digest_merge.py -v`
Expected: PASS (all three).

- [ ] **Step 5: Commit**

```bash
git add lectern/digest_merge.py tests/test_digest_merge.py
git commit -S -m "digest_merge: validate + partial-ward zero + total recompute + advisory cohort cols"
```

---

## Task 6: `lab_digest` CLI + `reg-lab-digest` wrapper

**Files:**
- Create: `lectern/lab_digest.py`
- Modify: `install.sh` (register the `reg-lab-digest` wrapper, mirroring the other `reg-*` entries)
- Test: `tests/test_lab_digest_cli.py`

**Interfaces:**
- Consumes: `emit` (Task 4), `merge_results` + `apply_to_cohort` (Task 5), `load_rubric` (Task 2).
- Produces: `main(argv: list[str] | None = None) -> int` with subcommands:
  - `emit --bundle <dir> --rubric <yaml> --out <tasks.jsonl>`
  - `merge --bundle <dir> --rubric <yaml> --results <results.jsonl>`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_lab_digest_cli.py
import csv, json
from pathlib import Path
from lectern.lab_digest import main
from tests.test_digest_rubric import GOOD, _write
from tests.test_digest_merge import _bundle2, _cohort

def test_cli_emit_then_merge(tmp_path):
    rub = _write(tmp_path, GOOD); b = _bundle2(tmp_path); _cohort(b)
    tasks = tmp_path / "tasks.jsonl"
    assert main(["emit","--bundle",str(b),"--rubric",str(rub),"--out",str(tasks)]) == 0
    assert tasks.exists() and (tasks.parent / "digest.schema.json").exists()
    res = b / "results.jsonl"
    res.write_text(json.dumps({"github_id":"harleyq","sections":{"ward1":5,"ward2":10,"ward3":9,"craft":6},
                  "bonus":{"omega":4},"total":34,"comment":"strong","confidence":"high","abstain":False}))
    assert main(["merge","--bundle",str(b),"--rubric",str(rub),"--results",str(res)]) == 0
    rows = {r["github_id"]: r for r in csv.DictReader((b / "cohort.csv").open())}
    assert rows["harleyq"]["writeup_score"] == "30"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_lab_digest_cli.py -v`
Expected: FAIL (module missing).

- [ ] **Step 3: Write minimal implementation**

```python
# lectern/lab_digest.py
"""reg-lab-digest — emit a grading work-list / merge graded results (advisory, deterministic)."""
from __future__ import annotations
import argparse
from pathlib import Path
from lectern.digest_rubric import load_rubric
from lectern.digest_emit import emit
from lectern.digest_merge import merge_results, apply_to_cohort

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="reg-lab-digest",
        description="Layer-2 writeup digest: emit a grading work-list, merge graded results.")
    sub = p.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("emit"); e.add_argument("--bundle", type=Path, required=True)
    e.add_argument("--rubric", type=Path, required=True); e.add_argument("--out", type=Path, required=True)
    m = sub.add_parser("merge"); m.add_argument("--bundle", type=Path, required=True)
    m.add_argument("--rubric", type=Path, required=True); m.add_argument("--results", type=Path, required=True)
    a = p.parse_args(argv)
    rubric = load_rubric(a.rubric)
    if a.cmd == "emit":
        n = emit(a.bundle, rubric, a.out)
        print(f"digest: {n} task(s) to grade -> {a.out}")
        return 0
    merged = merge_results(a.bundle, rubric, a.results)
    apply_to_cohort(a.bundle, merged)
    scored = sum(1 for x in merged if x.score is not None)
    held = sum(1 for x in merged if x.score is None)
    print(f"digest: merged {scored} scored, {held} withheld -> {a.bundle}/cohort.csv")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
```

Then in `install.sh`, add a `reg-lab-digest` wrapper line next to the other `reg-*` wrappers, pointing at `python -m lectern.lab_digest`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_lab_digest_cli.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add lectern/lab_digest.py install.sh tests/test_lab_digest_cli.py
git commit -S -m "lab_digest: reg-lab-digest emit/merge CLI + wrapper"
```

---

## Task 7: First consumer — Spellbreaker rubric + grader-prompt doc

**Files:**
- Create: `templates/spellbreaker.rubric.yaml`
- Create: `docs/lab-digest-grader-prompt.md`
- Test: `tests/test_spellbreaker_rubric.py`

**Interfaces:**
- Consumes: `load_rubric` (Task 2).
- Produces: a validated `templates/spellbreaker.rubric.yaml` (the Lab 1 grimoire rubric — 30 pts, sections ward1/ward2/ward3/craft + omega bonus) and the harness grader-prompt contract.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_spellbreaker_rubric.py
from pathlib import Path
from lectern.digest_rubric import load_rubric

def test_spellbreaker_rubric_valid():
    r = load_rubric(Path("templates/spellbreaker.rubric.yaml"))
    assert r.total == 30 and r.cap == 30
    assert {s.key for s in r.sections} == {"ward1","ward2","ward3","craft"}
    assert r.sections[0].requires_cleared == "ward1"
    assert [s.key for s in r.bonus] == ["omega"] and r.bonus[0].requires_cleared == "ward4"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_spellbreaker_rubric.py -v`
Expected: FAIL (file missing).

- [ ] **Step 3: Write the rubric + grader prompt**

Create `templates/spellbreaker.rubric.yaml` with `lab`, `total: 30`, `comment_max_chars: 140`, the four core sections (ward1=5/ward2=10/ward3=9/craft=6, each with `requires_cleared` where applicable and the Strong/Adequate/Weak/Missing anchor text copied from `classes/378-478/labs/378-spellbreaker/spellbreaker_lab_grading_rubric.md`), a `bonus` omega=4 with `requires_cleared: ward4`, and `cap: 30`. Create `docs/lab-digest-grader-prompt.md` documenting the harness contract: read `digest_tasks.jsonl`, score each non-skip task's `writeup_text` against the embedded `rubric.anchors` (mechanism-over-outcome), emit one `digest.schema.json`-conforming object per line to `digest_results.jsonl`; abstain (confidence:low) rather than guess.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_spellbreaker_rubric.py -v`
Expected: PASS.

- [ ] **Step 5: Run the full suite + commit**

Run: `python -m pytest -q`
Expected: all pass.

```bash
git add templates/spellbreaker.rubric.yaml docs/lab-digest-grader-prompt.md tests/test_spellbreaker_rubric.py
git commit -S -m "digest: Spellbreaker rubric YAML + harness grader-prompt contract"
```

---

## Self-Review

- **Spec coverage:** rubric YAML (T2) · output schema (T3) · emit work-list + honor/skip short-circuit (T4) · merge with partial-ward zeroing + total recompute + confidence gate + advisory-only cohort write (T5) · two-phase CLI (T6) · writeup-body persistence gap (T1) · first consumer rubric + grader prompt (T7). REPORT ➊-column fill is folded into `apply_to_cohort` (cohort.csv is the REPORT's data source) — if a separate REPORT.md rewrite is wanted later, it's an additive follow-on, not blocking.
- **Placeholder scan:** none — every code step carries full code; T7's rubric content is sourced verbatim from the existing markdown rubric.
- **Type consistency:** `Rubric`/`Section` (T2) consumed unchanged by T3–T7; `Merged` (T5) consumed by T6; bundle JSON shape matches `record_to_dict` (verified against a real bundle).

## Execution Handoff

Two execution options — subagent-driven (fresh subagent per task, review between) or inline (executing-plans with checkpoints).
