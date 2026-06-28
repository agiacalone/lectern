# Lab Grading Types — An Instructor's Guide to Choosing One

**Who this is for.** Instructors and ISAs deciding *how a lab will be graded* — before writing it.
You don't need a security or operating-systems background; specialized terms are explained the first
time they appear. This is the **which-do-I-pick** guide. For *how each type works under the hood*,
see the engine reference it links to (oracle `docs/grading-model.md`); for the **deep technical
internals** that an OS or computer-security specialist would want, follow the "dig deeper" links at
the end of each section — those docs are kept precisely so the specialist can go as far down as they
like.

> **Companion:** once you've picked a type here, `docs/assignment-authoring.md` (Step 0 onward) walks
> you through *authoring* the assignment so its graders have everything they need.

---

## Why a course needs more than one grader

A normal programming assignment grades itself: run the student's code, diff the output against a key.
Hands-on security and systems labs break that in two ways, and each break needs a different answer:

- Some labs **can't** be graded by running student code — the "answer" is a secret you must keep, and
  running their code on your machine would be unsafe or beside the point (think: *break this cipher*).
- Some labs **must** run student code that is *designed* to misbehave — a lab about crashing a
  program, or a deliberately buggy concurrent program, can take your grading machine down with it.

So instead of one grader there's a small menu. Pick by answering one question about your lab.

---

## The one question — then a decision tree

> **Does grading require *running* the student's code — and if so, is the grade just *how the
> program behaves*?**

```
Is the deliverable subjective (a writeup, design, analysis)?
│
├── YES ───────────────────────────────────► MANUAL (rubric / grading skill)
│
└── NO: can you grade it WITHOUT running their code?  (check a single submitted answer)
        │
        ├── YES ───────────────────────────► ORACLE  (verify-by-proof service)
        │
        └── NO: you must run it. What did the student submit?
                ├── a program, judged by behavior ──► GRADEBOX · code-running
                ├── a working exploit of a target ──► GRADEBOX · exploit-verification
                └── a modified binary file + patch ─► GRADEBOX · binary-artifact / ROM
```

Almost every real lab ends up **hybrid** — one machine-graded part plus one human-graded part. That's
expected; see the last section.

---

## Manual · rubric or grading skill

**Use it when** the deliverable is *inherently subjective*: a malware-analysis writeup, a design
rationale, a reflection, the *quality* of an explanation. A human grades it against a rubric (the
four-anchor Full / Solid / Weak / Absent language) and/or a Claude Code grading skill.

**Don't use it for** anything a machine can decide objectively — autograding the objective part frees
your ISAs to spend their judgment where it actually matters.

**The payoff with the other types:** every automated type below *emits evidence* (what changed, what
passed, integrity flags) straight into the human grader's hands, so the manual pass is faster and more
consistent.

**Maturity: in production.** (Pokémon-malware and buffer-overflow rubrics are in active use.)

**Author it:** `docs/assignment-authoring.md` Step 2.

---

## Oracle · verify-by-proof

**Plain version.** A small web service holds the lab's secret and **never runs student code.** The
student does the work on their own machine and submits only the *result* — a value only a real
solution could produce. The service checks it and returns a trustworthy pass/fail. (Picture a
combination lock you mailed out: you never watch them work, but the right combination back proves they
opened it.)

**Use it when** the lab reduces to *"prove you obtained this result"* **and** you must not run student
code on the grading host:
- cryptography — recover a key, forge a message authentication code, break an encryption mode
- web auth — mint a login token the server is fooled into accepting
- any "submit the one value only the real solution produces" challenge

**Don't use it when** the thing you're grading is a program's *behavior* — there's no single answer to
submit. That's gradebox.

**Why it's hard to cheat:** each student gets their own secret, derived from their identity, so answers
can't be shared and the secret never leaves the server. A "pass" means the work was genuinely done.

**Ships with:** ready-made `spellbreaker` (symmetric crypto) and `webauth` (token forgery) modules.

**Maturity: in production** — it has graded a live CECS 378 cryptography lab.

**Author it:** oracle `docs/ADDING_AN_ASSIGNMENT.md` (a small Python module). **Dig deeper (specialist):**
oracle `docs/grading-model.md` §"verify-by-proof", and the per-course derived-key / audit design in the
oracle README + `docs/COMPLIANCE.md`.

---

## gradebox · running student code safely

When you *must* run student code, gradebox runs **each submission inside its own sandbox** — a
disposable, locked-down container with no network, no access to the host or to other students' work,
and hard caps on CPU, memory, and process count. Hostile code runs safely; the grade is *what it did*,
not what it claimed. A preflight check refuses to grade at all if the machine can't isolate properly,
and results roll up into a gradebook spreadsheet. Authoring takes **no programming** — a container
recipe plus one short configuration file.

gradebox has three flavors. They differ only in *what the student submits*.

### code-running — "did they build a working program?"

**Use it when** the deliverable is *a working program* whose correctness you can see by running it:
operating-systems and systems labs — processes, threads, synchronization, producer/consumer,
"does it finish without deadlocking."

**Don't use it when** there's no objective behavioral check (use manual), or the student must *attack*
a target rather than build to spec (use exploit-verification).

**The hazard it tames:** a **fork bomb** — a program that endlessly spawns copies of itself until the
machine runs out of process slots and freezes. (A real one took down a grading host; that's why
gradebox exists.) The sandbox contains it and *labels* it instead of crashing.

**Maturity: built and stress-tested** against fork bombs, memory hogs, infinite loops, and escape
attempts. **Author it / dig deeper:** oracle `docs/gradebox-authoring.md` (worked synchronization-lab
example); internals in oracle `docs/gradebox.md`.

### exploit-verification — "did they *actually* break the target?"

**Use it when** the student must *demonstrate a capability* against a target program — buffer overflow,
privilege escalation, "make this program do what it shouldn't." The obvious grader — search the output
for a secret "flag" — is defeated by a student who simply *prints the flag*. This flavor plants a
**fresh random secret each round** and checks the exploit actually retrieves *that* secret, several
rounds in a row. Hardcoding the flag scores zero.

**Don't use it for** build-to-spec programs (that's code-running) or anything with no target to break.

**The cheat it closes:** a real submission once commented out its exploit and just printed a
precomputed flag — and a naive text-search grader passed it. Not anymore.

**Maturity: validated end-to-end** on a real CECS 378 buffer-overflow submission (real exploit full
marks; print-the-flag zero). **Author it / dig deeper:** oracle `docs/exploit-verification.md`.

### binary-artifact / ROM — "did they correctly modify this file?"

**Use it when** the deliverable is *a modified binary file plus a patch* — e.g. a retro game-cartridge
image (a "ROM") the student hand-edited, submitted with the small patch describing their changes. The
grade is **deterministic checks on the bytes**: does applying their patch to the official starting file
reproduce their binary; would the file actually boot on real hardware (not just a lenient emulator);
did the right data structures change; and — because each student starts from an *individualized* base
with a hidden, tamper-evident identity stamp — is this genuinely *their* copy. Borrow a classmate's
patch and it fails by construction.

**Don't use it for** behavior you'd need to run (that's the other two flavors); this is for truth that
lives in the file itself.

**Maturity (precise):** the **byte-level foundation is built and merged** (patch applier, boot-validity
checks, byte-diff, structure reader, identity stamp — tested and reviewed); the **full lab grader that
wraps it is still in design**, first target the CECS 378 Pokémon-malware lab. Real tested plumbing; the
finished end-to-end grader is forthcoming. **Dig deeper (specialist):** oracle `docs/grading-model.md`
§2c, and the design write-up `docs/superpowers/specs/2026-06-28-pokemon-malware-gradebox-program-design.md`
(kept in the private `-dev` lab repo for the operator-only details).

---

## Hybrid · what most labs actually are

Real labs mix an objective slice with a subjective one — so you mix types. Author the deliverables so
each slice goes to the smallest tool that covers it:

> **CECS 378 Pokémon-malware lab.** The patched ROM, its structure changes, and the hidden identity →
> gradebox binary-artifact (objective). The malware-analysis writeup and the creative work → manual
> rubric (subjective). The machine's evidence accelerates the human pass.

**The rule of thumb:** autograde what is *decidable*; emit *evidence* for everything that isn't. Don't
try to autograde an inherently visual or subjective deliverable — that's false confidence.

---

## Cheat-resistance you can add to *any* type

These are authoring techniques, not separate graders — sprinkle them in. None needs a security
background:

- **A required fingerprint (the "brown M&M").** A small, course-specific element a correct solution
  *must* touch; copied work never touches it, so it stands out. (Named for the band that hid a
  "no brown M&Ms" clause to spot venues that hadn't read the contract.)
- **Per-student individualization.** Give each student a slightly different starting point/input
  stamped from their identity; the grader regenerates it and trusts nothing in the files — so one
  student's work can't pass as another's. (Same idea as per-student exam serials.)
- **Make the public solution not fit.** Hand out a custom starting point so online walkthroughs don't
  transfer.
- **Fresh-secret checking** (the exploit-verification trick) — defeats "hardcode the expected output."
- **Authenticity triage** (`reg-triage`) — scans submission *history* for tell-tale patterns. Golden
  rule: **flag for a human, never auto-penalize.** No student is sanctioned by a script alone.

---

## Pick-the-type cheat sheet

| Your lab's deliverable | Grading type | Author it with | Maturity |
|---|---|---|---|
| A writeup, design, or analysis | **Manual rubric** | `assignment-authoring.md` §2 | production |
| "Prove you recovered this secret / forged this token" | **Oracle verify-by-proof** | oracle `ADDING_AN_ASSIGNMENT.md` | production |
| A program judged by how it behaves | **gradebox code-running** | oracle `gradebox-authoring.md` | built & stress-tested |
| A working exploit of a target | **gradebox exploit-verification** | oracle `exploit-verification.md` | validated e2e |
| A patched / modified binary file | **gradebox binary-artifact/ROM** | program spec (in design) | foundation merged; grader forthcoming |
| Some of each (most labs) | **Hybrid** | `assignment-authoring.md` | — |

---

## See also

- `docs/assignment-authoring.md` — the full authoring procedure (Step 0 picks the mechanism per deliverable)
- oracle `docs/grading-model.md` — the engine reference: what each type *is* (the layer this guide chooses among)
- **Dig-deeper, specialist docs** (kept for OS / computer-security depth): oracle `docs/gradebox.md`
  (sandbox security model), `docs/gradebox-authoring.md`, `docs/exploit-verification.md`,
  `docs/ADDING_AN_ASSIGNMENT.md`, `docs/COMPLIANCE.md`
- `docs/recon-report-workflow.md` (cohort recon) · `docs/gradescope-workflow.md`
