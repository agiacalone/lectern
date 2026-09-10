# Design — CECS 326 Lab 1: The Torn Map (pthreads onboarding lab)

- **Date:** 2026-09-10
- **Status:** Approved (design); implementation not started
- **Replaces:** `agiacalone/cecs-326-reading-processes_and_threads` (created 2022-02-18, last content change 2025-02-13)
- **New template:** `agiacalone/cecs-326-lab-threads`
- **Canvas column:** `Lab 1 - Threads` — **unchanged**, so `classes/326/gradebook-schema.yaml` needs no edit
- **Points:** 60 (45 autograded / 15 ISA-graded)
- **Doctrine:** [`docs/assignment-authoring.md`](../../assignment-authoring.md) · [`docs/grading-types.md`](../../grading-types.md) · [[notes/lab-doctrine]]

## Problem

The outgoing Lab 1 is ten prose questions answered in a writeup. Its content is
fine — it maps cleanly onto all six sections of
`classes/326/lectures/processes_and_threads/processes_and_threads_lecture_main.md`,
scheduling included. It contradicts the Fa26 syllabus in three places:

| Lab 1 (2022) | Fa26 syllabus |
|---|---|
| "questions from the Chapter 2 reading from **your text book**"; cites *Fig. 2-24 / 2-28 of MOS4e* | "**There is no textbook for this course, and nothing to buy.**" |
| A reading worksheet turned in for a grade | "there are no longer **reading questions to complete and turn in**. The discussion *is* the assignment now." |
| A writeup | Class Rules: "**Lab assignments will be coding projects** designed to practice the concepts discussed in lecture." |

A student with the syllabus open can correctly object to the assignment. That is
the trigger; the age is only why nobody noticed.

**Second problem, from Anthony 2026-09-10:** for many students this is their
**first C program**. The Fa26 syllabus's "GitHub & Software" section promises no
development environment at all — no VM, no gcc, no Linux — while Lab 2's README
assumes "your Linux virtual machine that we created during the first few weeks of
class." Nothing in Fa26 creates that VM. ==Lab 1 has to supply the toolchain, not
just the concurrency.==

## Shape

A **prologue to Lab 2**. Lab 2 is the RPG dungeon; Lab 1 is the errand before it.
The dungeon's map was copied once, torn, and scattered across seven scriptoria.
Each keeps a few leaves and answers slowly. Send one runner to each and
reassemble the map exactly — one wrong byte and the party walks into a wall.

The theme is not decoration. It supplies the lab's two hard requirements for
free: *why the bytes must match exactly*, and *why the sources are slow*.

### Why threads, when Lab 2 is processes

Lab 2 is entirely **process**-based: `fork`/`exec`, POSIX shared memory, signals,
named semaphores. A **thread**-based Lab 1 is a progression rather than a
rehearsal, and the shared address space is exactly what makes the race in Phase 3
possible without any IPC machinery.

## Phases

A student new to C banks real points before threads appear. Phase 1 is worth more
than Phase 2 deliberately: correctness in C first, concurrency second.

| Phase | Student does | Pts | Teaches |
|---|---|--:|---|
| **0 · The Gate** | Get a Linux toolchain; compile the provided `warmup.c`; make `make` work | 5 | gcc, `-Wall`, make, man pages |
| **1 · One runner** | Single-threaded fetch: loop `mirror_read`, assemble, checksum | 15 | pointers, buffers, `size_t`/`off_t`, error checking — **no threads** |
| **2 · Seven runners** | `pthread_create` / `pthread_join`, genuine overlap | 15 | threads |
| **3 · The race** | The shared counter: observe it break, fix it | 10 | mutual exclusion |
| **4 · The report** | `WRITEUP.md` | 15 | ISA rubric |

Split: **45 code / 15 writeup**. One split, carried identically by the README and
the rubric, per authoring doctrine.

## Provided starter

| File | Purpose |
|---|---|
| `mirror.h` | The scriptorium API |
| `mirror_X86_64.o`, `mirror_ARM64_linux.o`, `mirror_ARM64.o` | Prebuilt library, tri-arch — the same provided-object pattern students meet again as Lab 2's `dungeon.o` |
| `warmup.c` | Phase 0's compile target |
| `example_serial.c` | One worked `mirror_read` call, so a first-time C student starts from a shape, not a blank file |
| `Makefile` skeleton, `selfcheck.sh` | Non-binding student self-check (authoring doctrine, Step 1) |
| `.devcontainer/` | "Open in Codespaces" → compiling C in a minute, with no local Linux |

```c
#define MIRROR_COUNT 7

int     mirror_open(void);                                            /* total map size */
ssize_t mirror_read(int scriptorium, off_t start, size_t len, char *buf);
int     mirror_max_concurrency(void);   /* peak simultaneous readers; the grader reads this */
```

`mirror_read` sleeps a few milliseconds with jitter. **The latency is the lesson:**
serial is slow, seven runners are fast, and the speedup is bounded by the slowest
scriptorium. Without it there is no reason to thread anything.

### The devcontainer earns its place twice

TODO #282 wants Lab 2 moved to Codespaces to kill "the arch/compile-env grading
mess." Fixing the environment at Lab 1 fixes it at the point of entry, which is
where it should have been fixed. The Spellbreaker template already ships a
`.devcontainer`, so this is a proven pattern in this fleet rather than a new bet.

## The planted race

Threads write **disjoint** byte ranges into the assembled buffer — safe with no
lock. They also all increment a shared `leaves_recovered` counter — not safe.

That separation is the entire pedagogical point, and it is the one OSTEP
`threads-intro.pdf` teaches: sharing is not the hazard, *unsynchronized mutation*
is. A student who locks the buffer writes "to be safe" has misread the problem,
and the writeup rubric asks them to explain the difference.

Jitter is tuned so an unlocked counter loses updates on nearly every run. A race
that fails one run in fifty teaches the wrong lesson — that concurrency bugs are
bad luck.

## Grading

**Autograded (gradebox, 45) —** runnable code with deterministic checks, per the
Step 0 mechanism table.

| Check | Pts |
|---|--:|
| Builds clean under `-Wall -Werror -pthread` | gate |
| Assembled map byte-identical to the round's expected digest | 20 |
| `mirror_max_concurrency() >= 7` | 15 |
| Counter exact across 50 repeated runs | 10 |
| *Evidence (0 pt): serial-vs-threaded timing, peak concurrency, whether `pthread_mutex` symbols linked* | — |

Phase 0's 5 points are the build gate; Phase 1's 15 are the byte-identical check
reached single-threaded. A student who stops after Phase 1 earns 20 of 45, which
is the intended floor for someone still learning C.

**ISA-graded (15) —** `WRITEUP.md`, four-anchor language matching the Spellbreaker
rubric's house style:

- The interleaving that loses an update — mechanism, not "I added a lock" (8)
- Why disjoint buffer writes are safe but the counter is not (4)
- Serial-vs-threaded timing, and what bounds the speedup (3)

## Anti-hardcode

The mirror library is **seeded per grading round** (`dynamic_flag` device,
gradebox authoring guide). The correct output differs each round, so a committed
answer file cannot pass. Authenticity of commit history is already covered by
`reg-lab-recon` / `reg-triage`; integrity findings **flag, never auto-deduct**.

## Readings — all free

The Fa26 syllabus sells no textbook, so every citation must be free to read.
OSTEP (Arpaci-Dusseau, *Operating Systems: Three Easy Pieces*, "free in PDF form"):

- `threads-intro.pdf` — Concurrency: An Introduction
- `threads-api.pdf` — Thread API
- `threads-locks.pdf` — Locks

Plus `pthread_create(3)`, `pthread_join(3)`, `pthread_mutex_lock(3)`. Lab 2's
semaphores live in `threads-sema.pdf`, so the two labs do not overlap.

This is the first artifact to cite OSTEP and is a live test of the migration in
TODO #455/#456 before the lecture mains are converted.

## Deliverables (fixed paths — graders match case-sensitively)

`fetch.c` · `Makefile` producing `./fetch` · `WRITEUP.md` at repo root

## Artifacts to produce

| Artifact | Where |
|---|---|
| Template repo | `agiacalone/cecs-326-lab-threads` (flag as template) |
| Mirror library source + tri-arch build | in the template, source kept private-side |
| gradebox image + spec | `oracle` repo, `images/` + `<lab>.yaml` |
| ISA rubric | `classes/326/labs/threads/threads_lab_grading_rubric.md` |
| Lab index + README mirror | `classes/326/labs/threads/{index.md,README.md}` |
| Serial stamp | `<!-- serial: XXXXXXXX -->`, per [[notes/lab-doctrine]] |
| Old template | **archived, not deleted** — it is the record of an assignment delivered 2022–2025 |

## Open

- **Post date.** This is several days of work, not an afternoon. 326 Lab 1 cannot
  ship on 2026-09-10. Either slip it, or post something smaller this week and let
  The Torn Map land as Lab 2 with the semaphore dungeon becoming Lab 3.
  ==Undecided.==
- **Identity binding.** Nothing maps `student_id ↔ github_username` under C50.
  A required name + student-ID header in `WRITEUP.md` would solve it for every
  graded lab at zero cost. See [[notes/syllabus-github-section-c50-rewrite]];
  decide there, apply here.
