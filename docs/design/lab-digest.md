# Lab Writeup Digest (recon Layer-2) — Design

> `reg-lab-digest` — turn each student's lab writeup into an advisory
> `{score, comment}` against a rubric, merged into the recon cohort sheet/REPORT.
> Automates, as a reproducible contract, the manual Layer-2 grimoire pass first
> done by hand for CECS 378 Su26 Lab 1 (Spellbreaker), 2026-06-21.

## 1. Summary

`reg-lab-recon` sweeps a lab's student-repo population into a **deterministic**
bundle: autograde points (Part A, audit-grade), commit triage, and *structural*
writeup facts (`recon_docs.py` — frontmatter, sections, source count, raw text;
explicitly **no summarization**). The one thing it cannot do deterministically is
read a free-text writeup and judge it. That judgment — the recon REPORT's
**"Layer-2 writeup digest"**, long marked *pending* — is this feature.

The judgment needs an LLM; lectern is pure deterministic Python (pyyaml +
jsonschema, offline, no API key). So the LLM lives **outside** lectern, reached
through a **contract**: lectern emits a grading work-list and ingests validated
results. The fan-out (subagents / Claude Code) is the pluggable middle.

## 2. Decisions (brainstorm 2026-06-21)

| Decision | Choice | Why |
|---|---|---|
| LLM boundary | **Delegate via contract** | Keeps lectern dep-light, offline, reproducible. The scaffolding (emit/merge) is deterministic; only the middle is model-driven. Mirrors how the Lab 1 pass was actually run (parallel grading subagents). |
| Rubric format | **Structured rubric YAML** | Machine-readable sections + max points + anchors → bound into the grader prompt and validated against on merge. The markdown rubric stays the human doc. |
| Command shape | **Two-phase `reg-lab-digest emit` / `merge`** | The deterministic ends bracket the harness fan-out. Re-runnable; either end testable in isolation. |
| Output | **Advisory only** | `merge` fills the REPORT ➊ table's *Writeup/Proposed* columns; it **never** writes to `reg-gradebook`. Grades stay the instructor's call (Part B doctrine). |

## 3. Data flow

```
reg-lab-recon ──► bundle/ (cohort.csv, repos/<id>.json incl. writeup raw text)
                      │
   rubric.yaml ──►  reg-lab-digest emit
                      │
                      ▼
              digest_tasks.jsonl   +   digest.schema.json
                      │
            [harness fan-out: agents grade each task → schema]
                      │
                      ▼
              digest_results.jsonl
                      │
   rubric.yaml ──►  reg-lab-digest merge ──► cohort.csv (+writeup_score/comment)
   bundle/      ──►                          REPORT.md  (➊ Writeup/Proposed filled)
```

`emit` and `merge` are pure functions of their inputs — same
`(bundle, rubric, results)` ⇒ same output.

## 4. Rubric YAML

```yaml
# spellbreaker.rubric.yaml
lab: "Lab 1 — Symmetric Cryptography (Spellbreaker)"
total: 30                      # grimoire points (the manual part; wards are autograded)
comment_max_chars: 140
sections:
  - { key: ward1,  label: "Ward I — ECB detection",        max: 5,
      requires_cleared: ward1,                              # un-cleared ⇒ forced 0 on merge
      anchors: { strong: "...", adequate: "...", weak: "...", missing: "..." } }
  - { key: ward2,  label: "Ward II — byte-at-a-time",       max: 10, requires_cleared: ward2, anchors: {...} }
  - { key: ward3,  label: "Ward III — CBC bit-flipping",    max: 9,  requires_cleared: ward3, anchors: {...} }
  - { key: craft,  label: "Sources + craft",                max: 6,  anchors: {...} }
bonus:
  - { key: omega,  label: "OMEGA — padding oracle",         max: 4,  requires_cleared: ward4, anchors: {...} }
cap: 30                        # total incl. bonus is capped here
```

`requires_cleared` names an **autograde** key (from the recon manifest's
`autograde.steps`). On merge, a section whose ward was not cleared is forced to 0
— the partial-ward rule is enforced deterministically, never trusted to the model.
Module `lectern.digest_rubric` parses + validates this (max ≥ 0, keys unique,
Σmax of core sections == total, bonus capped by `cap`).

## 5. Phase `emit`

`reg-lab-digest emit --bundle <dir> --rubric <yaml> --out digest_tasks.jsonl`

For each repo record in the bundle, write one task object:

```json
{ "github_id": "gh-user-06",
  "student": "Selina Kyle",
  "writeup_text": "<full WRITEUP.md body, frontmatter stripped>",
  "autograde": { "points": 70, "cleared": ["ward1","ward2","ward3","ward4"], "honor_ok": true },
  "rubric": { ...embedded rubric... },
  "schema": { ...embedded output schema... } }
```

- Writeup text comes from the bundle (recon already captured `raw_path`; `emit`
  reads it, strips frontmatter, caps length).
- `cleared` is derived from the autograde result so the grader knows which
  sections are in play (and the merge can enforce it).
- **Honor-gate / non-submission short-circuit:** repos with `honor_ok == false`
  or zero autograde get a task flagged `skip: true` (grimoire 0, no model call).
- Also writes `digest.schema.json` (§7) next to the tasks file.

## 6. The fan-out (harness, not lectern)

Documented contract, not lectern code. An agent (or N parallel subagents) reads
`digest_tasks.jsonl`, and for each non-skipped task scores the writeup against the
embedded rubric+anchors, appending one line to `digest_results.jsonl` per §7.
Reference prompt template ships in `docs/lab-digest-grader-prompt.md`. The
`superpowers:dispatching-parallel-agents` pattern is the canonical runner; a
single agent works for small cohorts.

## 7. Output schema (`digest.schema.json`)

```json
{ "github_id": "string",
  "sections": { "ward1": 0, "ward2": 0, "ward3": 0, "craft": 0 },
  "bonus":    { "omega": 0 },
  "total":    0,
  "comment":  "string (<= comment_max_chars)",
  "confidence": "high | medium | low",
  "abstain":  false }
```

JSON-Schema validated at merge. `total` is advisory; merge recomputes the
authoritative total from sections (so a model arithmetic slip can't change a grade).

## 8. Phase `merge`

`reg-lab-digest merge --bundle <dir> --rubric <yaml> --results digest_results.jsonl`

For each result, in order:
1. **Validate** against `digest.schema.json`; structurally invalid ⇒ flag
   `digest:invalid`, skip (leave Writeup blank/pending).
2. **Enforce partial-ward zeroing** — any section whose `requires_cleared` ward is
   not in the autograde `cleared` set is forced to 0.
3. **Recompute total** = min(cap, Σ core sections + Σ bonus). The model's `total`
   is ignored except as a cross-check (mismatch ⇒ `digest:total-drift` flag).
4. **Truncate / reject comment** over `comment_max_chars`.
5. **Confidence gate** — `confidence == low` or `abstain` ⇒ score withheld,
   flagged `needs-human-read` (Writeup stays *pending*, not a silent number).
6. **Merge** into `cohort.csv` (`writeup_score`, `writeup_comment`, optional
   `writeup_breakdown`) and fill the REPORT **➊ table** *Writeup* + *Proposed*
   (= Auto + Writeup) columns, marked advisory.

`merge` **never** writes a scores CSV or touches `reg-gradebook`. Promotion to the
gradebook stays the existing separate, human-confirmed step.

## 9. Units

| Module | Job | Depends on |
|---|---|---|
| `lectern.digest_rubric` | parse + validate rubric YAML → `Rubric` | pyyaml |
| `lectern.digest_emit` | bundle + rubric → tasks.jsonl + schema | recon bundle, digest_rubric |
| `lectern.digest_schema` | the output JSON-Schema + a validator | jsonschema |
| `lectern.digest_merge` | results + bundle + rubric → cohort/REPORT | digest_schema, digest_rubric |
| `lectern.lab_digest` (CLI) | `emit` / `merge` subcommands | the above |

## 10. Testing

- **digest_rubric:** valid parse; rejects bad totals (Σcore ≠ total), dup keys, negative max, bonus over cap.
- **digest_emit:** task shape; frontmatter stripped; `cleared` derived from autograde; honor-fail ⇒ `skip`.
- **digest_merge:** schema-invalid rejected; **partial-ward zeroing** (un-cleared ward forced 0 even if the model scored it); total recomputed + capped; `total-drift` flagged; over-length comment handled; low-confidence ⇒ `needs-human-read`, no number; advisory columns filled, **gradebook untouched**.
- **Fixtures:** synthetic Batman-cast writeups (Harley = thorough, Joker = empty/honor-fail, Riddler = plausible-but-wrong → exercises confidence + partial-ward paths).

## 11. Integration + follow-ups

- Recon stays the upstream sweep; digest is a follow-on (not folded into the recon
  phases — keeps the model boundary explicit and the bundle re-usable).
- A later convenience could derive `*.rubric.yaml` ⇄ the markdown rubric, so the
  human doc and the machine contract can't drift. Out of scope here.
- First consumer: Spellbreaker (`spellbreaker.rubric.yaml`). The Lab 1 Su26 pass is
  the golden reference for the fixtures' expected behavior.
