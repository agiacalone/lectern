# `reg-lab-report deliver --from-note` — note-authoritative feedback — Design

> Make the **grading-round note authoritative**: the per-round report note
> (`recon-<lab>/REPORT.md`) holds every student's graded feedback, and
> `reg-lab-report deliver` *reads* it to render each repo's `FEEDBACK.md`. Replaces
> the digest-cohort re-render path for hand-graded labs, so the tool never clobbers
> hand-authored feedback. Fits lectern doctrine: the vault is the proprietary record;
> the tool is a deterministic renderer over a parseable contract.

## 1. Why

Doctrine (2026-06-28): each grading round = **one note** holding cohort facts +
grades + all per-student FEEDBACK, edited in place as grading proceeds. The existing
`deliver --cohort` re-renders `FEEDBACK.md` from `templates/feedback.md` + a
digest-merged `cohort.csv`, which would **overwrite** feedback authored in the note.
The fix inverts the source of truth: parse the note → rows → render → deliver. Same
principle as the deliverable-naming and `result.json` contracts — the artifact
conforms to a machine-consumable shape.

## 2. The note block contract (`lectern.feedback_note`)

One block per student under the note's per-student-feedback section, keyed by github id:

```
### <Display Name> — **<total> / <grand>**
`<github_id>` · [repo](<url>)
<Comp1> <n>/<max> · <Comp2> <n>/<max> · … · <CompK> +<n>/<max>
_Comments:_ <student-facing prose, until the next ### / ## / EOF>
```

- **Key** — the first backtick-quoted token (`<github_id>`); repo = `repo_prefix-<github_id>`.
- **Total** — the `**x / y**` on the heading; `__`/`—` ⇒ ungraded → `graded=False`, skipped by deliver.
- **Components** — the `·`-delimited `Label n/max` tokens, **self-describing from the note** (leading `+` marks extra credit). No per-lab component manifest needed — the note declares them.
- **Comments** — text after `_Comments:_` to the next heading; HTML comments stripped; run through `feedback_sanitize` before delivery.

`parse_feedback_note(path) -> [{github_id, student, total, grand, components, comment, graded}]`.
Tolerant of `__`/blank cells and pre-filled HTML-comment placeholders.

## 3. Surface

```
reg-lab-report deliver --from-note <REPORT.md> --manifest <lab>.report.yaml [--only … --skip … --execute]
```

`--from-note` and `--cohort` are mutually exclusive (one required). The manifest still
supplies delivery metadata (org, repo_prefix, course/term/section, lab name, feedback
branch + PR); grades/grand/components/comment come from the note. Everything downstream
— signing (mandatory), PR close, signed merge-to-main, idempotency, `FEEDBACK_LOG.md` —
is unchanged.

## 4. Units

| Module | Change |
|---|---|
| `lectern.feedback_note` (new) | parse note → rows; self-describing components; skip ungraded |
| `lectern.feedback_deliver` | `render_feedback_md_from_note` (N-component table); `deliver(..., render=)` injectable + reads `total`/`grand`/`components` from the row; `main()` adds `--from-note` (xor `--cohort`) |
| `lectern.feedback_log` | tolerant: component breakdown + per-row `grand` for note-path entries; Auto/Writeup unchanged for the digest path |
| `lectern.feedback_sanitize` | unchanged — run on each parsed comment |

The digest path (`--cohort`, Wards/Grimoire) is untouched — both paths share `deliver()`,
`_merge_to_main`, and the signing/idempotency guarantees.

## 5. Testing

- **Parser** (`tests/test_feedback_note.py`): one row per block; ungraded `__` flagged; components incl. EC + max; multi-line comment captured, HTML stripped; gid not confused by backticks in the comment; non-score lines rejected.
- **Render/deliver** (`tests/test_feedback_deliver.py`): N-component table + EC row; zero-total non-submission note; `deliver` reads note total + injected renderer; signed execute path. Synthetic Batman cohort fixtures.
- Full suite green (no regression to the digest/Spellbreaker golden path).

## 6. Out of scope / follow-ups

- Embedding the per-student breakdown into the **merge commit** message (`MERGE_MSG` is fixed today) — the breakdown rides in `FEEDBACK.md` until then.
- A `report.yaml ⇄ markdown rubric` derive (shared follow-up with digest).
