# LMS Suite Integration — Design

- **Date:** 2026-06-21
- **Status:** Draft (awaiting review)
- **Author:** Anthony Giacalone (with Claude Code)
- **Repos in scope:** `agiacalone/lectern` (public, MIT), `agiacalone/scriptorium` (public, MIT), `agiacalone/oracle` (private, PolyForm Strict)

---

## 1. Context & goals

The teaching toolchain is now framed as a three-component suite — **Lectern · Scriptorium · Oracle**:

- **Lectern** — the Registrar: term/section lifecycle, gradebook, exam build/verify, lab recon/digest. Python, `pytest`. **It is the hub** — it both drives Scriptorium and consumes Oracle.
- **Scriptorium** — lecture-materials generator (notes, Cornell handouts, quizzes, slides, question banks, reading lists). Node.js, `vitest`.
- **Oracle** — the autograder "secret box" (`/verify` arbiter + gradebox sandbox runner). Python, `pytest`. **Private / licensed.**

The suite is moving toward an **official release candidate**. Before cutting it we need (a) **integration documentation** describing how the three fit together, and (b) an **integration test** that enforces those seams so they cannot drift silently. This spec designs both. It deliberately does **not** redesign any single component — it formalizes the boundaries between them.

**Goals**

1. Document every integration seam as a named, versioned **contract** (schema + example + ownership + current state).
2. Add a cross-component **integration test** to Lectern that exercises the live Scriptorium seam and golden-tests the Oracle and question-bank seams.
3. Pin a coordinated **release-compatibility matrix** with a checker, so the three components ship as a versioned set.
4. Fix the drift bugs the seam analysis already surfaced.

**Non-goals (out of scope for this spec)**

- **Closing the question-bank format gap** (Scriptorium ↔ Lectern). Documented + golden-tested as a known gap; the adapter is a tracked follow-up.
- A separate "suite" umbrella repo. Lectern is the hub.
- Full live end-to-end with a running Oracle in CI. Oracle is private; its public surface is its JSON contract.

---

## 2. The three seams (current, factual)

| Seam | Direction | Mechanism | State |
|---|---|---|---|
| **A · Reading-list** | Lectern → Scriptorium | `reg-exam-readinglist` shells out to `node exam-reading-list-cli.js` | ✅ Working |
| **B · Autograde** | Oracle → Lectern | `result.json` contract consumed by `recon_autograde` (CI-artifact → in-repo → log-scrape fallbacks) | ✅ Working |
| **C · Question-bank** | Scriptorium → Lectern | Scriptorium emits Markdown-monolith; Lectern `qbank.py` expects YAML-fenced blocks | ❌ Format-incompatible (known gap) |

### Seam A — Reading-list contract

Lectern-side wrapper reads `exam_reading_lists.yaml`, resolves each exam's topic `*_lecture_main.md` files, and invokes:

```
node <scriptorium>/exam-reading-list-cli.js \
  --exam-name <name> --slug <slug> --course <c> --term <t> \
  --out <dir> --mains <main1.md>,<main2.md>[,...] \
  [--textbook ...] [--citation-key ...] [--note ...] [--note-title ...]
```

→ emits `<out>/<slug>_reading_list.md`. Manifest schema (abridged):

```yaml
course: "CECS 378"
term: su26
lectures_dir: ../lectures           # relative to the manifest
exams:
  - { slug: midterm_1, name: "Midterm 1", topics: [topic_a, topic_b] }
```

**Drift bug found:** the wrapper's default skill dir is the retired `~/.claude/skills/lecture-materials-assistant`. Must point at `scriptorium` (keep the alias as a fallback). See §5.

### Seam B — Autograde contract

Oracle (or a lab's CI) publishes `grading/result.json`; Lectern's `recon_autograde.parse_result_json` parses it:

```json
{
  "schema": 1, "assignment": "spellbreaker", "commit": "abc123",
  "honor_ok": true,
  "challenges": {
    "ward1": {"pass": true,  "points": 10, "max": 10},
    "ward2": {"pass": false, "points": 0,  "max": 35}
  },
  "points": 10, "max": 100
}
```

→ `AutogradeResult(honor_ok: bool, points: int, max: int, challenges: dict[str, Challenge(passed, points, max)], commit)`. Three fetch strategies converge on the same dataclass: CI run-artifact (preferred), in-repo file, log-scrape (legacy). Oracle's *code* stays private; this JSON is the public seam.

### Seam C — Question-bank gap (documented, not closed)

Scriptorium `question-bank.js` emits:

```markdown
## m01
- type: mc
- difficulty: 1
- prompt: |
    A block device exposes...
- options:
    - A. A tree of named files
    - B. A flat array of blocks
- answer: B
```

Lectern `qbank.py` expects YAML-fenced blocks:

```yaml
- id: m01
  type: mc
  points: 2
  stem: "A block device exposes..."
  outcomes:
    - { key: a, text: "A tree of named files", credited: false, points: 0 }
    - { key: b, text: "A flat array of blocks", credited: true,  points: 2 }
    - { key: none, text: "No answer / multiple marks", credited: false, points: 0 }
```

Two divergences: **serialization** (markdown bullets vs YAML `outcomes[]`) and **type coverage** (Scriptorium has `sa`; Lectern qbank models `mc/tf/fib/code`). This spec encodes the gap as a strict-xfail test (§3) so closing it later flips a known signal.

---

## 3. Integration documentation deliverable

One document: **`lectern/docs/design/lms-suite-integration.md`**. Structure:

1. **Suite map** — the three components, their roles, language/test stack, and **license posture** (two public MIT, Oracle private/PolyForm). A diagram of hub-and-spoke data flow.
2. **One section per seam (A/B/C)** — direction, mechanism, **contract schema**, a worked example drawn from the demo course (§4), current state, and which repo owns the contract.
3. **The qbank gap** — honest write-up: why the two "question bank" concepts diverged, the impact, and the tracked decision to close it post-RC.
4. **Release coupling** — embeds/links the compatibility matrix (§6).

Each repo's README "suite" section cross-links this doc (Lectern hosts it; Scriptorium and Oracle link in).

---

## 4. The demo course is the shared integration fixture

`examples/cecs-378-demo/` does double duty — it is both the worked-example demo and the integration-test substrate. It gains the inputs each seam needs:

- **Seam A:** a minimal Scriptorium `*_lecture_main.md` + an `exam_reading_lists.yaml` manifest.
- **Seam B:** sample Oracle `result.json` fixtures (all-pass, partial, honor-fail).
- **Seam C:** a Scriptorium-emitted `*_question_bank.md` *and* a Lectern-format bank, side by side, to demonstrate the divergence.

The integration test reads from this one fixture course; the docs' worked examples point at the same files. One synthetic course, told three ways.

---

## 5. Integration test harness

Location: **`lectern/tests/integration/`**. Marked with a `suite` pytest marker so the default `pytest -q` matrix (Python 3.11–3.13) is unaffected unless explicitly selected.

| Test | Model | Behavior |
|---|---|---|
| `test_seam_readinglist.py` | **Live** | Locate Scriptorium via `LECTERN_SCRIPTORIUM_DIR` env or `~/git/scriptorium`; run `node exam-reading-list-cli.js` against the fixture lecture-main; assert the emitted `_reading_list.md` matches a golden (timestamps/paths normalized). `pytest.mark.skipif` when `node` or Scriptorium is absent. |
| `test_seam_autograde.py` | **Golden** | Feed committed Oracle `result.json` fixtures (all-pass / partial / honor-fail) through `parse_result_json`; assert the resulting `AutogradeResult`. Asserts the *contract shape* explicitly (distinct from existing unit tests). |
| `test_seam_qbank.py` | **Golden + gap-guard** | Assert Lectern qbank round-trips its own format; assert it **cannot yet** parse a Scriptorium-emitted bank via `@pytest.mark.xfail(strict=True)`. When the gap is closed, the xfail flips and forces the test to be updated. |
| `test_seam_versions.py` | **Matrix check** | Run the compatibility checker (§6); skip components not installed. |

**Golden fixtures** live in `tests/integration/fixtures/` and each carries a provenance header — producing tool, version, and the exact regen command — plus a `regen.sh`/`make regen-goldens` target. Drift becomes a deliberate, reviewed update rather than a silent pass.

**CI:** a new opt-in job (`integration` / `suite`) runs `pytest -m suite` with Node + a Scriptorium checkout available. The existing public Python matrix stays green and unchanged.

---

## 6. Release coupling — compatibility matrix + checker

**`SUITE.md`** (in lectern) is the source of truth for the coordinated release. It declares the suite version and the known-compatible component versions and seam-contract versions (ranges below are illustrative — actual pins are set at snapshot time from each repo's real version):

```yaml
suite: "LMS Suite"
release: "v0.1.0-rc1"
components:
  lectern:     ">=0.5.0,<0.6"
  scriptorium: ">=0.1.0,<0.2"
  oracle:      ">=0.3.0,<0.4"
seam_contracts:
  reading_list: 1
  autograde:    1     # result.json schema:1
  question_bank: 0    # gap; not yet a stable contract
```

**Checker:** `lectern/suite_check.py` (exposed as `reg-suite-check`) reads `SUITE.md`, resolves each installed component's version (Lectern: package metadata; Scriptorium: `package.json`; Oracle: its version file — skipped if absent), and compares against the ranges. Exit non-zero + a readable diff on mismatch. It is wired into `test_seam_versions.py` so version skew fails the suite test, and it is the gate Phase 4 runs before tagging.

---

## 7. How this slots into the RC

1. **Phase 2 — doc verify + per-repo tests green.** Each repo's docs conform; `pytest`/`vitest` green in all three.
2. **Phase 3 — integration test green.** `pytest -m suite` passes (live Scriptorium seam + golden Oracle/qbank + version matrix). The qbank gap is a *known* strict-xfail, not a failure.
3. **Phase 4 — snapshot + RC.** `reg-suite-check` passes against `SUITE.md`; tag each repo at the pinned versions (Oracle tagged privately); announce "LMS Suite v0.1.0-rc1".

---

## 8. File-by-file change list

**New**

- `lectern/docs/design/lms-suite-integration.md` — the integration doc (§3).
- `lectern/tests/integration/` — `test_seam_readinglist.py`, `test_seam_autograde.py`, `test_seam_qbank.py`, `test_seam_versions.py`, `fixtures/` (+ `regen.sh`).
- `lectern/SUITE.md` — compatibility matrix (§6).
- `lectern/suite_check.py` + `reg-suite-check` entry point.
- `examples/cecs-378-demo/` integration inputs: `*_lecture_main.md`, `exam_reading_lists.yaml`, `result.json` fixtures, a Scriptorium-format and a Lectern-format question bank.
- `.github/workflows/` — opt-in `suite` integration job (Node + Scriptorium checkout).

**Modified**

- `reg-exam-readinglist` wrapper — default skill dir `lecture-materials-assistant` → `scriptorium` (alias fallback). *(Drift fix.)*
- `pyproject.toml` — register the `suite` pytest marker; add `reg-suite-check` console entry.
- Each repo README "suite" section — cross-link the integration doc.
- Scriptorium + Oracle READMEs — link back to the Lectern-hosted integration doc.

---

## 9. Testing strategy

- The integration harness **is** the test deliverable; it must pass under `pytest -m suite` locally (with Node + Scriptorium present) and in the opt-in CI job.
- The public Python matrix must remain green with zero new required dependencies (the `suite` marker is opt-in).
- Golden regeneration is a single command and produces a reviewable diff.
- `reg-suite-check` has its own unit tests (version-in-range, out-of-range, component-absent).

---

## 10. Tracked follow-ups (post-RC)

1. **Close the question-bank gap** — adapter so a Scriptorium bank feeds `reg-exam-build` (decide `sa`-type handling). Flips the strict-xfail in `test_seam_qbank.py`.
2. Source the `reg-exam-readinglist` wrapper from the Lectern repo (today it lives only in `~/bin`).
3. Consider promoting the compatibility check into each component's own release CI.
