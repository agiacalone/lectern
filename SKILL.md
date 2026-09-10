---
name: lectern
description: Course/teaching operations for a CSULB lecturer — the Registrar. Term + section lifecycle (create/finalize/archive), gradebook consolidation, exam build/verify with per-student serials, ISA Drive publishing, GitHub Classroom binding, LMS roster/grade import. Trigger on grading close-out, starting a new term, building/verifying exams, importing rosters or grades, publishing to ISAs, or any reg-* command.
---

# Lectern — Course Operations Skill

Lectern is the operational/records counterpart to `lecture-materials-assistant`
(which generates lecture content). It owns "the Registrar": the lifecycle and
records of running courses. All tools are vault-aware via an explicit
`--vault-root` argument — no hard-coded vault paths and no external vault package
(the one `slugify` helper is vendored into `lectern/_text.py`).

## Wrappers (reg-*)

| Wrapper | Module | Purpose |
|---|---|---|
| `reg-term-create` | term_create | Scaffold a term from a YAML term-spec (semester note + class notes + manifest skeletons + MOC wiring), idempotent; `--init` writes a stub spec |
| `reg-term-finalize` | term_finalize | Reconcile grade distributions + flip statuses to finalized + roll up enrollment-weighted aggregates; `--dry-run`, `--allow-missing` |
| `reg-term-archive` | term_archive | Per-section archive bundle orchestrator + `--check` drift validator |
| `reg-gradebook` | gradebook | Consolidate normalized grades+roster into gradebook.csv/.md |
| `reg-exam-build` | exam_build | Assemble exam PDF(s) — single-source `.tex` or pack-mode `.yaml` (multi-form, individualized, Gradescope products) |
| `reg-exam-verify` | exam_verify | Verify a student exam serial against the registry |
| `reg-exam-readinglist` | (standalone → lecture-materials) | Generate consolidated per-exam reading-list study guides from an exam→topics manifest |
| `reg-lms-grades-import` | lms_grades | Normalize a Canvas grades.csv export |
| `reg-lms-roster-import` | lms_roster | Normalize a CSULB faculty-center roster export |
| `reg-c50` | c50 | **Classroom 50** — the GitHub Classroom successor (legacy sunset 2026-08-28). `classroom-add` creates one classroom per section from the term-spec · `codes` mints the per-section self-enrollment codes · `roster-import` turns collected GitHub usernames into a roster + org invitations · `post` registers a lab as an assignment in every section that teaches it, binds it into the class notes, and writes the Canvas announcement · `status` reads back what is actually registered. Resolves org, classroom, slug, template, points and due date from the vault rather than the command line |
| `reg-classroom-roster-seed` | classroom_seed | ==**RETIRED** — legacy GitHub Classroom, and it never worked live== (it POSTed to a read-only endpoint). Kept only so old runbooks resolve. Use `reg-c50 roster-import` |
| `reg-github-bind` | github_bind | Bind student GitHub IDs to roster entries |
| `reg-isa-publish` | isa_publish | Publish ISA grading artifacts to Drive (rclone/gdrive backend) |
| `reg-gradescope-stats` | gradescope_stats | Per-outcome **item analysis** from Gradescope *Export Evaluations* — per-distractor stats joined to grading-note `form·Qn·slot` keys (dead/over-key distractors, miskey alarm); emits `ITEM_ANALYSIS.md` newspaper broadsheet + `item_scores` matrix |
| `reg-triage` | triage | Git-history **authenticity triage** for GitHub Classroom submissions: `init` scaffolds a manifest, `sweep` scores a class into FLAG/REVIEW/PASS (CSV + Markdown broadsheet; org-`scrape` repo discovery post-Classroom), `report` emits a two-tier audit doc with a sanitized `--release` variant, `rhythm` flags cross-assignment commit-rhythm shifts. 100% triage — no student penalized without human review |
| `reg-syllabus` | syllabus | Generate course syllabi from Markdown with a tamper-evident control-number serial: `stamp` injects a repo-tree SHA-256 + register row, `build` renders `syllabus.html` + a Canvas-RCE-safe `syllabus_canvas.html` (`--pdf` opt-in, print only) |
| `reg-lab-recon` | recon | Sweep a lab's student-repo population into a deterministic **recon bundle** (Part A facts): per-repo autograde points (parsed from CI logs), honor gate, commit triage, structural writeup facts → `cohort.csv` + `FACTS.md` + a two-tier cohort-intelligence `REPORT.md`. Advisory; no student graded without human review |
| `reg-lab-digest` | lab_digest | **Layer-2 writeup digest** over a recon bundle: `emit` a grading work-list (writeups + rubric YAML + output schema), then `merge` model-graded results into the cohort sheet as advisory writeup scores + rationale comments. LLM grading runs in the **harness via a contract** (no API dep in lectern); deterministic guardrails — partial-ward zeroing from autograde truth, total recompute, confidence gating. Results carry both an internal `comment` and a sanitized `student_comment`. **Never writes the gradebook** |
| `reg-lab-report` | lab_report | **Layer-3 instructor report + feedback delivery.** `render` → the canonical `REPORT.md` (distribution + agate charts, grade table, four-bucket grading recommendations, Canvas entry sheet) deterministically from the recon bundle + digest cohort. `deliver` → a sanitized, GPG-signed `FEEDBACK.md` to each repo's `feedback` branch, closes the feedback PR, **then merges `feedback` into `main`** (signed; direct-add fallback for unrelated-history repos) so it shows on the student's default branch; **`--dry-run` by default**, signing mandatory, idempotent (feedback + main independently; `--no-merge-main` opts out), emits a verbatim `FEEDBACK_LOG.md`. Feedback source is either the digest cohort (`--cohort`) or — **note-authoritative** — the grading-round note itself (`--from-note <REPORT.md>`), parsing per-student blocks so hand-authored feedback is delivered verbatim, never re-derived (N generic components). Trigger after grading a lab to produce the instructor report and/or post feedback to students |
| `reg-admin-form` | admin_form | **Administrative forms** — fill a campus form (Notice of Absence, …) from the vault's own records. A YAML *form profile* declares the fields; the engine resolves them from the term-spec, class-notes and syllabi, and emits a copy/paste `FORM.md`, a routing `EMAIL.md`, and a machine `record.yaml`. Computes which class meetings an absence actually costs (meeting patterns × campus closures) and what topic each was going to cover. Adding a form is a profile, not code. Slash command: `/timeoff` |

Library modules (no wrapper): `exam_serial`, `manifest_schema`, `student_id`,
`drive_auth`, `isa_publish_schema`, `class_calendar`. Triage engine: `triage_signals`, `triage_engine`, `triage_manifest`, `triage_rhythm`, `triage_scrape`, `triage_version`. Plus `syllabus_serial`, `qbank`.

## Exam reading-list study guides (`reg-exam-readinglist`)

A quiz/exam is a short exam; an **exam reading-list** is the consolidated, per-exam
study guide — the multi-topic companion to the single-topic lecture reading lists,
mapping each covered handout's Cornell cues to their textbook sections (the
`final_third_reading_list` pattern).

`reg-exam-readinglist` is a standalone wrapper (run via the lectern
venv) that drives the **lecture-materials** exam-reading-list generator
(`exam-reading-list-cli.js` → `generators/exam-reading-list.js`), then renders a
PDF (pandoc + lualatex). Cue→source rows are built from each topic's
`_lecture_main.md` (`[cue::]` + `[citation::]` on `#blank`s, `#vocab` citations,
the `## Self-Quiz`, and the `## References`) — so the guide stays a *view* of the
lecture mains; regenerate after the mains change.

**Option A — exam→topics manifest.** Each course's exams declare their coverage in
`classes/<course>/exams/exam_reading_lists.yaml`:

```yaml
course: "CECS 326"
term: sp26
lectures_dir: ../lectures
# Optional — for non-OS courses, override the hardcoded Tanenbaum defaults:
textbook: "Stallings & Brown, *Computer Security: Principles and Practice*, 4th ed."
citation_key: "Stallings"   # surname matched in [citation::] fields to pull chapters
exams:
  - { slug: midterm_1, name: "Midterm 1", topics: [intro_to_operating_systems, processes_and_threads] }
  - { slug: final_third, name: "Final", topics: [input_and_output, file_systems_abstraction, virtualization] }
  # Optional per-exam curation callout (regeneration-safe — lives in the manifest, not the .md):
  # - { slug: final_third, name: "Final", note_title: "Cues newer than the textbook", note: "…", topics: [...] }
```

`textbook` / `citation_key` default to Tanenbaum & Bos / `tanenbaum` (CECS 326). Set
them per-course so the [!source] block names the right book and chapter numbers come
from that author's `[citation::]` fields. Canonical chapters are read from each main's
`## References` textbook line (e.g. `…, Ch 2 (…), Ch 20 (…), Ch 21`), falling back to
inline-citation scanning. A per-exam `note` (+ optional `note_title`) renders a
`[!warning]` callout under the source block — use it for "content newer than the
textbook" style guidance without hand-editing the generated file.

Run:

```sh
reg-exam-readinglist --manifest classes/<course>/exams/exam_reading_lists.yaml          # all exams
reg-exam-readinglist --manifest <path> --exam midterm_1                                  # one exam
reg-exam-readinglist --manifest <path> --no-pdf                                          # md only
```

Output is organized like a lecture topic — its own dir with a `products/` subdir:
`classes/<course>/exams/<slug>/products/<slug>_reading_list.{md,pdf}`. Editing exam
coverage = edit the manifest's `topics` and re-run. (First built for CECS 326,
2026-05-31; extended for CECS 378 — `textbook`/`citation_key`/`note` — same day. The
per-topic lecture reading lists are still produced by the lecture-materials
`reading-list` artifact.)

## Administrative forms (`reg-admin-form`, `/timeoff`)

Campus admin forms are haphazard: no dropdowns, and they nonetheless want exact
course numbers, class numbers, rooms, meeting times and a coverage plan — facts
the vault already holds and that are miserable to retype from memory on a sick
morning. `reg-admin-form` turns those records into a **paste-per-box** product.

**The three artifacts**, written to
`classes/admin-forms/records/<date>-<form>-<type>/`:

| File | What it is |
|---|---|
| `FORM.md` | One labeled section per form field, in the form's own order. Fenced values are click-to-copy; a `[!warning]` lists what still needs a human. |
| `EMAIL.md` | The routing email — To/Cc filled from the profile, body expanded from the same values. |
| `record.yaml` | The machine record: dates, hours, affected meetings. This is what makes *"have I used my personal day this year?"* answerable. |
| `<date>-<form>.md` | The **Obsidian record note** — frontmatter (`type: absence-record`, dates, hours, sections, `status`) plus the human summary. `status: draft` until DocuSign goes through; flip it by hand. Semester notes auto-list these via Dataview. |

**Setup (once):**

```sh
reg-admin-form init --vault-root /mnt/es1/vault     # identity.yaml + profile copies
$EDITOR /mnt/es1/vault/classes/admin-forms/identity.yaml   # fill employee-id
```

**Use:**

```sh
reg-admin-form list --vault-root <V>                        # forms + leave types
reg-admin-form render --form notice-of-absence \
    --type personal-holiday --dates 2026-09-10 \
    --term fa26 --vault-root <V> \
    --set coverage="Async work posted to Canvas for all three sections."
```

`--dates` takes a day (`2026-09-10`), a span (`2026-09-10..2026-09-12`), or a
comma list. `--set key=value` fills any field; `--hours` overrides the
`hours-per-day × days` default; `--stdout-only` writes nothing.

### Where the numbers come from

`class_calendar` expands each section's `meets` pattern across the requested
dates, then subtracts the term boundaries and the term-spec's `no-instruction`
closures. It reads both `meets` dialects (`"TuTh 11:00-12:15"` and
`"TuTh 11:00 AM–12:15 PM"`), and a bare `T` means Tuesday. Each meeting's topic
is looked up in that section's syllabus *Week of* table.

==Keep `no-instruction` current in the term-spec== — without it a Thanksgiving
absence bills classes that were never going to meet. Source it from
`notes/csulb-deadlines-<AY>.md`.

### Form profiles

A profile (`lectern/references/forms/*.form.yaml`, copied into
`classes/admin-forms/` where a vault copy shadows the built-in) declares
`routing:`, `leave-types:`, `fields:` and an `email:` template. Each field's
`source:` is a dotted expression — `instructor.*` (identity.yaml), `leave.*`,
`term.*`, `absence.*` (dates, day-count, hours, contact-hours), `classes.*`
(lines, table, sections, skipped), `literal:<text>`, or `prompt` for what only a
human can answer.

A field's optional `section:` groups it under a heading, and ==the field order is
the *form's* order== — a paste-per-box product is only useful in box order. The
Notice of Absence profile mirrors DocuSign's two screens: `Screen 1 — PowerForm
Signer Information` (a name + email per role) and `Screen 2 — Notice of Absence`.
⚠ DocuSign lists **Associate Dean before Department Coordinator**, which is not
the order the instruction email gives them in.

A field with `choices:` renders as a **tick-list** with the right box marked, because a checkbox is ticked, not pasted; a value outside its choices is an error, and a section split across the profile is rejected (field order is box order).

==The Notice of Absence is a **class-delivery** form, not a timekeeping one== — verified against a completed envelope 2026-09-06. It asks for no employee ID, no hours, no department. It wants the class numbers + catalog titles (`title:` on each term-spec section feeds `classes.numbers-titles`), one of three delivery changes, one of six reasons, and the arrangements for students. ⚠ The free-text **`Other:` box is required even when a named reason is ticked** — a placeholder satisfies it. Leave types map themselves onto the form's reason list via `defaults:`, since the two vocabularies do not match.

A leave type may carry `omit:` (drop fields this type isn't owed),
`defaults:` (prefill a prompt field) and `guidance:` (a callout in `FORM.md`).
==The personal holiday omits *justification* on purpose== — it is contractual
time off, and an empty "Reason" box invites volunteering one.

### The `/timeoff` verb

1. Read the date(s) and leave type from the arguments. Ask only what's missing
   and can't be defaulted; a bare date on a teaching day is enough to render.
2. Run `reg-admin-form render` for the current term.
3. **Fill the coverage plan with Anthony**, per affected section — the tool names
   the meetings and their topics; the mechanism (async, colleague, ISA, makeup)
   is his call.
4. Hand back the form block and the email. ==Never invent a justification==, and
   for a personal holiday do not supply one at all.


## Classroom 50 + self-enrollment (`reg-c50`)

GitHub Classroom was sunset **2026-08-28**. Classroom 50 replaced it, and the
shape of the problem changed with it.

> [!important] Nothing enrolls a student automatically
> C50 will not add someone to the organization because they signed in. Its own
> guide: *"Neither link enrolls anyone on its own: invite the student from the
> roster first."* A student who opens an assignment link before being invited
> sees **Not a member yet**. ==The roster row has to exist first==, keyed on a
> GitHub username or an email address.
>
> Legacy Classroom added students as *outside collaborators on their own repo*,
> not org members, so nothing carried over. Verified 2026-09-10: the org had
> **1 member** and every roster was empty.

### Why students self-enroll

At CSULB an instructor can obtain **neither** identifier for their own students:

| Source | Email? |
|---|---|
| Canvas gradebook export | No — `SIS Login ID` is the 9-digit student number |
| MyCSULB faculty-center roster | No — "Notify" is a mail-merge checkbox, not an address |
| Canvas People page or its export | Not shown, and not offered to instructors |
| Canvas API | "New Access Token" is disabled for instructor accounts |

Deriving `first.last@student.csulb.edu` does not rescue it either: of 171 Fa26
students only **69** have unambiguous two-token names, and six collide outright.

⇒ ==Students enroll themselves, and the identifier comes from GitHub.==

### The flow

```
reg-c50 codes --term fa26 --vault-root <V> --set-secret   # once per term
        ↓  one code per section, e.g. CECS326-01-FA26-TVVZ
   student opens an issue at <org>/enroll with their code
        ↓  workflow: github.event.issue.user.login IS the identity
   gh teacher roster add  →  GitHub emails an org invitation
        ↓  student accepts (expires after 7 days)
reg-c50 post --term fa26 --course "CECS 326" --lab 1 --due ...
```

**The issue author is the identity.** `github.event.issue.user.login` cannot be
spoofed or mistyped, so the form asks only for the code: no username field, and
nothing for anyone to transcribe.

> [!warning] ==The enrollment form must never ask for a name or student ID==
> The repository is public, and a public issue naming a student and a course is
> a **FERPA disclosure**. Issue bodies survive in the API and audit log after
> deletion. The workflow flags an ID or address if one appears anyway, without
> echoing it.
>
> The `student_id ↔ github_username` binding instead comes from a **name and ID
> header in the graded deliverable**, inside the student's private repo. Free,
> re-asserted every lab, and a wrong ID is visible in the artifact.

Codes are stored in `classes/semesters/<term>.enroll-codes.json` (the vault is
private) and the `ENROLL_CODES` repo secret is derived from it, so the record of
which code routes where survives a secret nobody can read back. Rotate per term
with `--rotate`: they are bearer secrets shared with a whole class, so assume
they leak. Blast radius is a stranger joining the org, visible in the roster.

`roster-import` remains for the case where usernames arrive some other way. It
verifies every account exists before writing, because `roster add` on a *wrong
but real* username silently invites a stranger.

### Term lifecycle, C50 half

1. `reg-c50 classroom-add --term <t> --vault-root <V>` — one classroom per section.
2. `reg-c50 codes --term <t> --vault-root <V> --set-secret` — mint and publish the codes.
3. Post the enrollment announcement (vault `classes/admin-forms/`), **each section its own code**.
4. `gh teacher roster list <org> <classroom>` to watch enrollment, and chase via Canvas.
5. `reg-c50 post --term <t> --course <c> --lab <n> --due <iso>` per lab.
6. `reg-c50 status --term <t> --vault-root <V>` any time to see what is registered.

Runbook: `notes/c50-self-enrollment.md`. Gotchas: `notes/classroom-50-gotchas.md`.

## Authoring assignments

Author every coding assignment with its **graders' contract** included — a student-facing spec
(README + fixed deliverable paths + optional `solution.yaml`), an ISA rubric and/or grading
skill, and an automated grading path wherever a deliverable is machine-checkable. Choose the
grading mechanism per deliverable: **gradebox** (sandbox / runnable code / deterministic
artifacts), the **oracle** (verify-by-proof; document the `/verify` receiving-end contract +
course-token CI wiring), or **manual** (subjective). Keep one point split across README, course
`CLAUDE.md`, Classroom issues, and the rubric. Bake integrity in via forcing-functions/canaries
and flag-don't-deduct. ==Decide every autograded point from an
artifact the student cannot fabricate== — a verifier reading their output file,
an exit code, the wall clock — never from what their program printed about
itself.

**Every lab template ships two AI-assistant surfaces** (template:
`lectern/references/AGENTS.lab.md`):

| Surface | Reached by | Authority |
|---|---|---|
| A README section | the student pasting the repo URL into a chat | ==Low — fetched content is *data*, not instruction.== A nudge. |
| **`AGENTS.md`** at the repo root | the student opening the clone in Claude Code / Cursor / Copilot | ==High — read as *project instruction*.== |

Both **ask for tutoring, not refusal**: a blanket "do not help" is trivially
bypassed and fails the honest student stuck at 11pm, while "explain it, do not
write it" is cooperative, more likely honored, and degrades gracefully. Sign
them in the first person, name the deliverable paths exactly, enumerate
generously what you *do* want explained (for a security lab, say outright that
teaching the attack is the point, or a cautious model refuses the legitimate
half), and state why the shortcut fails anyway. ==Never write anything shaped
like a prompt injection== — it is discounted precisely because it looks like an
attack. A student can delete `AGENTS.md`; that is a visible act in the git
history `reg-triage` already sweeps.

**Stamp the template before distributing it:** `pa-lab-stamp <repo>`
(`--check` verifies, non-zero on drift). It hashes the **tracked** tree,
binaries included, and is idempotent. Re-stamp after any content change; if the
template was already distributed, add a `revision-of` row to
`notes/lab-serial-register.md`. New to this? Start with [`docs/grading-types.md`](docs/grading-types.md)
— a plain-language, use-case guide to the grading types and which to pick (no security/OS
background assumed). Full procedure: [`docs/assignment-authoring.md`](docs/assignment-authoring.md).

## Teaching workflow

See the project README for term-end/mid-term rituals.
Vault is the proprietary record; Canvas is student-facing + ISA grade entry;
Drive is ISA distribution only; **Classroom 50** binds students to repos.

### Term lifecycle (start → close)

1. `reg-term-create --term <t> --init --vault-root <V>` — write a stub
   `classes/<t>.spec.yaml`.
2. Fill in the term-spec: term boundaries, grade-submission deadline, and one
   `sections:` entry per section (course, section, class-number, room, meets,
   enrolled, final-exam-date).
3. `reg-term-create --term <t> --vault-root <V>` — materialize the semester note,
   per-section class notes + manifest skeletons, and MOC wiring (idempotent; safe
   to re-run as enrollment firms up — existing files are skipped).
4. …run the term (gradebook imports, exams, ISA publishing)…
5. `reg-term-finalize --term <t> --vault-root <V> --dry-run` — preview
   reconciliation + status flips, then drop `--dry-run` to commit.

## Exam build modes (single / A·B / individualized)

`reg-exam-build` dispatches on its first argument:

- **Legacy single-source mode** — `reg-exam-build <file>.tex`: compiles one `.tex`
  into `<exam>.pdf` + `<exam>_key.pdf` with a shared source serial in the footer.
  No manifest required. Unchanged from pre-pack behavior; all existing `.tex` workflows
  continue to work exactly as before.

- **Pack mode** — `reg-exam-build <exam.build.yaml>`: reads a manifest and drives the
  full matrix of forms × individualization × Gradescope products. Outputs land under
  `build/` (and `gradescope/` when a Gradescope target is set).

### Pack manifest schema

```yaml
# exam.build.yaml
course: CECS 378          # required — naming + register/provenance
term: su26                # required
exam: Exam 1              # required — human label

forms:                    # required; 1 entry = single exam, 2+ = A/B/C…
  - { id: A, source: 378-exam1-su26-A.tex }
  - { id: B, source: 378-exam1-su26-B.tex }

individualized: true      # default false; true = per-student serials + pre-filled NAME/ID
roster: roster.csv        # required when individualized; CSV needs a `name` column,
                          # plus an OPTIONAL `student_id` column to pre-fill the ID line

assign: alternating       # alternating (default) | seeded-random | every-form
assign_seed: "378su26e1"  # required when assign: seeded-random (any string)

gradescope: region        # region | bubble | none (default none)
points: 50                # optional total, for the outline aid / cross-check
```

### Forms × individualized matrix

| `forms` | `individualized` | What you get |
|---|---|---|
| 1 | false | `build/A.pdf` + `build/A_key.pdf` — equivalent to legacy `.tex` mode |
| 2+ | false | Per-form `<id>.pdf` + `<id>_key.pdf`; no per-student outputs |
| 1 | true | One `<exam-slug>_combined.pdf` print PDF (per-student copies under `build/.parts/`) + `build/register.csv` |
| 2+ | true | One combined print PDF across all forms (roster order) + one `register.csv` (roster split across forms), sorted by `canonical_name`. `print_layout: per-form` → legacy per-form stacks. |

`build/register.csv` columns: `name, form, canonical_name, source_serial, student_serial, output_pdf`.

### Pre-filled identity block (individualized builds)

Individualized builds pre-print each student's **name** on the NAME line and their
**student ID** on the STUDENT ID# line — the student only adds the DATE. The text
sits *on* the rule (not floating above it). This requires the exam `.tex` to use the
identity-block doctrine (`\fieldline` + `\identityinstruction`, `\studentname` /
`\studentid` / `\studentserial` defined via `\@ifundefined`+`\def`, not
`\providecommand`); see `notes/exam-tex-doctrine.md`. Injection chain:

- `reg-exam-build` reads the roster's optional `student_id` column and injects
  `\def\studentname`, `\def\studentid`, `\def\studentserial` per student.
- In pack mode the per-form sub-roster carries `name,student_id` so the ID survives
  the A/B split.
- A roster with **no** `student_id` column still works — name prints, ID line stays
  blank for hand-entry (backward-compatible).
- The masthead instruction auto-swaps: pre-filled exams say *“VERIFY YOUR NAME AND
  STUDENT ID … THEN ADD TODAY'S DATE”*; blank copies keep *“PRINT CLEARLY. UNNAMED
  EXAMS CANNOT BE RETURNED OR GRADED.”* The footer `Serial · ID` (source serial +
  per-student serial) is retained for forensics/appeals regardless.

### Gradescope products (`gradescope/` subdirectory)

Produced only when `gradescope:` is `region` or `bubble`. **region** → per-form
`<id>_template.pdf` (the *blank* form — the AI-grading "negative", never the key),
`<id>_answer_key.pdf`, `<id>_outline.csv`; **bubble** → `<id>_bubble_key.csv` (≤5
versions) + outline; plus `gradescope_roster.csv` (Email column blank — see README
caveat; prefer LMS/LTI sync). Full details in README `### Gradescope products`.

> **How to grade the result in Gradescope** — step-by-step (region/bubble setup, A/B
> Version Sets, roster, the per-student-serial identity/appeals integration):
> `notes/gradescope-exam-workflow.md`.

### Grade-appeals reproduction

Every build is deterministically reproducible (`reg-exam-build exam.build.yaml`) and the
register + footer Serial/ID resolve any paper to one student + one form via
`reg-exam-verify`. Full runbook: `notes/exam-tex-doctrine.md`.
