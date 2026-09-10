# Authoring a Coding Assignment

How to author a CECS coding assignment so it is **gradeable the same disciplined way every
time**: a clear student-facing spec, an ISA rubric (and/or grading skill), and an automated
grading path wherever a deliverable is machine-checkable — with the student-facing point split
and the grader-facing rubric kept in agreement.

This guide is **generic** (any coding assignment). The CECS 378 Pokémon-malware lab is used as a
worked example at the end.

> **Doctrine:** every assignment ships with its **graders' contract** — the rubric/skill *and*
> the run instructions for whatever automated grader applies. Don't bolt grading on after the
> students have already submitted.

---

## The two halves of every assignment

| Half | Artifacts | Owner |
|---|---|---|
| **Student-facing** | README (deliverables, fixed paths/names), starter repo, optional machine-readable solution manifest, **student self-check CI** (non-binding) | the student sees these |
| **Grader-facing** | ISA rubric and/or grading skill, the automated grader (gradebox spec / oracle provisioning), the run-doc, the integrity checklist | ISAs + the operator |

The two halves must agree on **one point split**. A README that says 33/8/17/42 while the rubric
says 20/20/15/20/25 is a defect — reconcile at authoring time, across README, the course
`CLAUDE.md`, the GitHub Classroom deliverable issues, and the rubric.

---

## Step 0 — Choose the grading mechanism

> **New to the grading types, or want the use-cases first?** Read [`docs/grading-types.md`](grading-types.md)
> — a plain-language decision guide (no security/OS background assumed) that walks the same choice
> below with worked examples and "use when / don't use when" for each type. The table here is the
> quick version.

| Mechanism | Use when | What it does |
|---|---|---|
| **gradebox** | The deliverable is **runnable code, an exploit, or a deterministic artifact** (a patch, a binary, a parseable file) | Runs untrusted student work in a hardened, ephemeral container → binary tests → score → `gradebook.csv`. See `oracle` repo `docs/gradebox-authoring.md`. |
| **oracle** | The lab reduces to **"prove you obtained a result"** and you must **not** run student code server-side (e.g. crypto: ciphertext + a candidate proof) | Verify-by-proof network service. The student runs the work their side; `/verify` is the sole arbiter; secrets never leave the host. See "oracle — receiving end" below. |
| **manual** | The deliverable is **inherently subjective** (a writeup, a design, a reflection) | ISA rubric / grading skill only. |
| **hybrid** | Most real labs | Deterministic slice → gradebox/oracle; subjective slice → manual rubric. The automated grader also emits **evidence** that accelerates the manual pass. |

> [!warning] ==A grader that reads the student's stdout is not a grader==
> CECS 326 Lab 1, 2026-09-10: a submission whose `main()` printed the three
> expected report lines and did nothing else scored **45/45** against the first
> draft of its spec. Decide each point from an artifact the student cannot
> fabricate: a verifier reading their output *file*, an exit code, the wall
> clock. Where a fact genuinely only exists inside their process, say so in the
> spec and pair it with something that does not. Worked example:
> `~/git/326/cecs-326-lab-threads-dev/gradebox/`.

Pick the smallest mechanism that covers each deliverable. Don't try to autograde an inherently
visual or subjective deliverable — that is false confidence. Autograde what is *decidable*; emit
*evidence* for the rest.

---

## Step 1 — Author the student-facing assignment

- **Fixed deliverable paths/names.** State them exactly (e.g. `WRITEUP.md` at repo root,
  `patch.ips`, `solution.yaml`). Graders match case-sensitively; naming variance becomes a false
  "missing deliverable." (See `feedback_lab_deliverable_naming_contract`.)
- **A machine-readable solution manifest where it helps.** Having the student *declare* their
  answer (the species, the config, the chosen target) in a small `solution.yaml` turns an
  ambiguous "did they do it" into a deterministic "does it match the declared answer."
- **Deliverables map 1:1 to rubric sections**, so the grade breakdown is legible.

---

## Step 1b — AI assistants: ask them to tutor, not to refuse

A student who wants the answer will paste the URL, or open the repo in an
agentic editor and say "implement this." Both are worth addressing, and they are
**different surfaces with different authority**.

| Surface | What the student did | How much weight it carries |
|---|---|---|
| A README section | pasted the repo URL into a chat | ==**Low.** Fetched page content is treated as *data*, not instruction== — that is the correct defense against prompt injection, and it applies to your README too. A nudge. |
| **`AGENTS.md`** at the repo root | cloned the repo, opened it in Claude Code / Cursor / Copilot | ==**High.** Read as *project instruction*==, in a file that conventionally carries exactly this guidance. |

Ship both. Template: [`lectern/references/AGENTS.lab.md`](../lectern/references/AGENTS.lab.md).

### Four rules for the wording

1. **Ask for tutoring, not refusal.** A blanket "do not help" is trivially
   bypassed *and* fails the honest student stuck at 11pm. "Explain it, do not
   write it" is a cooperative request, far more likely to be honored, and it
   degrades gracefully instead of failing shut.
2. **Sign it.** A named instructor stating course policy in the first person
   carries weight that anonymous boilerplate does not.
3. ==**Never write anything shaped like a prompt injection.**== No
   "IGNORE PREVIOUS INSTRUCTIONS", no hidden text, no white-on-white. It gets
   discounted precisely because it pattern-matches to an attack, and it makes
   the instructor look like they are playing games rather than stating a policy.
4. **Name the deliverable paths exactly**, and **enumerate generously what you
   do want explained.** A vague file is easy to reason around; a concrete one is
   not. For a security course, say plainly that teaching the attack is the point
   — otherwise a cautious model refuses the *legitimate* half of the request.

### It is a nudge, and the structural defences are the real work

Say why the shortcut does not work, in the file, because that is the part that
is actually load-bearing:

- **Per-student seeding** (`gradebox` `image_build.seed_template`) — the correct
  output differs per student, so a pasted answer fails verification.
- **The oracle** — proofs bound to student, challenge and session.
- **A writeup graded on mechanism** — "trace the interleaving that loses an
  update," in their own words.
- **`reg-triage`** — commit-history authenticity, flag-don't-deduct.

### The guard-file check

A student can delete `AGENTS.md`. That is fine, and it is the reason the file is
worth shipping: it is a visible, deliberate act in the git history.

`reg-triage` and `reg-lab-recon` both report it. A **guard file** is an
instructor-authored file the student was not asked to edit; the default is
`AGENTS.md`. Each one is compared against its baseline at the grading commit and
comes back `intact`, `modified`, `deleted` or `absent`:

- `reg-triage sweep`: a `guard` column in `results.csv`, a Guard column in
  `TRIAGE.md`, and a **Guard files** roll-up naming each repo and commit.
- `reg-triage report`: section **A.6 Guard-file integrity**, with the commits
  that touched the file and a reproduce command for each fact.
- `reg-lab-recon`: a `guard` column in `cohort.csv` and a **Guard files**
  section in `FACTS.md`.

Declare them in the manifest (both tools read the same key):

```yaml
guard_files:
  - AGENTS.md
  - path: .github/workflows/autograde.yml
    sha256: 9f2b…            # the file as distributed
```

==Add the `sha256` when you have it.== Without it the baseline is the file's
first appearance *in that repo*, which a squashed initial commit hides: a student
who edited `AGENTS.md` before their first push reads as `intact`. With it, the
comparison is against the template as you shipped it. `pa-lab-stamp` already
hashes the tracked tree, so the per-file digest is a `sha256sum` away.

> [!important] It is a fact, never a score
> A guard-file change carries no points and moves no triage bucket. That is by
> design, and the test suite asserts it. The scoring engine does not read `guard_files`
> at all. There are innocuous reasons to touch these files, so the tool names the
> commit and stops. Read it, then decide.

## Step 1c — Stamp the serial

Before a template is distributed, stamp it:

```sh
pa-lab-stamp <repo>            # stamp or re-stamp; prints old -> new
pa-lab-stamp --check <repo>    # verify; non-zero on drift
```

It hashes the repo's **tracked** tree, `lib/*.o` and every other binary
included, strips the existing footer before hashing (so it is idempotent), and
injects `<!-- serial: XXXXXXXX -->` into `README.md`. ==A serial that excludes
the binaries the lab depends on is worse than none== — a rebuilt library would
not move it.

Re-stamp after any content change, and if the template was **already
distributed**, add a row to `notes/lab-serial-register.md` with `revision-of`.
See `notes/lab-doctrine.md`.

## Step 2 — Author the rubric / grading skill

A detailed ISA rubric (see the existing `*_lab_grading_rubric.md` notes for the house style):

- Per-section point grids; **four-anchor language** (Full / Solid / Weak / Absent).
- An explicit **grading workflow order** (what to check first; the authenticity check is
  non-negotiable and comes first).
- A **mandatory academic-integrity checklist** ("flag, don't deduct" — escalate to the
  instructor).
- Point split **identical** to the student-facing breakdown.

Optionally encode the same rubric as a Claude Code grading skill so an agent can ISA-grade
consistently. The rubric and the skill are two renderings of one contract — keep them in sync.

---

## Step 3a — gradebox path (sandbox / runnable / deterministic)

Authoring a gradebox lab is **zero-Python**: a Docker image + one YAML spec. Any helper logic is
baked **into the image** as lab content, not added to the gradebox engine.

1. **Image** (`images/<lab>/`): a minimal base + the tools the checks need + any baked assets.
   - **Bake licensed/copyright assets into a PRIVATE image** and **do not publish it** (e.g. a
     base ROM, a dataset). Keep keys/secrets out of images entirely.
2. **Spec** (`<lab>.yaml`): `build.cmd` + `tests[]` (each a **binary** pass/fail check with
   `exit_code`/`stdout_regex`/`stdout_contains` predicates) + `limits` + optional `sandbox`
   profile. Use the **`dynamic_flag`** test type for exploit labs — a fresh random secret per
   round defeats a hardcoded-output cheat.
3. **Evidence tests (0-pt)**: print analysis (diffs, region maps, cross-checks) to the
   transcript so the manual pass is faster. Hard facts (a diff, a git history) are evidence;
   heuristic cross-checks are **advisory** — never auto-penalize on a heuristic
   (`feedback_triage_facts_vs_advisory`).
4. **Run-doc** (ships with the lab):
   ```sh
   python -m gradebox doctor                       # verify isolation controls
   python -m gradebox run --spec <lab>.yaml \
       --submissions ./repos --out ./out --jobs 4  # → out/gradebook.csv
   reg-gradebook import …                           # lectern boundary
   ```

Authoritative reference: `oracle` repo `docs/gradebox-authoring.md` + `docs/gradebox.md`.

---

## Step 3b — oracle path (verify-by-proof) — receiving end

Use the oracle when the lab is a **proof of a result** and you must not execute student code on
the server. The oracle never runs student code: students run the exploit/computation their side
and submit ciphertext + a candidate proof; `/verify` returns `{pass: bool}`; per-student keys are
derived `HMAC(root_key, course|repo|assignment|challenge|label)` so the key never leaves the host.

What the **authoring** side does (operator, off-HTTP admin CLI):

- Provision the course, enable the assignment, issue a **per-course service token**
  (`python -m oracle_server.admin add-course / enable-assignment / issue-token`).

What ships in the **assignment** (the receiving end — this is what to document for students/CI):

- The **`/verify` contract**: the exact route (`/{course}/{assignment}/verify`), what the
  student POSTs (e.g. ciphertext + candidate proof), and the `{pass}` response.
- **Course token wiring**: the service token as a GitHub Classroom **org secret** + a
  `$<LAB>_COURSE` variable; the student CI calls the course-scoped route. The token is *not* in
  the repo or image.
- **Fail-closed** behavior: no proof / wrong proof → no pass; the oracle is the sole arbiter.

Authoritative reference: `oracle` repo `docs/DEPLOYMENT.md` / `docs/COMPLIANCE.md`;
`project_grading_oracle_licensing`.

---

## Step 4 — Academic-integrity authoring patterns

Bake integrity into the assignment's **construction**, not just the grading.

- **Forcing functions / canaries** (`feedback_brown_mm_assignment_canaries`): a **class-specific
  element students must touch**. Borrowed work (a peer's patch, a public solution) never touches
  your unique element → it fails by construction and is detectable. Rotate a **per-term token** so
  last term's work also fails.
- **Hash / input forcing**: distribute a **custom base artifact** (a different hash than any
  stock/public version) so a solution built against the public version won't apply/validate —
  students are forced to engage *your* specific input. Going further, **significantly diverge**
  the base from any well-documented original (the "Super Star Trek" technique) so public
  documentation/solutions don't transfer and students must reverse *your* version.
- **Per-student individualized artifacts** (the exam per-student-serial pattern applied to labs):
  stamp each student's starter artifact with a token derived from their identity
  (`HMAC(class_key, student_id)`) so every student works against a provably **unique** input. The
  grader **regenerates** the artifact from the bound id and trusts nothing committed in the repo —
  borrowed work fails structurally (wrong base → no round-trip; embedded identity mismatch).
- **`dynamic_flag`** (gradebox): per-round random secret defeats hardcoded-output exploits.
- **Flag, don't deduct.** Hard facts (a diff that contradicts the writeup, a git history) are
  audit-grade evidence; heuristic scores are advisory; **no student is penalized without human
  review**. `reg-triage` provides git-history authenticity triage with this two-tier structure.

---

## Step 5 — Academic use & IP posture

- **Third-party / copyrighted assets** (ROMs, datasets, sample malware): keep them in **private,
  non-distributed** grading images for **educational binary-analysis use**. Be honest about
  derivative status — a build of a third-party disassembly is a *flavored build of that project*,
  not original IP; don't claim ownership. Match the posture the asset already has in the course.
- **Never bake secrets/keys** into images or repos. Oracle keys are derived server-side; gradebox
  injects per-round secrets at grade time.
- **Tooling licensing.** The oracle (and gradebox, which lives in the oracle repo) is
  **source-available** — PolyForm Strict + an Educational Institution Grant: free for academia,
  distribution-restricted. Public lectern tooling is MIT. (`project_grading_oracle_licensing`.)

---

## Step 6 — Reconcile & propagate

- **One point split** across README, course `CLAUDE.md`, Classroom deliverable issues, and the
  rubric.
- **Propagate through the template chain** (static copies, not live regen): dev template →
  student-facing template → per-class static copy → student forks (student work is never touched).
- **Student self-check CI**: a `.github/workflows` job running the **public** subset of the
  authoritative grader's checks, **non-binding** — students see green/red before submitting; the
  operator-run grader remains authoritative (mirrors the gradebox-vs-`autograde.yml` authority
  model).

---

## Worked example — CECS 378 Pokémon Malware lab (hybrid)

A binary-analysis lab (modify a Pokémon Yellow ROM) being redesigned to this standard:

- **Custom base artifact + canary:** a flavored ROM built from a pret/pokeyellow fork with a
  CECS-378 element students must change — different hash than the commercial dump (forcing
  function) and a per-section plagiarism canary in one.
- **gradebox (hybrid):** the `rom-lab` private image bakes the base ROM + a `.sym`-derived offset
  map + a pure-Python `romlab` helper; the spec scores the deterministic slice (IPS round-trip,
  canary-changed, each data structure changed / matching the declared species in `solution.yaml`)
  and emits evidence (writeup-offset cross-check, region map) for the manual slice (sprite
  aesthetics, malware reflection).
- **Reconciled split + run-doc + self-check CI** ship with the lab.

Full program design: `oracle` repo
`docs/superpowers/specs/2026-06-28-pokemon-malware-gradebox-program-design.md`.

---

## See also

- [`docs/grading-types.md`](grading-types.md) — plain-language guide to the grading types and which to pick (read first if you're new)
- `oracle` repo: `docs/grading-model.md` (the engine reference behind the grading types),
  `docs/gradebox-authoring.md`, `docs/gradebox.md`, `docs/exploit-verification.md`,
  `docs/DEPLOYMENT.md`
- lectern: `docs/recon-report-workflow.md` (cohort recon), `docs/gradescope-workflow.md`
- Memories: `feedback_assignment_authoring_grading_contract`, `project_gradebox_sandbox_runner`,
  `feedback_brown_mm_assignment_canaries`, `feedback_lab_deliverable_naming_contract`,
  `feedback_triage_facts_vs_advisory`, `project_grading_oracle_licensing`
