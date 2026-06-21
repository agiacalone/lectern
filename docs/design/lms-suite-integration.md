# LMS Suite Integration Guide

Lectern · Scriptorium · Oracle form a self-hosted, open-format LMS for university CS courses.
This document describes how the three components integrate: the component map, the three inter-component
seam contracts, release coupling mechanics, and how to run the integration test suite.

---

## Suite map

```
                    ┌─────────────────────────────────────┐
                    │            LMS Suite                │
                    │                                     │
   Seam A           │  ┌──────────────┐                  │
  (reading-list) ───┼──▶ Scriptorium │                  │
  Lectern drives    │  │  (content)   │                  │
  Scriptorium CLI   │  │  Node · MIT  │                  │
                    │  └──────┬───────┘                  │
                    │         │ Seam C (question-bank)   │
                    │         │ KNOWN GAP — not stable   │
                    │         ▼                          │
                    │  ┌──────────────┐                  │
                    │  │   Lectern    │ ◀── Seam B       │
                    │  │   (hub /     │    (autograde)   │
                    │  │  registrar)  │  Oracle → Lectern│
                    │  │  Python·MIT  │                  │
                    │  └──────────────┘                  │
                    │                                     │
                    │  ┌──────────────┐                  │
                    │  │    Oracle    │                  │
                    │  │  (grading)   │                  │
                    │  │  Python      │                  │
                    │  │  PolyForm    │                  │
                    │  │  Strict /    │                  │
                    │  │  private     │                  │
                    │  └──────────────┘                  │
                    └─────────────────────────────────────┘
```

| Component | Role | Language / test stack | License | Repo |
|---|---|---|---|---|
| **Lectern** | Course administration — hub of the suite | Python · pytest | MIT | `agiacalone/lectern` (public) |
| **Scriptorium** | Course content — lecture notes, handouts, question banks | Node.js · vitest | MIT | `agiacalone/scriptorium` (public) |
| **Oracle** | Grading — verify-by-proof oracle + gradebox sandbox runner | Python | PolyForm Strict 1.0.0 | `agiacalone/oracle` (**private, licensed**) |

**License note.** Lectern and Scriptorium are open source (MIT). Oracle is *source-available*:
accredited educational institutions can license it for free; all other uses are by arrangement.
Oracle's **code** is private — the only public surface is the `result.json` JSON contract (Seam B).

---

## Seam A — Reading-list (Lectern → Scriptorium) ✅

**Direction:** Lectern drives Scriptorium.

**How it works.** Lectern shells out to Scriptorium's `exam-reading-list-cli.js` with a structured
argument set, and Scriptorium emits a Markdown reading-list artifact.

### CLI argument contract

```
node ~/git/scriptorium/exam-reading-list-cli.js \
  --exam-name "Demo Exam" \
  --slug      demo_exam \
  --course    "CECS 378" \
  --term      su26 \
  --out       <output-dir> \
  --mains     <path/to/topic_demo_lecture_main.md>
```

Output: `<out>/<slug>_reading_list.md` (e.g. `demo_exam_reading_list.md`).

### Manifest schema (`exam_reading_lists.yaml`)

```yaml
course: "CECS 378"
term: su26
lectures_dir: .
exams:
  - { slug: demo_exam, name: "Demo Exam", topics: [topic_demo] }
```

Source: [`tests/integration/fixtures/readinglist/exam_reading_lists.yaml`](../../tests/integration/fixtures/readinglist/exam_reading_lists.yaml)

Keys:
- `course` — course name string passed to the CLI as `--course`
- `term` — term code passed as `--term`
- `lectures_dir` — base directory containing per-topic `*_lecture_main.md` files
- `exams[].slug` — used as `--slug` and the output filename stem
- `exams[].name` — passed as `--exam-name`
- `exams[].topics` — list of topic slugs; each slug resolves to `<lectures_dir>/<slug>/<slug>_lecture_main.md`

### Worked fixture

Input lecture main: [`tests/integration/fixtures/readinglist/topic_demo/topic_demo_lecture_main.md`](../../tests/integration/fixtures/readinglist/topic_demo/topic_demo_lecture_main.md)

Golden output: [`tests/integration/fixtures/readinglist/demo_exam_reading_list.golden.md`](../../tests/integration/fixtures/readinglist/demo_exam_reading_list.golden.md)

The golden file begins:

```markdown
---
title: CECS 378 — Demo Exam Reading List (Demo Topic — Security Fundamentals)
course: CECS 378
type: reading-list
...
---

# CECS 378 — Demo Exam Reading List
```

### Test

`tests/integration/test_seam_readinglist.py` — skip-gated: requires `node` on PATH and
`~/git/scriptorium/exam-reading-list-cli.js` to exist (or `LECTERN_SCRIPTORIUM_DIR` env override).
When gating conditions are met the test invokes the live CLI and diffs output against the golden
(volatile lines — ISO timestamps, absolute paths — are normalized before comparison).

**Owner:** Scriptorium emits; Lectern drives. Contract version: `reading_list: 1`.

---

## Seam B — Autograde (Oracle → Lectern) ✅

**Direction:** Oracle/lab CI → Lectern.

**How it works.** Oracle's per-student lab CI publishes a `grading/result.json` file conforming to
`schema: 1`. Lectern's `recon_autograde.parse_result_json` parses it into a typed `AutogradeResult`.
Oracle's *code* is private; the JSON is the sole public contract surface.

### `result.json` schema (schema: 1)

```json
{
  "schema": 1,
  "assignment": "<name>",
  "commit": "<sha>",
  "honor_ok": true,
  "points": 60,
  "max": 60,
  "challenges": {
    "ward1": { "pass": true,  "points": 10, "max": 10 },
    "ward2": { "pass": true,  "points": 35, "max": 35 },
    "ward3": { "pass": true,  "points": 15, "max": 15 }
  }
}
```

Source: [`tests/integration/fixtures/autograde/result_allpass.json`](../../tests/integration/fixtures/autograde/result_allpass.json)

Top-level fields:
- `honor_ok` — boolean; `false` blocks credit even if challenges pass
- `points` — total earned points
- `max` — total possible points
- `commit` — head SHA of the graded submission (optional; used for audit)
- `challenges` — keyed by ward name → `{pass, points, max}`

### Lectern mapping (`AutogradeResult`)

`lectern.recon_autograde.parse_result_json(text)` returns:

```
AutogradeResult(
    honor_ok: bool,
    points:   int,
    max:      int,
    challenges: { key → Challenge(key, passed, points, max) },
    commit:   str | None,
)
```

### Fetch fallbacks (priority order)

1. **CI artifact** — `fetch_autograde_artifact`: downloads the `grading-result` artifact from the
   latest completed `autograde.yml` run. Preferred: students cannot delete run artifacts.
2. **In-repo file** — `fetch_autograde`: reads `grading/result.json` from the repo's default branch
   via the GitHub contents API.
3. **Log scrape** — `scrape_autograde`: parses `PASS <key>` / `FAIL <key>` lines from the run log.
   Legacy path for labs that pre-date the `result.json` contract. **Note:** do not use
   `jobs`-API step conclusions for Spellbreaker-style labs — `continue-on-error: true` masks every
   step conclusion as "success" regardless of outcome; the log lines are authoritative.

### Fixtures

| File | Scenario |
|---|---|
| [`result_allpass.json`](../../tests/integration/fixtures/autograde/result_allpass.json) | All wards pass, honor OK, 60/60 |
| [`result_partial.json`](../../tests/integration/fixtures/autograde/result_partial.json) | ward2 fails (0/35), total 25/60 |
| [`result_honorfail.json`](../../tests/integration/fixtures/autograde/result_honorfail.json) | `honor_ok: false`, partial credit |

### Test

`tests/integration/test_seam_autograde.py` — pure golden test (no live network), always runs under
`pytest -m suite`. Exercises all three fixture scenarios plus a malformed-JSON guard.

**Owner:** Oracle publishes; Lectern consumes. Contract version: `autograde: 1`.

---

## Seam C — Question-bank (Scriptorium → Lectern) — KNOWN GAP

**Direction:** Scriptorium → Lectern (intended; not yet working).

This seam is a tracked gap. It is documented here so the divergence is explicit and the closure
plan is recorded in one place.

### The two formats side by side

**Scriptorium format** (`tests/integration/fixtures/qbank/scriptorium_bank.md`):

```markdown
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
```

Scriptorium emits a **Markdown monolith**: `## <id>` section headers, YAML-like bullet lists
for fields, plain-text options with letter prefixes, and a single `- answer: X` line.

**Lectern format** (`tests/integration/fixtures/qbank/lectern_bank.md`):

````markdown
```yaml
id: m01
type: mc
points: 2
stem: "Which key encrypts an RSA message for a recipient?"
outcomes:
  - { key: a, text: "The sender's private key", credited: false, points: 0 }
  - { key: b, text: "The recipient's public key", credited: true, points: 2 }
  - { key: c, text: "A shared session key", credited: false, points: 0 }
  - { key: none, text: "No answer / multiple marks", credited: false, points: 0 }
```
````

Lectern's `qbank.load_bank` expects **YAML-fenced blocks**: each question is a `\`\`\`yaml` dict
with `id/type/points/stem/outcomes[{key,text,credited,points,accept}]`.  For `mc/tf/code` types a
`none` outcome is required (no-answer / multiple-marks slot).

### Two divergences

| Dimension | Scriptorium | Lectern |
|---|---|---|
| Serialization | Markdown-monolith (bullet lists) | YAML-fenced blocks (one dict per question) |
| Type coverage | Includes `sa` (short-answer) | Models `mc / tf / fib / code` — no `sa` |

### Impact

`lectern.qbank.load_bank` on a Scriptorium-format file finds zero `\`\`\`yaml` fences and returns
an empty bank. Exam assembly from a Scriptorium-authored question bank is not yet possible.

### Guard

`tests/integration/test_seam_qbank.py` carries a `@pytest.mark.xfail(strict=True)` on
`test_scriptorium_bank_is_not_yet_consumable`. The `strict=True` flag means the test **must fail**:
if an adapter ever lands and the assert starts passing, the strict xfail fires loudly, forcing an
explicit test update to the new contract.

### Closure plan

Tracked as a post-RC follow-up. Closure requires either:
- A Scriptorium adapter that translates the monolith format into YAML-fenced Lectern records, or
- A Lectern parser extension (`load_bank` variant) that accepts the Scriptorium format directly.

When closed, flip `xfail` → positive assertion and bump `seam_contracts.question_bank` to `1`.

**Contract version:** `question_bank: 0` (not stable).

---

## Release coupling

`SUITE.md` (repo root) is the single source of truth for which component versions are compatible
and which seam contracts are in force.

```yaml
suite: "LMS Suite"
release: "v0.1.0-rc1"
components:
  lectern:     ">=0.1.0,<0.2"
  scriptorium: ">=0.1.0,<0.2"
  oracle:      ">=0.1.0,<0.2"
seam_contracts:
  reading_list: 1     # reg-exam-readinglist CLI arg contract
  autograde:    1     # result.json schema:1
  question_bank: 0    # KNOWN GAP — not a stable contract yet
```

`reg-suite-check` (`python -m lectern.suite_check`) reads this matrix and verifies all installed
components against it. CI runs the same check via `tests/integration/test_seam_versions.py`.

### How `reg-suite-check` resolves versions

For **Lectern**: `importlib.metadata.version("lectern")`, falling back to `pyproject.toml`.

For **Scriptorium** and **Oracle**: searches for `package.json`, `VERSION`, or `pyproject.toml`
under a configured root directory (env var `LECTERN_SCRIPTORIUM_DIR` / `LECTERN_ORACLE_DIR`, or
default paths `~/git/scriptorium` and `/mnt/es2/opt/oracle` / `~/git/oracle`).

If a component's root directory does not exist or yields no version, `resolve_version` returns
`None`. `check()` maps `None` to a **SKIP** result (not a failure). Oracle is routinely absent on
development machines; its absence must not block `reg-suite-check`.

### `SUITE.md` version-constraint grammar

The constraint spec in each `components` value is parsed by `lectern.suite_check.in_range`:

**Operators:** `>=`  `>`  `<=`  `<`  `==`

**Combining:** comma separates clauses; all clauses must hold (logical AND).

**Normalization:** version strings are parsed into `(major, minor, patch)` tuples.
Extra numeric components beyond the third are truncated; missing components are zero-padded.
So `"0.2"` → `(0, 2, 0)` and `"0.1.0.4"` → `(0, 1, 0)`.

**Worked examples:**

| Call | Result | Reason |
|---|---|---|
| `in_range("0.1.0", ">=0.1.0,<0.2")` | `True` | At the lower bound; `(0,1,0) < (0,2,0)` |
| `in_range("0.1.9", ">=0.1.0,<0.2")` | `True` | Within range |
| `in_range("0.2.0", ">=0.1.0,<0.2")` | `False` | `(0,2,0)` is not `< (0,2,0)` |

---

## Running the integration tests

Integration tests are **opt-in** via a `suite` pytest marker (the default `addopts` in `pytest.ini`
/ `pyproject.toml` excludes them):

```bash
# Run only integration / seam tests
pytest -m suite

# Run everything (unit + integration)
pytest
```

### Skip-gating

Seam A (`test_seam_readinglist.py`) skips automatically when `node` is absent from PATH or
`exam-reading-list-cli.js` is not found at the Scriptorium root. The gate is declared at the top
of the test file as a `pytest.mark.skipif`.

Seam B (`test_seam_autograde.py`) and Seam C (`test_seam_qbank.py`) are pure-Python golden tests
and always run.

### Regenerating the reading-list golden

If Scriptorium's CLI output changes, update the golden file:

```bash
cd tests/integration
./regen.sh
```

`regen.sh` invokes the live CLI against the fixture lecture main and copies the output over
`fixtures/readinglist/demo_exam_reading_list.golden.md`. Commit the updated golden alongside any
CLI or fixture changes.
