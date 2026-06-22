# `reg-lab-report` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a lectern Layer-3 verb `reg-lab-report` that deterministically renders the canonical instructor lab report (facts + scores + agate graphs + grading recommendations) and, separately gated, delivers sanitized GPG-signed feedback to each student's repo `feedback` branch.

**Architecture:** Pure-deterministic offline Python module `lectern.lab_report` with two argparse subcommands — `render` (read-only report from the recon bundle + digest-merged cohort + gradebook standing) and `deliver` (outward-facing signed feedback push, `--dry-run` default). The only LLM touchpoint stays the existing digest contract, extended here with a `student_comment` field. GitHub/git ops go through injected callbacks (mockable), matching lectern's `recon` pattern.

**Tech Stack:** Python 3.11+, argparse, pyyaml, jsonschema, `gh` CLI + `git` via subprocess callbacks, pytest + pytest-mock. No new heavy deps (no jinja2, no matplotlib).

> [!warning] Sequencing — deferred, ships as a PR
> **Do not start this yet.** It is queued **behind the [[2026-06-21-lms-suite-integration-plan|LMS-suite integration]]** — implement only after that work lands. When picked up, it ships as its **own feature branch → PR** against `agiacalone/lectern` (not direct-to-`main`); mirror the vault design+plan into the repo `docs/` as the first commit, then execute the tasks below. Status: **spec + plan complete, execution parked.**

Design: [[2026-06-21-lab-report-design]]. Golden reference: [[classes/378-478/archives/su26-01/recon-lab1/REPORT|Su26 Lab 1 REPORT]] + [[classes/378-478/archives/su26-01/recon-lab1/FEEDBACK_LOG|FEEDBACK_LOG]].

## Global Constraints

- **Repo:** `~/git/lectern` (canonical: public `agiacalone/lectern`); mirror design+plan from vault on start.
- **Offline/pure:** no network in `render`; no new runtime deps beyond pyyaml + jsonschema (already present).
- **GitHub/git via callbacks:** every external call takes a `gh=`/`git=` keyword defaulting to a `subprocess.run` wrapper; tests inject fakes. Never PyGithub.
- **Signing mandatory in `deliver`:** commits use `git commit -S`; refuse to push if the resulting commit is not GPG-signed.
- **`--dry-run` is the default for `deliver`;** `--execute` required to perform any remote mutation.
- **Advisory firewall:** the tool never writes a scores CSV and never calls `reg-gradebook`. Internal `comment` is never a delivery input — only `student_comment`.
- **CLI shape:** module exposes `main(argv: list[str]) -> int`; subcommands via argparse; installed as `reg-lab-report` by `install.sh` (wrapper → `python -m lectern.lab_report`).
- **Test style:** pytest, `testpaths=["tests"]`, fixtures use the Batman synthetic cohort (Harley/Joker/Barbara Gordon/Riddler).
- **Student-id padding:** reuse `lectern.student_id.pad_student_id`; never re-implement.

---

### Task 1: Report manifest (`report_manifest`)

**Files:**
- Create: `lectern/report_manifest.py`
- Test: `tests/test_report_manifest.py`
- Create (fixture): `templates/spellbreaker.report.yaml`

**Interfaces:**
- Produces: `@dataclass ReportManifest(course, section, term, lab, org, repo_prefix, auto_max:int, writeup_max:int, wards:list[Ward], letter_cuts:dict[str,float], bump_band:float, feedback_branch:str, feedback_pr:int)`; `Ward(key:str, label:str)`. `load_report_manifest(path:str) -> ReportManifest`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_report_manifest.py
from lectern.report_manifest import load_report_manifest

def test_loads_spellbreaker(tmp_path):
    p = tmp_path / "m.yaml"
    p.write_text(
        "course: CECS 378\nsection: '01'\nterm: su26\n"
        "lab: 'Lab 1 — Symmetric Cryptography'\n"
        "org: Giacalone-CECS\nrepo_prefix: cecs-378-su26-01-lab-01-symmetric-crypto\n"
        "auto_max: 70\nwriteup_max: 30\nbump_band: 1.0\n"
        "feedback_branch: feedback\nfeedback_pr: 1\n"
        "wards:\n  - {key: ward1, label: 'Ward I'}\n  - {key: ward2, label: 'Ward II'}\n"
        "letter_cuts: {A: 90, B: 80, C: 70, D: 60, F: 0}\n"
    )
    m = load_report_manifest(str(p))
    assert m.auto_max == 70 and m.writeup_max == 30
    assert [w.key for w in m.wards] == ["ward1", "ward2"]
    assert m.letter_cuts["A"] == 90 and m.feedback_pr == 1

def test_rejects_bad_point_split(tmp_path):
    p = tmp_path / "m.yaml"
    p.write_text("course: X\nsection: '01'\nterm: su26\nlab: L\norg: O\n"
                 "repo_prefix: p\nauto_max: -1\nwriteup_max: 30\n"
                 "feedback_branch: feedback\nfeedback_pr: 1\nwards: []\n"
                 "letter_cuts: {A: 90}\n")
    import pytest
    with pytest.raises(ValueError):
        load_report_manifest(str(p))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_report_manifest.py -v`
Expected: FAIL (`ModuleNotFoundError: lectern.report_manifest`).

- [ ] **Step 3: Write minimal implementation**

```python
# lectern/report_manifest.py
from dataclasses import dataclass
import yaml

@dataclass
class Ward:
    key: str
    label: str

@dataclass
class ReportManifest:
    course: str
    section: str
    term: str
    lab: str
    org: str
    repo_prefix: str
    auto_max: int
    writeup_max: int
    wards: list
    letter_cuts: dict
    bump_band: float
    feedback_branch: str
    feedback_pr: int

def load_report_manifest(path: str) -> ReportManifest:
    with open(path) as f:
        d = yaml.safe_load(f) or {}
    auto_max = int(d.get("auto_max", 0))
    writeup_max = int(d.get("writeup_max", 0))
    if auto_max < 0 or writeup_max < 0:
        raise ValueError("auto_max/writeup_max must be >= 0")
    wards = [Ward(w["key"], w["label"]) for w in (d.get("wards") or [])]
    return ReportManifest(
        course=d["course"], section=str(d["section"]), term=d["term"],
        lab=d["lab"], org=d["org"], repo_prefix=d["repo_prefix"],
        auto_max=auto_max, writeup_max=writeup_max, wards=wards,
        letter_cuts=d.get("letter_cuts", {}), bump_band=float(d.get("bump_band", 1.0)),
        feedback_branch=d.get("feedback_branch", "feedback"),
        feedback_pr=int(d.get("feedback_pr", 1)),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_report_manifest.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Create the reference manifest + commit**

Write `templates/spellbreaker.report.yaml` mirroring the Step-1 fixture (wards ward1–ward3 + omega, full letter_cuts, real prefix).

```bash
git add lectern/report_manifest.py tests/test_report_manifest.py templates/spellbreaker.report.yaml
git commit -S -m "feat(lab-report): report manifest parser + spellbreaker reference"
```

---

### Task 2: Agate charts (`report_charts`)

**Files:**
- Create: `lectern/report_charts.py`
- Test: `tests/test_report_charts.py`

**Interfaces:**
- Produces: `bar_chart(rows: list[tuple[str,int]], *, max_w:int=24) -> str` (each row `LABEL ▏███ N`, bars scaled to the max value, label column padded to the widest label); `histogram(values: list[float], bins: list[tuple[str,float,float]], *, max_w:int=24) -> str` (bins are `(label, lo, hi)`, hi exclusive except the last which is inclusive); `funnel(stages: list[tuple[str,int]], *, max_w:int=24) -> str` (alias of bar_chart with stage order preserved).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_report_charts.py
from lectern.report_charts import bar_chart, histogram

def test_bar_chart_scales_to_max():
    out = bar_chart([("A", 13), ("B", 6), ("F", 3)], max_w=10)
    lines = out.splitlines()
    assert lines[0].startswith("A ▏") and lines[0].endswith(" 13")
    # max value gets the full bar width
    assert "█" * 10 in lines[0]
    # zero-safe: smaller bars are proportionally shorter
    assert lines[1].count("█") < lines[0].count("█")

def test_bar_chart_handles_zero():
    out = bar_chart([("D", 0), ("A", 5)], max_w=8)
    assert out.splitlines()[0].strip().endswith("0")
    assert "█" not in out.splitlines()[0]

def test_histogram_bins_inclusive_last():
    bins = [("<70", 0, 70), ("70-79", 70, 80), ("80-89", 80, 90), ("90-100", 90, 100)]
    out = histogram([100, 95, 90, 84, 70, 43], bins, max_w=10)
    rows = {l.split("▏")[0].strip(): l for l in out.splitlines()}
    assert rows["90-100"].endswith(" 3")   # 100,95,90
    assert rows["70-79"].endswith(" 1")    # 70
    assert rows["<70"].endswith(" 1")      # 43
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_report_charts.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Write minimal implementation**

```python
# lectern/report_charts.py
def bar_chart(rows, *, max_w: int = 24) -> str:
    if not rows:
        return ""
    label_w = max(len(str(l)) for l, _ in rows)
    peak = max((v for _, v in rows), default=0) or 1
    lines = []
    for label, value in rows:
        n = round(value / peak * max_w) if value > 0 else 0
        lines.append(f"{str(label).ljust(label_w)} ▏{'█' * n} {value}")
    return "\n".join(lines)

def funnel(stages, *, max_w: int = 24) -> str:
    return bar_chart(stages, max_w=max_w)

def histogram(values, bins, *, max_w: int = 24) -> str:
    counts = []
    for i, (label, lo, hi) in enumerate(bins):
        last = i == len(bins) - 1
        c = sum(1 for v in values if (lo <= v <= hi) if last else (lo <= v < hi))
        counts.append((label, c))
    return bar_chart(counts, max_w=max_w)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_report_charts.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add lectern/report_charts.py tests/test_report_charts.py
git commit -S -m "feat(lab-report): agate chart primitives"
```

---

### Task 3: Sanitization lint (`feedback_sanitize`)

**Files:**
- Create: `lectern/feedback_sanitize.py`
- Test: `tests/test_feedback_sanitize.py`

**Interfaces:**
- Produces: `lint_student_comment(text: str, *, cohort_names: list[str]) -> list[str]` — returns a list of violation tags (empty = clean). Tags: `internal-jargon`, `cross-student`. Matching is case-insensitive, word-boundary for jargon, substring for names.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_feedback_sanitize.py
from lectern.feedback_sanitize import lint_student_comment

NAMES = ["Basil Karlo", "Barbara Gordon", "bwayne"]

def test_clean_passes():
    assert lint_student_comment(
        "Full clear across all wards; strong padding-oracle writeup.", cohort_names=NAMES) == []

def test_flags_internal_jargon():
    tags = lint_student_comment("Triage REVIEW; honor-gate failed; digest abstained.", cohort_names=NAMES)
    assert "internal-jargon" in tags

def test_flags_cross_student_name():
    tags = lint_student_comment("Better than Basil Karlo's attempt.", cohort_names=NAMES)
    assert "cross-student" in tags

def test_jargon_is_word_boundary():
    # "flagging" must NOT trip the "FLAG" token
    assert lint_student_comment("Consider flagging weak ciphers.", cohort_names=NAMES) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_feedback_sanitize.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Write minimal implementation**

```python
# lectern/feedback_sanitize.py
import re

JARGON = [
    "review", "flag", "honor-gate", "honor gate", "triage",
    "advisory", "screening", "digest", "recon", "oracle", "abstain",
]

def lint_student_comment(text: str, *, cohort_names) -> list:
    tags = []
    low = text.lower()
    for tok in JARGON:
        if re.search(rf"(?<!\w){re.escape(tok)}(?!\w)", low):
            tags.append("internal-jargon")
            break
    for name in cohort_names:
        if name and name.lower() in low:
            tags.append("cross-student")
            break
    return tags
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_feedback_sanitize.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add lectern/feedback_sanitize.py tests/test_feedback_sanitize.py
git commit -S -m "feat(lab-report): student_comment sanitization lint"
```

---

### Task 4: Digest `student_comment` extension

**Files:**
- Modify: `lectern/digest_schema.py` (add `student_comment` to required + properties)
- Modify: `lectern/digest_emit.py` (embed `student_comment_max_chars`; instruct via embedded schema)
- Modify: `lectern/digest_merge.py` (carry `student_comment` into cohort.csv + run sanitize lint; withhold on low-confidence)
- Modify: `docs/lab-digest-grader-prompt.md` (document the new field + sanitization rules)
- Test: `tests/test_digest_student_comment.py`

**Interfaces:**
- Consumes: `lectern.feedback_sanitize.lint_student_comment` (Task 3).
- Produces: digest result objects gain `student_comment: str`; merged `cohort.csv` gains columns `student_comment` and (when lint/confidence withholds it) a `student-comment:needs-review` entry in `writeup_flags`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_digest_student_comment.py
from lectern.digest_schema import validate_result
from lectern.digest_rubric import load_rubric

def _rubric(tmp_path):
    p = tmp_path / "r.yaml"
    p.write_text("lab: L\ntotal: 30\ncomment_max_chars: 140\nstudent_comment_max_chars: 600\ncap: 30\n"
                 "sections:\n  - {key: ward1, label: W1, max: 30, requires_cleared: ward1, "
                 "anchors: {strong: s, adequate: a, weak: w, missing: m}}\n")
    return load_rubric(str(p))

def test_student_comment_required(tmp_path):
    r = _rubric(tmp_path)
    obj = {"github_id": "x", "sections": {"ward1": 30}, "total": 30,
           "comment": "ok", "confidence": "high", "abstain": False}
    errs = validate_result(obj, r)
    assert any("student_comment" in e for e in errs)

def test_student_comment_present_validates(tmp_path):
    r = _rubric(tmp_path)
    obj = {"github_id": "x", "sections": {"ward1": 30}, "total": 30,
           "comment": "ok", "student_comment": "Nice full clear.",
           "confidence": "high", "abstain": False}
    assert validate_result(obj, r) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_digest_student_comment.py -v`
Expected: FAIL (`student_comment` not in schema → second test errors, or first test finds no such error).

- [ ] **Step 3: Edit `digest_schema.py`**

In the schema builder add to `required` the string `"student_comment"` and to `properties`:

```python
"student_comment": {"type": "string", "maxLength": rubric.student_comment_max_chars},
```

(If `digest_rubric.Rubric` lacks `student_comment_max_chars`, add it there with default `600`, parsed from the rubric YAML key `student_comment_max_chars`.)

- [ ] **Step 4: Edit `digest_merge.py`**

After the existing confidence gate, before writing the cohort row:

```python
from lectern.feedback_sanitize import lint_student_comment

sc = (result.get("student_comment") or "").strip()
flags = row.setdefault("writeup_flags", [])
if result.get("confidence") == "low" or result.get("abstain"):
    sc = ""  # withhold; needs-human-read already flagged
elif sc:
    bad = lint_student_comment(sc, cohort_names=all_display_names + all_github_ids)
    if bad:
        flags.append("student-comment:needs-review")
        sc = ""
row["student_comment"] = sc
```

(Add `student_comment` to the cohort.csv column list in the writer.)

- [ ] **Step 5: Edit `digest_emit.py` + grader prompt**

In `digest_emit`, include `student_comment_max_chars` in the embedded rubric/schema. In `docs/lab-digest-grader-prompt.md` add a section: emit `student_comment` — constructive, mechanism-focused, the lab's in-world vocabulary OK, **no cross-student comparison, no internal triage jargon, AI disclosure never penalized**, ≤ `student_comment_max_chars`.

- [ ] **Step 6: Run tests (new + existing digest suite)**

Run: `pytest tests/test_digest_student_comment.py tests/test_digest_merge.py tests/test_digest_schema.py -v`
Expected: PASS (new 2 + existing green; fix any existing fixture that now needs `student_comment`).

- [ ] **Step 7: Commit**

```bash
git add lectern/digest_schema.py lectern/digest_emit.py lectern/digest_merge.py lectern/digest_rubric.py docs/lab-digest-grader-prompt.md tests/test_digest_student_comment.py
git commit -S -m "feat(digest): student_comment field + sanitize-on-merge"
```

---

### Task 5: Recommendations engine (`report_recommend`)

**Files:**
- Create: `lectern/report_recommend.py`
- Test: `tests/test_report_recommend.py`

**Interfaces:**
- Consumes: cohort rows (dicts with `github_id, student, points, honor_ok, triage_bucket, writeup_flags, proposed`), standing dict `{github_id: weighted_pct}`, `ReportManifest`.
- Produces: `recommend(cohort: list[dict], standing: dict, manifest) -> Recommendations` where `@dataclass Recommendations(confirm:list, edge_cases:list, low_confidence:list, upward:list)`; each entry is `{"github_id","student","reason"}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_report_recommend.py
from lectern.report_recommend import recommend
from lectern.report_manifest import ReportManifest

M = ReportManifest("CECS 378","01","su26","L","O","p",70,30,[],
                   {"A":90,"B":80,"C":70,"D":60,"F":0}, 1.0, "feedback", 1)

def row(**k):
    base = dict(github_id="x", student="X", points=70, honor_ok=True,
                triage_bucket="PASS", writeup_flags=[], proposed=100)
    base.update(k); return base

def test_routine_goes_to_confirm():
    rec = recommend([row()], {"x": 96.0}, M)
    assert rec.confirm and not rec.edge_cases

def test_honor_fail_is_edge_case():
    rec = recommend([row(github_id="j", honor_ok=False, points=0, proposed=0)], {"j": 0}, M)
    assert any(e["github_id"] == "j" for e in rec.edge_cases)

def test_flag_triage_is_edge_case():
    rec = recommend([row(github_id="f", triage_bucket="FLAG")], {"f": 80}, M)
    assert any(e["github_id"] == "f" for e in rec.edge_cases)

def test_needs_review_is_low_confidence():
    rec = recommend([row(github_id="r", writeup_flags=["student-comment:needs-review"])], {"r": 85}, M)
    assert any(e["github_id"] == "r" for e in rec.low_confidence)

def test_near_letter_cut_is_upward():
    # 89.4 is within bump_band(1.0) below B cut 80? no — it's near A cut 90.
    rec = recommend([row(github_id="u")], {"u": 89.4}, M)
    assert any(e["github_id"] == "u" for e in rec.upward)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_report_recommend.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Write minimal implementation**

```python
# lectern/report_recommend.py
from dataclasses import dataclass, field

@dataclass
class Recommendations:
    confirm: list = field(default_factory=list)
    edge_cases: list = field(default_factory=list)
    low_confidence: list = field(default_factory=list)
    upward: list = field(default_factory=list)

LOW_CONF_FLAGS = {"student-comment:needs-review", "digest:invalid",
                  "digest:total-drift", "needs-human-read", "partial-ward-zeroed"}

def _item(r, reason):
    return {"github_id": r["github_id"], "student": r["student"], "reason": reason}

def _near_cut(pct, cuts, band):
    for letter, cut in cuts.items():
        if cut and 0 <= (cut - pct) <= band:
            return letter
    return None

def recommend(cohort, standing, manifest) -> Recommendations:
    rec = Recommendations()
    for r in cohort:
        gid = r["github_id"]
        pct = standing.get(gid)
        flags = set(r.get("writeup_flags") or [])
        if not r.get("honor_ok", True) or r.get("points", 0) == 0:
            rec.edge_cases.append(_item(r, "honor-gate fail / non-submission — late-policy call"))
            continue
        if r.get("triage_bucket") in ("REVIEW", "FLAG"):
            rec.edge_cases.append(_item(r, f"triage {r['triage_bucket']} — review before posting"))
            continue
        if flags & LOW_CONF_FLAGS:
            rec.low_confidence.append(_item(r, f"automated score withheld: {sorted(flags & LOW_CONF_FLAGS)}"))
            continue
        near = _near_cut(pct, manifest.letter_cuts, manifest.bump_band) if pct is not None else None
        if near:
            rec.upward.append(_item(r, f"{pct:.1f}% — within {manifest.bump_band} of {near} cut"))
        rec.confirm.append(_item(r, f"proposed {r.get('proposed')} — routine"))
    return rec
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_report_recommend.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add lectern/report_recommend.py tests/test_report_recommend.py
git commit -S -m "feat(lab-report): deterministic recommendations engine"
```

---

### Task 6: Report renderer (`report_render`)

**Files:**
- Create: `lectern/report_render.py`
- Create: `templates/instructor-report.md` (section skeleton with `{{...}}` slots)
- Test: `tests/test_report_render.py`
- Create (fixture): `tests/fixtures/batman_cohort.csv`

**Interfaces:**
- Consumes: recon `bundle/`, the digest-merged `cohort.csv`, optional `gradebook.csv`, `ReportManifest`; `report_charts`, `report_recommend`.
- Produces: `render_report(bundle_dir:str, cohort_csv:str, manifest, *, standing_csv:str|None=None) -> str` (the full REPORT.md text); `main(argv)` for `reg-lab-report render`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_report_render.py
from lectern.report_render import render_report
from lectern.report_manifest import ReportManifest
import csv, os

M = ReportManifest("CECS 378","01","su26","Lab 1 — Symmetric Cryptography",
                   "Giacalone-CECS","cecs-378-su26-01-lab-01-symmetric-crypto",
                   70,30,[type("W",(),{"key":"ward1","label":"Ward I"})(),
                          type("W",(),{"key":"ward2","label":"Ward II"})()],
                   {"A":90,"B":80,"C":70,"D":60,"F":0}, 1.0, "feedback", 1)

def _cohort(tmp_path):
    p = tmp_path / "cohort.csv"
    with open(p, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["github_id","student","points","honor_ok","triage_bucket",
                    "writeup_score","writeup_comment","student_comment","writeup_flags"])
        w.writerow(["bwayne","Selina Kyle","70","True","PASS","30","precise","Full clear.",""])
        w.writerow(["flawton","James Gordon","0","False","REVIEW","0","","","" ])
    return str(p)

def test_render_has_sections(tmp_path):
    out = render_report(str(tmp_path), _cohort(tmp_path), M)
    for h in ["# ", "GRADE DISTRIBUTION", "Grade table", "recommendations",
              "Canvas entry sheet", "Provenance"]:
        assert h in out

def test_proposed_is_auto_plus_writeup(tmp_path):
    out = render_report(str(tmp_path), _cohort(tmp_path), M)
    assert "100" in out          # Arya 70+30
    # non-submission routed to edge cases, not confirm
    assert "James Gordon" in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_report_render.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Write minimal implementation**

```python
# lectern/report_render.py
import csv, statistics
from lectern.report_charts import bar_chart, histogram, funnel
from lectern.report_recommend import recommend
from lectern.report_manifest import load_report_manifest

def _read_cohort(path):
    with open(path) as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["points"] = int(float(r.get("points") or 0))
        r["writeup_score"] = int(float(r.get("writeup_score") or 0))
        r["proposed"] = r["points"] + r["writeup_score"]
        r["honor_ok"] = str(r.get("honor_ok")).lower() in ("true", "1", "yes")
        r["writeup_flags"] = [x for x in (r.get("writeup_flags") or "").split(";") if x]
    return rows

def _letter(pct, cuts):
    for l, c in sorted(cuts.items(), key=lambda kv: -kv[1]):
        if pct >= c:
            return l
    return "F"

def _standing(rows, manifest):
    # mid-term standing fallback: proposed% of the lab only (no gradebook supplied)
    return {r["github_id"]: (r["proposed"] / (manifest.auto_max + manifest.writeup_max) * 100)
            for r in rows}

def render_report(bundle_dir, cohort_csv, manifest, *, standing_csv=None):
    rows = _read_cohort(cohort_csv)
    enrolled = [r for r in rows if r["honor_ok"] and r["points"] > 0] or rows
    proposed = [r["proposed"] for r in enrolled]
    n = len(enrolled)
    mean = statistics.mean(proposed) if proposed else 0
    median = statistics.median(proposed) if proposed else 0
    sigma = statistics.pstdev(proposed) if len(proposed) > 1 else 0
    standing = _standing(rows, manifest)
    # grade distribution
    dist = {}
    for r in enrolled:
        dist[_letter(r["proposed"], manifest.letter_cuts)] = dist.get(_letter(r["proposed"], manifest.letter_cuts), 0) + 1
    grade_rows = [(l, dist.get(l, 0)) for l in ["A","B","C","D","F"]]
    hist_bins = [("<70",0,70),("70-79",70,80),("80-89",80,90),("90-100",90,100)]
    # ward funnel
    ward_rows = []
    for w in manifest.wards:
        cleared = sum(1 for r in rows if w.key in (r.get("cleared","") or ""))
        ward_rows.append((w.label, cleared))
    rec = recommend(rows, standing, manifest)

    out = []
    out.append(f"# {manifest.lab} · Instructor Report")
    out.append(f"*{manifest.course} · {manifest.term} · §{manifest.section} — n={n} · "
               f"mean {mean:.1f} · median {median:.0f} · σ {sigma:.1f}*\n")
    out.append("## Distribution\n```\nGRADE DISTRIBUTION  n=%d  μ=%.1f  σ=%.1f\n%s\n\n"
               "SCORE HISTOGRAM\n%s\n\nWARD-CLEAR FUNNEL\n%s\n```\n"
               % (n, mean, sigma, bar_chart(grade_rows), histogram(proposed, hist_bins),
                  funnel(ward_rows)))
    out.append("## ➊ Grade table\n")
    out.append("| Student | github | Auto | Writeup | **Proposed** | flags |")
    out.append("| --- | --- | --: | --: | --: | --- |")
    for r in sorted(rows, key=lambda r: -r["proposed"]):
        out.append(f"| {r['student']} | {r['github_id']} | {r['points']} | "
                   f"{r['writeup_score']} | **{r['proposed']}** | {';'.join(r['writeup_flags'])} |")
    out.append("\n## Grading recommendations\n")
    for title, items in [("Confirm (routine)", rec.confirm), ("Edge cases needing a call", rec.edge_cases),
                         ("Low-confidence / needs-human-read", rec.low_confidence),
                         ("Upward-adjustment candidates", rec.upward)]:
        out.append(f"### {title}")
        out.extend(f"- **{i['student']}** ({i['github_id']}) — {i['reason']}" for i in items) or out.append("- _none_")
        out.append("")
    out.append("## Canvas entry sheet\n")
    out.append("| Student (Last, First) | Proposed |\n| --- | --: |")
    for r in sorted(rows, key=lambda r: r["student"].split()[-1]):
        out.append(f"| {r['student']} | {r['proposed']} |")
    out.append("\n## Provenance & caveats\n")
    out.append("Part A (autograde/honor/commits) = audit-grade facts. Part B (writeup "
               "scores/comments) = advisory, instructor-confirmed. Rendered by `reg-lab-report`.")
    return "\n".join(out)

def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(prog="reg-lab-report render")
    ap.add_argument("--bundle", required=True)
    ap.add_argument("--cohort", required=True)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--standing")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    m = load_report_manifest(a.manifest)
    text = render_report(a.bundle, a.cohort, m, standing_csv=a.standing)
    with open(a.out, "w") as f:
        f.write(text + "\n")
    print(f"wrote {a.out}")
    return 0
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_report_render.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add lectern/report_render.py templates/instructor-report.md tests/test_report_render.py tests/fixtures/batman_cohort.csv
git commit -S -m "feat(lab-report): deterministic REPORT.md renderer"
```

---

### Task 7: Feedback log (`feedback_log`)

**Files:**
- Create: `lectern/feedback_log.py`
- Create: `templates/feedback-log.md`
- Test: `tests/test_feedback_log.py`

**Interfaces:**
- Produces: `render_feedback_log(entries: list[dict], manifest) -> str` where each entry is `{"github_id","student","auto","writeup","total","student_comment","posted","signed","pr_state"}`; sorted by total desc. Includes frontmatter (`type: feedback-log`, `visibility: private`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_feedback_log.py
from lectern.feedback_log import render_feedback_log
from lectern.report_manifest import ReportManifest

M = ReportManifest("CECS 378","01","su26","Lab 1","Giacalone-CECS",
                   "cecs-378-su26-01-lab-01-symmetric-crypto",70,30,[],{}, 1.0, "feedback", 1)

def test_log_has_frontmatter_and_entries():
    out = render_feedback_log([
        {"github_id":"bwayne","student":"Selina Kyle","auto":70,"writeup":30,"total":100,
         "student_comment":"Full clear.","posted":True,"signed":True,"pr_state":"CLOSED"}], M)
    assert out.startswith("---") and "type: feedback-log" in out
    assert "visibility: private" in out
    assert "Selina Kyle" in out and "100" in out and "Full clear." in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_feedback_log.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Write minimal implementation**

```python
# lectern/feedback_log.py
def render_feedback_log(entries, manifest) -> str:
    out = ["---", "type: feedback-log",
           "tags: [feedback-log, grading, private]", "visibility: private",
           "icon: LiMessageSquareText", "iconColor: var(--text-normal)", "---",
           f"# {manifest.lab} · Feedback Delivered to Students",
           f"*{manifest.course} · {manifest.term} · §{manifest.section} — verbatim record*", ""]
    for e in sorted(entries, key=lambda e: -e["total"]):
        sig = "signed" if e.get("signed") else "UNSIGNED"
        out.append(f"### {e['student']} — {e['total']}/{manifest.auto_max + manifest.writeup_max}")
        out.append(f"*github: `{e['github_id']}` · Auto {e['auto']}/{manifest.auto_max} · "
                   f"Writeup {e['writeup']}/{manifest.writeup_max} · {sig} · PR {e.get('pr_state','-')}*")
        out.append("")
        out.append(f"> {e.get('student_comment','') or '_no comment_'}")
        out.append("")
    return "\n".join(out)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_feedback_log.py -v`
Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
git add lectern/feedback_log.py templates/feedback-log.md tests/test_feedback_log.py
git commit -S -m "feat(lab-report): verbatim feedback-log renderer"
```

---

### Task 8: Feedback delivery (`feedback_deliver`)

**Files:**
- Create: `lectern/feedback_deliver.py`
- Create: `templates/feedback.md`
- Test: `tests/test_feedback_deliver.py`

**Interfaces:**
- Consumes: cohort rows, `ReportManifest`, `feedback_log.render_feedback_log`.
- Produces: `render_feedback_md(row, manifest) -> str`; `deliver(cohort, manifest, workdir, *, execute=False, close=True, only=None, skip=None, gh=..., git=...) -> list[dict]` (returns the log entries; in dry-run performs no remote ops). `main(argv)` for `reg-lab-report deliver`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_feedback_deliver.py
from lectern.feedback_deliver import render_feedback_md, deliver
from lectern.report_manifest import ReportManifest

M = ReportManifest("CECS 378","01","su26","Lab 1","Giacalone-CECS",
                   "cecs-378-su26-01-lab-01-symmetric-crypto",70,30,[],{}, 1.0, "feedback", 1)

def row(**k):
    base = dict(github_id="bwayne", student="Selina Kyle", points=70,
                writeup_score=30, student_comment="Full clear.", honor_ok=True)
    base.update(k); return base

def test_feedback_md_has_breakdown_and_comment():
    md = render_feedback_md(row(), M)
    assert "100 / 100" in md and "70 / 70" in md and "Full clear." in md

def test_dry_run_makes_no_calls(tmp_path):
    calls = []
    fake = lambda *a, **k: calls.append(a) or type("R",(),{"stdout":"","returncode":0})()
    entries = deliver([row()], M, str(tmp_path), execute=False, gh=fake, git=fake)
    assert calls == []                      # nothing remote in dry-run
    assert entries[0]["github_id"] == "bwayne" and entries[0]["posted"] is False

def test_non_submission_gets_neutral_note(tmp_path):
    md = render_feedback_md(row(github_id="flawton", student="James Gordon",
                                points=0, writeup_score=0, student_comment="", honor_ok=False), M)
    assert "No submission" in md and "0 / 100" in md

def test_only_filter(tmp_path):
    fake = lambda *a, **k: type("R",(),{"stdout":"OPEN","returncode":0})()
    entries = deliver([row(), row(github_id="skyle", student="John B")], M, str(tmp_path),
                      execute=False, only=["skyle"], gh=fake, git=fake)
    assert [e["github_id"] for e in entries] == ["skyle"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_feedback_deliver.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Write minimal implementation**

```python
# lectern/feedback_deliver.py
import os, subprocess

TOTAL = lambda m: m.auto_max + m.writeup_max

def _sh(*args, **k):
    return subprocess.run(args, capture_output=True, text=True, **k)

def render_feedback_md(row, manifest) -> str:
    total = row["points"] + row["writeup_score"]
    if not row.get("honor_ok", True) or total == 0:
        comment = ("No submission was recorded for this lab. If you believe this is an "
                   "error, please contact me right away.")
    else:
        comment = row.get("student_comment") or "_See score breakdown above._"
    return (f"# {manifest.lab} — Feedback\n\n"
            f"**Total: {total} / {TOTAL(manifest)}**\n\n"
            f"| Component | Score |\n| --- | --: |\n"
            f"| Wards (autograder) | {row['points']} / {manifest.auto_max} |\n"
            f"| Grimoire (writeup) | {row['writeup_score']} / {manifest.writeup_max} |\n\n"
            f"## Comments\n{comment}\n\n---\n"
            f"*{manifest.course} · {manifest.term} · §{manifest.section} — graded by Prof. Giacalone*\n")

def deliver(cohort, manifest, workdir, *, execute=False, close=True,
            only=None, skip=None, gh=_sh, git=_sh):
    rows = [r for r in cohort
            if (not only or r["github_id"] in only) and (not skip or r["github_id"] not in skip)]
    entries = []
    for r in rows:
        gid = r["github_id"]
        repo = f"{manifest.org}/{manifest.repo_prefix}-{gid}"
        total = r["points"] + r["writeup_score"]
        md = render_feedback_md(r, manifest)
        posted = signed = False
        pr_state = "-"
        if execute:
            dest = os.path.join(workdir, gid)
            gh("repo", "clone", repo, dest, "--", "--branch",
               manifest.feedback_branch, "--single-branch")
            with open(os.path.join(dest, "FEEDBACK.md"), "w") as f:
                f.write(md)
            git("-C", dest, "add", "FEEDBACK.md")
            git("-C", dest, "commit", "-S", "-m", "Lab feedback and grade breakdown")
            ver = git("-C", dest, "log", "-1", "--show-signature")
            signed = "Good signature" in (ver.stdout + getattr(ver, "stderr", ""))
            if not signed:
                raise RuntimeError(f"refusing to push unsigned commit for {gid}")
            git("-C", dest, "push", "origin", manifest.feedback_branch)
            posted = True
            st = gh("pr", "view", str(manifest.feedback_pr), "--repo", repo,
                    "--json", "state", "-q", ".state")
            pr_state = (st.stdout or "").strip() or "-"
            if close and pr_state == "OPEN":
                gh("pr", "close", str(manifest.feedback_pr), "--repo", repo)
                pr_state = "CLOSED"
        entries.append({"github_id": gid, "student": r["student"], "auto": r["points"],
                        "writeup": r["writeup_score"], "total": total,
                        "student_comment": r.get("student_comment", ""),
                        "posted": posted, "signed": signed, "pr_state": pr_state})
    return entries

def main(argv=None):
    import argparse, csv
    from lectern.report_manifest import load_report_manifest
    from lectern.feedback_log import render_feedback_log
    ap = argparse.ArgumentParser(prog="reg-lab-report deliver")
    ap.add_argument("--cohort", required=True)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--workdir", default="/tmp/reg-lab-report")
    ap.add_argument("--execute", action="store_true")
    ap.add_argument("--no-close", action="store_true")
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--skip", nargs="*")
    ap.add_argument("--log-out")
    a = ap.parse_args(argv)
    m = load_report_manifest(a.manifest)
    with open(a.cohort) as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["points"] = int(float(r.get("points") or 0))
        r["writeup_score"] = int(float(r.get("writeup_score") or 0))
        r["honor_ok"] = str(r.get("honor_ok")).lower() in ("true","1","yes")
    os.makedirs(a.workdir, exist_ok=True)
    entries = deliver(rows, m, a.workdir, execute=a.execute, close=not a.no_close,
                      only=a.only, skip=a.skip)
    if a.log_out:
        with open(a.log_out, "w") as f:
            f.write(render_feedback_log(entries, m) + "\n")
    print(("EXECUTED" if a.execute else "DRY-RUN") + f": {len(entries)} repos")
    return 0
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_feedback_deliver.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add lectern/feedback_deliver.py templates/feedback.md tests/test_feedback_deliver.py
git commit -S -m "feat(lab-report): signed feedback-branch delivery (dry-run default)"
```

---

### Task 9: CLI wiring (`lab_report`) + install

**Files:**
- Create: `lectern/lab_report.py`
- Modify: `install.sh` (register `reg-lab-report` wrapper)
- Test: `tests/test_lab_report_cli.py`

**Interfaces:**
- Consumes: `report_render.main`, `feedback_deliver.main`.
- Produces: `main(argv) -> int` dispatching `render` / `deliver`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_lab_report_cli.py
import pytest
from lectern.lab_report import main

def test_requires_subcommand():
    with pytest.raises(SystemExit):
        main([])

def test_render_dispatch(tmp_path, monkeypatch):
    called = {}
    monkeypatch.setattr("lectern.report_render.main", lambda argv: called.setdefault("render", argv) or 0)
    assert main(["render", "--bundle", "b", "--cohort", "c", "--manifest", "m", "--out", "o"]) == 0
    assert called["render"][0] == "--bundle"

def test_deliver_dispatch(monkeypatch):
    called = {}
    monkeypatch.setattr("lectern.feedback_deliver.main", lambda argv: called.setdefault("deliver", argv) or 0)
    assert main(["deliver", "--cohort", "c", "--manifest", "m"]) == 0
    assert "deliver" in called
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_lab_report_cli.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Write minimal implementation**

```python
# lectern/lab_report.py
import sys

def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] not in ("render", "deliver"):
        print("usage: reg-lab-report {render|deliver} ...", file=sys.stderr)
        raise SystemExit(2)
    sub, rest = argv[0], argv[1:]
    if sub == "render":
        from lectern import report_render
        return report_render.main(rest)
    from lectern import feedback_deliver
    return feedback_deliver.main(rest)

if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Register the wrapper in `install.sh`**

Add `reg-lab-report` to the command list that writes `python -m lectern.lab_report "$@"` wrappers (follow the existing `reg-lab-recon` line verbatim).

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_lab_report_cli.py -v`
Expected: PASS (3 passed).

- [ ] **Step 6: Commit**

```bash
git add lectern/lab_report.py install.sh tests/test_lab_report_cli.py
git commit -S -m "feat(lab-report): reg-lab-report CLI (render/deliver) + install wrapper"
```

---

### Task 10: Golden integration test (Spellbreaker Su26)

**Files:**
- Create: `tests/test_lab_report_golden.py`
- Create (fixtures): `tests/fixtures/spellbreaker_su26/cohort.csv`, `tests/fixtures/spellbreaker_su26/expected_report.md`

**Interfaces:**
- Consumes: `report_render.render_report`. The fixtures are derived from this session's real `cohort.csv` + the verified `REPORT.md` / `FEEDBACK_LOG.md`.

- [ ] **Step 1: Build the fixtures**

Create `tests/fixtures/spellbreaker_su26/cohort.csv` from the 25-student Su26 Lab 1 data (github_id, student, points, honor_ok, triage_bucket, writeup_score, writeup_comment, student_comment, cleared, writeup_flags). Generate `expected_report.md` once by running `render_report` and **hand-verify** it against [[classes/378-478/archives/su26-01/recon-lab1/REPORT]] (grade table + distribution + Canvas sheet must match), then freeze it.

- [ ] **Step 2: Write the golden test**

```python
# tests/test_lab_report_golden.py
import os
from lectern.report_render import render_report
from lectern.report_manifest import load_report_manifest

FX = os.path.join(os.path.dirname(__file__), "fixtures", "spellbreaker_su26")

def test_golden_render_matches():
    m = load_report_manifest(os.path.join(FX, "spellbreaker.report.yaml"))
    out = render_report(FX, os.path.join(FX, "cohort.csv"), m)
    expected = open(os.path.join(FX, "expected_report.md")).read()
    assert out.strip() == expected.strip()

def test_golden_stats_match_known_cohort():
    m = load_report_manifest(os.path.join(FX, "spellbreaker.report.yaml"))
    out = render_report(FX, os.path.join(FX, "cohort.csv"), m)
    assert "mean 82.6" in out and "median 90" in out and "n=25" in out
```

- [ ] **Step 3: Run test to verify it passes**

Run: `pytest tests/test_lab_report_golden.py -v`
Expected: PASS (2 passed). If drift, fix the renderer (not the frozen expected) unless the change is intentional.

- [ ] **Step 4: Run the full suite**

Run: `pytest -q`
Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add tests/test_lab_report_golden.py tests/fixtures/spellbreaker_su26/
git commit -S -m "test(lab-report): golden render against Spellbreaker Su26 cohort"
```

---

### Task 11: Docs surface (CHANGELOG / SKILL / README / design)

**Files:**
- Modify: `CHANGELOG.md`, `SKILL.md`, `README.md`
- Create: `docs/design/lab-report.md` (mirror of the vault design)
- Modify: `docs/recon-report-workflow.md` (redirect note → superseded by `reg-lab-report render`)

- [ ] **Step 1: CHANGELOG** — add an Unreleased entry: `reg-lab-report` (render + deliver), digest `student_comment` extension, sanitize lint.

- [ ] **Step 2: SKILL.md** — add the `reg-lab-report render|deliver` command row to the grading table; one-line trigger note ("after grading a lab, to produce the instructor report and/or post feedback").

- [ ] **Step 3: README.md** — add a "Layer 3 — instructor report + feedback delivery" subsection under the grading pipeline with a `render`/`deliver` example (`--dry-run` shown first).

- [ ] **Step 4: docs/design/lab-report.md** — copy the vault design `2026-06-21-lab-report-design.md`; add the recon-report-workflow redirect note.

- [ ] **Step 5: Commit**

```bash
git add CHANGELOG.md SKILL.md README.md docs/design/lab-report.md docs/recon-report-workflow.md
git commit -S -m "docs(lab-report): changelog, skill, readme, design mirror"
```

---

## Self-Review

**Spec coverage:** §3 inputs → Task 1 (manifest) + Task 6 (render reads cohort). §4 report sections → Task 6. §5 charts → Task 2. §6 recommendations (4 buckets) → Task 5. §7 digest `student_comment` → Task 4. §8 sanitize lint → Task 3 + wired in Task 4/8. §9 deliver (dry-run/signing/idempotent/log) → Tasks 7+8. §10 modules → Tasks 1–9. §11 testing incl. golden + Batman fixtures → Tasks 2–10. §12 docs → Task 11. No uncovered requirement.

**Deferred-but-specified (note for executor):** idempotency skip (compare existing `FEEDBACK.md`) and the post-push `verified` GitHub check are described in §9 — add them in Task 8 as a follow-on step if not covered by the minimal impl shown (they are optional hardening, not required for first green). The `--mermaid` flag is explicitly out of scope (agate-only chosen).

**Placeholder scan:** no TBD/TODO; every code step shows real code; commands have expected output.

**Type consistency:** `ReportManifest` fields are used identically across Tasks 1/5/6/7/8/9; `recommend()` returns `Recommendations` consumed in Task 6; `render_feedback_md`/`deliver` signatures match Task 8 usage; cohort row keys (`points`, `writeup_score`, `proposed`, `honor_ok`, `writeup_flags`) are normalized the same way in `report_render._read_cohort` and `feedback_deliver.main`.

---

## Implementation deviations (discovered during execution, 2026-06-21)

The code blocks above are the design intent; these corrections were made (and tested) during implementation:

1. **`report_charts.histogram`** — the bin comprehension's conditional must be parenthesized: `... if ((lo <= v <= hi) if last else (lo <= v < hi))`. The unparenthesized `if ... if ... else` form is a `SyntaxError`.
2. **`feedback_sanitize.JARGON`** — dropped tokens that collide with legitimate crypto vocabulary (`oracle` → "padding oracle", `digest` → "message digest") and ordinary verbs (`review`, `flag`). Final list: `honor-gate`, `triage`, `advisory`, `screening`, `abstain`, `needs-human-read`, `partial-ward`. Cross-student leakage is caught separately by name.
3. **`report_render` stats** — the distribution counts **all enrolled rows** (the cohort, including a non-submission's `0`), not an `honor_ok`/`points`-filtered subset; otherwise `n`/mean diverge from the recon (`n=25`, mean `82.6`). Honor-fail/zero routing happens only in the recommendations buckets.
4. **`test_lab_report_cli`** — the dispatch stub uses `lambda argv: called.update(...) or 0` (not `setdefault(...) or 0`, which returns the list and breaks the `== 0` assertion).
5. **Required `student_comment`** — making the field required in the strict digest schema required updating the existing fixtures in `test_digest_schema.py`, `test_digest_merge.py`, and `test_lab_digest_cli.py`.

All 364 tests pass (334 baseline + 30 new).

## Post-implementation addition — merge feedback → main (2026-06-22)

Added after the first live run: a `FEEDBACK.md` committed only to the `feedback` branch is invisible on the student's repo home, so `deliver` now merges `feedback` into the default branch (`main`) as a final, signed step.

- **`report_manifest`** — new `default_branch: str = "main"` field (+ `default_branch:` key parse).
- **`feedback_deliver`** — full clone (both branches) + `checkout feedback` replaces the single-branch clone; new `_merge_to_main()` runs after the PR closes, **independently of feedback-branch idempotency** (the file can be on `feedback` yet missing from `main` — the exact production case). Signed merge commit; signing enforced on the merge too. **Unrelated-history fallback:** a repo whose `main`/`feedback` share no common ancestor (`git merge` → "refusing to merge unrelated histories") gets the file landed directly on `main` via a signed commit. Idempotency on main probes `git show main:FEEDBACK.md` (not the worktree, so it stays mock-testable). New `--no-merge-main` flag; entries carry `main_state` (`merged`/`added`/`unchanged`/`-`), surfaced in `FEEDBACK_LOG.md`.

Fixtures stay on the Batman synthetic cohort — no real student data in the repo. (Shipped as a follow-up PR after the original Layer-3 PR merged; the stale golden REPORT fixture was regenerated in the same PR.)
