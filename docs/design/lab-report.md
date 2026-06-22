# `reg-lab-report` — Instructor Lab Report + Feedback Delivery — Design

> `reg-lab-report` — lectern **Layer 3**. Deterministically renders the canonical
> *instructor report* for a lab (all facts + scores + graphs + grading
> recommendations) from the recon bundle + digest results, and — separately gated —
> **delivers** sanitized, GPG-signed feedback to each student via their repo's
> `feedback` branch. Productizes the manual close-out first done by hand for
> CECS 378 Su26 Lab 1 (Spellbreaker), 2026-06-21.

## 1. Summary

The lectern grading pipeline today is:

```
reg-lab-recon  (Layer 1 — Part A facts: autograde, honor-gate, commit triage, writeup structure)
reg-lab-digest (Layer 2 — Part B advisory: LLM-scored writeup {score, comment} via contract)
reg-gradebook  (consolidate per-component scores → gradebook.csv / GRADEBOOK.md)
```

Two gaps remain, both exercised manually during the Su26 Lab 1 close-out:

1. **The instructor report is not a product.** `REPORT.md` is assembled by an
   *agent workflow* (`docs/recon-report-workflow.md`), so it is neither
   reproducible nor consistent term-to-term.
2. **Feedback delivery is not a product.** Posting a sanitized grade breakdown +
   comment to each student (signed commit to the `feedback` branch, close the
   feedback PR) was done by hand — no tooling, no record contract.

`reg-lab-report` fills both as a **Layer-3** verb with two subcommands:
`render` (read-only report) and `deliver` (outward-facing feedback push). It stays
pure-deterministic offline Python; the sole LLM touchpoint remains the existing
digest contract (extended here with a student-facing comment field).

See [[2026-06-21-lab-digest-design|the lab-digest design]] (Layer 2) and
[[classes/378-478/archives/su26-01/recon-lab1/REPORT|the Su26 Lab 1 report]] +
[[classes/378-478/archives/su26-01/recon-lab1/FEEDBACK_LOG|FEEDBACK_LOG]] — the
manual artifacts this product reproduces and the golden reference for tests.

## 2. Decisions (brainstorm 2026-06-21)

| Decision | Choice | Why |
|---|---|---|
| Pipeline position | **New Layer-3 verb `reg-lab-report`** | Consumes recon+digest; report becomes reproducible (same inputs ⇒ same bytes). Replaces the agent-assembled recon-report-workflow. |
| Command shape | **Two subcommands: `render` / `deliver`** | Firewalls the read-only report from the outward-facing push. `render` is safe to run anytime; `deliver` is gated. |
| Report density | **Dense, agate, detailed** | All info, breakdowns + tables, per the newspaper/agate register. "Pack in as much as we can." |
| Recommendations | **4 deterministic buckets** | Proposed-final + confirm list · edge cases needing a call · low-confidence/needs-human-read · upward-adjustment candidates. All derived from facts; advisory only. |
| Graphs | **Unicode agate charts** | Deterministic, zero-dependency, renders in Obsidian/GitHub/plain-text/print. lectern stays offline. |
| Student-facing comment | **Extend the digest contract** | Add `student_comment` to the digest output schema/grader-prompt — one grading pass yields internal `comment` + sanitized student prose. Judgment stays in the existing LLM boundary; lectern only assembles. |
| Sanitization safety | **Deterministic lint, withhold on fail** | A merge-time lint scans `student_comment` for internal tokens (triage words, "honor-gate", grader-tool names, other students' names) → flag + withhold from delivery. Internal `comment` is never sent to students. |
| Delivery safety | **Dry-run default · signing mandatory · idempotent** | Outward-facing + hard-to-reverse. `--execute` required to push; refuses unsigned; skips unchanged repos; auto-logs a verbatim record. |
| Default-branch visibility | **Merge `feedback` → `main` after the PR closes** | A `FEEDBACK.md` that lives only on the `feedback` branch is invisible on the student's repo home. `deliver` merges it onto the default branch with a **signed** merge commit (signing enforced on the merge too). Classroom repos whose `main`/`feedback` share **no common ancestor** can't be merged — `deliver` lands the file directly on `main` with a signed commit instead. Idempotent independently of the feedback branch (probes `git show main:FEEDBACK.md`); `--no-merge-main` opts out. |

## 3. Architecture & data flow

```
recon bundle/ ─┐
digest results ─┼─►  reg-lab-report render  ─►  REPORT.md      (canonical instructor report)
gradebook       ┘        (read-only)

REPORT inputs ─┐
digest         ─┼─►  reg-lab-report deliver ─►  per-repo feedback branch (signed FEEDBACK.md)
report manifest ┘        (--dry-run default;     feedback PR #1 closed
                          --execute to push)     feedback → main (signed merge; shows on default branch)
                                                 FEEDBACK_LOG.md + provenance (verbatim record)
```

`render` is a pure function of `(bundle, digest_results/cohort, standing, manifest)`.
`deliver` is the only side-effecting path; in `--dry-run` it is also pure (prints a
plan, writes nothing remote).

### Inputs

- **recon `bundle/`** — `cohort.csv`, `repos/<id>.json`, `writeups/<id>.md`,
  `bundle.json` (from `reg-lab-recon`).
- **digest results** — **canonically** the digest-merged `cohort.csv` (carries
  `writeup_score`, `writeup_comment`, **`student_comment`**, `writeup_flags`); render
  reads from there. (`digest_results.jsonl` is not a render input — merge into the
  cohort first.)
- **gradebook standing** (optional) — `gradebook.csv` for the weighted-standing and
  letter-boundary signals used by the upward-adjustment recommendations.
- **report manifest** — small YAML (`<lab>.report.yaml`): wards/labels, points split
  (auto max, writeup max), letter cuts, org/repo prefix, feedback-branch + PR
  conventions, the per-student `FEEDBACK.md` template id. Reuses recon manifest
  fields where possible (org, repo_prefix, total_points).

## 4. `render` — the instructor report

`reg-lab-report render --bundle <dir> --cohort <cohort.csv> [--standing gradebook.csv]
--manifest <lab>.report.yaml --out REPORT.md`

Deterministic markdown assembly (f-strings + helpers, no jinja2 — matches existing
lectern rendering). Sections, in order:

1. **Header + synthesis** — lab/course/section/term/n; cohort narrative; distribution
   stats (mean, median, σ, range, perfect-score count).
2. **Agate graphs** (`report_charts`):
   - Grade distribution (A/B/C/D/F bars).
   - Score histogram (10-pt bins).
   - Ward-clear funnel (per challenge key, from autograde `cleared` counts).
   - Auto-vs-writeup split (table: how many full-auto students landed at each writeup tier).
3. **➊ Grade table** — per student: `Auto /<autoMax>` · `Writeup /<wMax>` · **Proposed**
   (= Auto + Writeup) · basis (one line) · flags.
4. **Grading recommendations** — four subsections (`report_recommend`, §6).
5. **Per-student detail** — breakdown table (per-section writeup points) + the internal
   `writeup_comment` + a link to delivered feedback (when present).
6. **Departed / non-submission** — withdrawn/dropped/honor-fail, with status + basis.
7. **Canvas entry sheet** — Last, First → Proposed, roster-ordered, with a posted-status
   column (filled after `deliver`).
8. **Delivered-feedback status** — populated by `deliver`: per student posted? signed✓?
   PR state. Blank/"not yet delivered" before the first deliver.
9. **Provenance & caveats** — tooling + versions, reproducibility note, and the
   **Part-A-facts / Part-B-advisory firewall** statement (hard git facts = audit-grade;
   heuristic/LLM scores = advisory, instructor-confirmed).

Output is the canonical `REPORT.md` in the lab's archive folder (the same location the
agent workflow wrote to). Idempotent overwrite; a `--check` mode diffs against the
existing file without writing (for CI/regression).

## 5. Agate charts (`lectern.report_charts`)

Pure helpers returning markdown-safe strings:

- `bar_chart(rows, label_w, max_w)` — `LABEL ▏████ value`, block-char scaled to the max.
- `histogram(values, bins)` — binned counts → bars.
- `funnel(stages)` — ordered descending bars (ward-clear).

Block glyph `█` with `▏` left rule; counts right-aligned; deterministic width scaling.
No color (markdown), no Unicode beyond block elements (renders in print + GitHub).
Unit-tested on bin edges, zero counts, and width scaling.

## 6. Recommendations engine (`lectern.report_recommend`)

Pure rules over `(cohort, autograde, digest flags, standing, manifest)`. Emits four
buckets; **advisory only** — never writes scores. Each item carries the *evidence*
(the fact that triggered it) so the instructor can confirm fast.

| Bucket | Rule basis |
|---|---|
| **Confirm list** | Routine pass-throughs: honor_ok, no triage flag, digest confidence ≥ medium, no partial-ward zeroing surprise. "Confirm these N." |
| **Edge cases needing a call** | honor-gate fail · non-submission / late-policy · wrong-section · triage bucket ∈ {REVIEW, FLAG}. The decisions only the instructor can make. |
| **Low-confidence / needs-human-read** | digest `abstain` or `confidence == low` · partial-ward zeroing applied · digest total-vs-recomputed drift · `student-comment:needs-review` lint hit. Anywhere the automated number shouldn't be trusted blind. |
| **Upward-adjustment candidates** | Standing within a configurable band below a letter cut (e.g. ≤1.0 pt under), or progress-ratchet signal. Surfaced for discretionary bumps per the upward-adjustment doctrine — never auto-applied. |

Each rule is independently testable; one fixture per flag path.

## 7. Digest extension — `student_comment`

The digest's `comment` is *internal* terse shorthand (≤140 chars). Delivery needs
*student-facing* prose. Extend the **existing** digest contract rather than add a new
LLM pass:

- **Schema** (`digest.schema.json` / `digest_schema.py`): add required field
  `student_comment` (string, ≤ `student_comment_max_chars`, default ~600).
- **Grader prompt** (`docs/lab-digest-grader-prompt.md`): instruct the model to emit,
  alongside the internal comment, a constructive student-facing comment —
  mechanism-focused, no cross-student comparison, no internal triage jargon, the lab's
  in-world vocabulary OK, **AI disclosure never penalized**.
- **Merge** (`digest_merge.py`): carry `student_comment` into `cohort.csv`; run the
  **sanitization lint** (§8). Low-confidence/abstain ⇒ `student_comment` withheld
  (delivery falls back to score-only or skips, instructor's call).

This is a backward-compatible additive change to the Layer-2 contract; existing digest
tests extend to cover the new field.

## 8. Sanitization lint (`lectern.feedback_sanitize`)

Deterministic guard run at digest-merge and again at deliver-time:

- **Blacklist token classes:** triage words (`REVIEW`, `FLAG`, `PASS` as a verdict),
  `honor-gate`/`honor gate`, grader/tool names (`digest`, `recon`, `oracle`, model
  names), advisory framing (`advisory`, `screening`), and **other students' display
  names / github ids** (from the cohort) — cross-student leakage is the worst failure.
- A hit ⇒ `student-comment:needs-review`; the comment is **withheld from delivery**
  until cleared (surfaced in the report's low-confidence bucket).
- The internal `comment` is *structurally* never a delivery input — only
  `student_comment` is read by `deliver`.

## 9. `deliver` — feedback to students

`reg-lab-report deliver --bundle <dir> --cohort <cohort.csv> --manifest <lab>.report.yaml
[--only <id>...] [--skip <id>...] [--execute] [--no-close]`

Per enrolled repo (mirrors the validated 2026-06-21 manual run, hardened):

1. Render `FEEDBACK.md` from `templates/feedback.md`: total + a breakdown table
   (Auto /autoMax + Writeup /wMax) + the `student_comment` + a footer line.
   Non-submission ⇒ neutral templated note.
2. Clone the repo's `feedback` branch (single-branch), drop `FEEDBACK.md`.
3. `git commit -S` (signing **mandatory**; per-clone user.name/email/signingkey set;
   refuse to proceed if the commit is unsigned).
4. `git push origin feedback`.
5. `gh pr close 1` if the feedback PR is OPEN (skip MERGED/CLOSED; `--no-close` to
   suppress).
6. **Auto-log:** append/emit `FEEDBACK_LOG.md` (verbatim student-facing text + score +
   github link + signature/PR status, score-ordered) and a provenance line into the
   archive — the disputable record.

**Safety contract:**
- **`--dry-run` is the default.** Without `--execute`, prints the per-repo plan + the
  `FEEDBACK.md` it *would* push; writes nothing remote.
- **Idempotent.** Skip repos whose `feedback`-branch `FEEDBACK.md` already matches.
- **Signing verified.** Optionally confirm GitHub `verification.verified == true`
  post-push.
- **All GitHub/git ops go through injected callbacks** (`gh=`, `git=`) — mockable,
  matching lectern's existing `recon` pattern; no PyGithub.

## 10. Units

| Module | Job | Depends on |
|---|---|---|
| `lectern.report_manifest` | parse + validate `<lab>.report.yaml` | pyyaml |
| `lectern.report_charts` | agate chart primitives | — |
| `lectern.report_recommend` | the 4 recommendation buckets | cohort/standing |
| `lectern.report_render` | bundle+digest+standing → REPORT.md | charts, recommend, manifest |
| `lectern.feedback_sanitize` | student_comment lint | cohort (names) |
| `lectern.feedback_deliver` | feedback-branch + signed-commit + PR ops | gh/git callbacks |
| `lectern.feedback_log` | FEEDBACK_LOG.md + provenance | — |
| `lectern.lab_report` (CLI) | `render` / `deliver` subcommands | the above |
| digest edits | `student_comment` in schema/emit/merge + grader-prompt | existing digest |
| templates | `instructor-report.md`, `feedback.md`, `feedback-log.md` | — |

## 11. Testing

- **Golden render:** the Spellbreaker Su26 Lab 1 cohort (this session) → a known
  `REPORT.md` byte-for-byte; the manual `REPORT.md`/`FEEDBACK_LOG.md` are the oracle.
- **Charts:** bin edges, zero counts, width scaling, label alignment.
- **Recommendations:** one fixture per flag path (honor-fail, REVIEW/FLAG triage,
  abstain, partial-ward zeroing, total-drift, near-letter-cut bump).
- **Sanitize lint:** catches each blacklisted token class incl. cross-student names;
  passes clean prose.
- **Digest extension:** `student_comment` required, length-capped, withheld on
  low-confidence.
- **deliver (mocked gh/git):** dry-run plan; idempotency skip; **signing-required
  refusal**; non-submission note; PR-state handling (OPEN→close, MERGED/CLOSED→leave);
  `--only`/`--skip`; FEEDBACK_LOG emitted.
- **Fixtures:** Batman synthetic cohort — Harley (thorough, full clear), Joker
  (honor-fail / non-submission), Barbara Gordon (model student), Riddler
  (plausible-but-wrong → low-confidence + lint paths).

## 12. Integration & follow-ups

- `render` supersedes `docs/recon-report-workflow.md` as the REPORT producer; the
  workflow doc is retired/redirected to this tool.
- Promotion to `reg-gradebook` stays the existing separate, human-confirmed step —
  `reg-lab-report` is report + delivery, never a grade writer.
- **Docs surface** (per the LMS-suite reader-docs rule): `CHANGELOG.md`, a `SKILL.md`
  command entry, `README.md`, and `docs/design/lab-report.md` in the lectern repo.
- Spec + plan authored vault-first ([[2026-06-21-lab-report-design]] +
  [[2026-06-21-lab-report-plan]]); mirror to the lectern repo `docs/design/` when
  implementation starts.
- **Sequencing:** deferred behind the [[2026-06-21-lms-suite-integration-plan|LMS-suite
  integration]] — implemented *after* that lands, as its **own feature branch → PR**
  against `agiacalone/lectern`. Status: spec + plan complete, execution parked.
- Out of scope: a `report.yaml ⇄ markdown rubric` derive (shared with digest's
  same follow-up); multi-lab term roll-up reports.
