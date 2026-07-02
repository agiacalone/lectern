# Lab 3 — Buffer Overflow (demo) · Instructor Report
*CECS 378 · su26 · §01 — n=10 · mean 70.4 · median 78 · σ 34.0*

## Distribution
```
GRADE DISTRIBUTION  n=10  μ=70.4  σ=34.0
A ▏████████████████████████ 4
B ▏ 0
C ▏████████████████████████ 4
D ▏ 0
F ▏████████████ 2

SCORE HISTOGRAM
<70    ▏████████████ 2
70-79  ▏████████████████████████ 4
80-89  ▏ 0
90-100 ▏████████████████████████ 4

WARD-CLEAR FUNNEL
Phase Φ ACE (WALK IN)    ▏████████████████████████ 8
Phase Ω ACE (COLD STEEL) ▏███████████████ 5
```

## ➊ Grade table

| Student | github | Auto | Writeup | **Proposed** | flags |
| --- | --- | --: | --: | --: | --- |
| Bruce Wayne | bruce-wayne | 70 | 30 | **100** |  |
| Barbara Gordon | barbara-gordon | 70 | 29 | **99** |  |
| Dick Grayson | dick-grayson | 70 | 27 | **97** |  |
| Kate Kane | kate-kane | 70 | 26 | **96** |  |
| Harvey Dent | harvey-dent | 60 | 18 | **78** |  |
| Pamela Isley | pamela-isley | 60 | 17 | **77** |  |
| Oswald Cobblepot | oswald-cobblepot | 60 | 15 | **75** |  |
| Jason Todd | jason-todd | 70 | 0 | **70** |  |
| Edward Nashton | edward-nashton | 0 | 12 | **12** |  |
| Selina Kyle | selina-kyle | 0 | 0 | **0** |  |

## Grading recommendations

### Confirm (routine)
- **Bruce Wayne** (bruce-wayne) — proposed 100 — routine
- **Barbara Gordon** (barbara-gordon) — proposed 99 — routine
- **Dick Grayson** (dick-grayson) — proposed 97 — routine
- **Kate Kane** (kate-kane) — proposed 96 — routine
- **Harvey Dent** (harvey-dent) — proposed 78 — routine
- **Oswald Cobblepot** (oswald-cobblepot) — proposed 75 — routine
- **Jason Todd** (jason-todd) — proposed 70 — routine

### Edge cases needing a call
- **Pamela Isley** (pamela-isley) — triage REVIEW — review before posting
- **Edward Nashton** (edward-nashton) — honor-gate fail / non-submission — late-policy call
- **Selina Kyle** (selina-kyle) — honor-gate fail / non-submission — late-policy call

### Low-confidence / needs-human-read
- _none_

### Upward-adjustment candidates
- **Jason Todd** (jason-todd) — 70.0% — within 1.0 of C cut

## Per-student feedback & grades

> [!note] The block quote under each student is the **student-facing** text `reg-lab-report deliver` ships verbatim to their `FEEDBACK.md`; the `<!-- internal -->` line (forensic notes + flags) is **stripped at delivery**. A `> _Comments:_` placeholder marks an **ungraded** submission — the comment prose is filled by **LLM agentic grading** (`reg-lab-digest`, per `docs/lab-digest-grader-prompt.md`), never scripted; `deliver` skips any block still holding the placeholder.

### Bruce Wayne — **100 / 100**
*github: `bruce-wayne` · Auto 70/70 · Writeup 30/30*

> Outstanding after-action report. RECON derives the offset from your own leaked buffer/saved-EIP pair; Phase Phi ties every shellcode stage to a reason; Phase Omega is complete end-to-end — libc base from the printf leak, the setreuid privilege fix with a man-page cite, and a real pop/pop/ret gadget with disassembly. Nothing to add.

<!-- internal: All sections strong; mechanism-causal throughout; Omega full. -->

### Barbara Gordon — **99 / 100**
*github: `barbara-gordon` · Auto 70/70 · Writeup 29/30*

> Excellent, mechanism-first write-up. Both phases are explained at the byte level and your reflections are concrete. To reach full on Phase Omega, show the numeric libc offsets your commands returned rather than describing them. Great work.

<!-- internal: Strong throughout; Omega thin on one sub-part. -->

### Dick Grayson — **97 / 100**
*github: `dick-grayson` · Auto 70/70 · Writeup 27/30*

> Strong report. Phase Phi is exact and your Omega ret2libc chain is clearly reasoned. Two gaps: paste vuln2's own gdb output in RECON, and add the pop/pop/ret disassembly in Phase Omega. Well done.

<!-- internal: Solid; recon one binary; Omega missing a sub-part. -->

### Kate Kane — **96 / 100**
*github: `kate-kane` · Auto 70/70 · Writeup 26/30*

> Nice work — both phases land and your leak-then-pwn explanation is clear. For full marks, paste both binaries' gdb output and add the setreuid man-page citation in Phase Omega.

<!-- internal: Good; Phi solid, Omega missing a sub-part; recon one binary. -->

### Harvey Dent — **78 / 100**
*github: `harvey-dent` · Auto 60/70 · Writeup 18/30*

> Your Phase Phi walkthrough is solid — the sub-esp guard, the setreuid privilege fix, and the NOP-sled sizing are all here. Phase Omega was left as template placeholders; even without a working exploit you earn most of those points by writing up the NX fail-analysis, the libc offsets, and the pop/pop/ret gadget. Give the ret2libc walkthrough a try.

<!-- internal: Phi solid; Omega left as template placeholders (unattempted). -->

### Pamela Isley — **77 / 100**
*github: `pamela-isley` · Auto 60/70 · Writeup 17/30*

> Good Phase Phi engagement. Two things to tighten: RECON needs the explicit offset subtraction and both binaries' gdb output, and Phase Omega is unfilled — the ret2libc mechanism is worth writing up even without a passing exploit.

<!-- internal: Phi ok; Omega blank; recon thin (vuln1 only, implicit arithmetic). -->

### Oswald Cobblepot — **75 / 100**
*github: `oswald-cobblepot` · Auto 60/70 · Writeup 15/30*

> Your Phase Phi exploit passed, but the walkthrough is generic — tie it to specific lines of your own exploit1.c. Phase Omega is left as placeholders; completing the ret2libc write-up is the biggest available gain. Flesh out the reflections too.

<!-- internal: Phi generic; Omega blank; aftermath thin. -->

### Jason Todd — **__ / 100**
*github: `jason-todd` · Auto 70/70 · Writeup __/30*

> _Comments:_ 

### Edward Nashton — **12 / 100**
*github: `edward-nashton` · Auto 0/70 · Writeup 12/30*

> Right now neither exploit lands in the autograder, but your RECON and Phase Phi reasoning show real understanding. Get a working shell on vuln1 first, then fill the Phase Omega section. Please come to office hours — there's credit waiting once the exploits work and the sections are filled.

<!-- internal: FAILED BOTH PHASES (honor ok); Phi walkthrough has merit; Omega ~blank; no screenshots. -->

### Selina Kyle — **0 / 100**
*github: `selina-kyle` · Auto 0/70 · Writeup 0/30*

> _no submission_

## Canvas entry sheet

| Student (Last, First) | Proposed |
| --- | --: |
| Oswald Cobblepot | 75 |
| Harvey Dent | 78 |
| Barbara Gordon | 99 |
| Dick Grayson | 97 |
| Pamela Isley | 77 |
| Kate Kane | 96 |
| Selina Kyle | 0 |
| Edward Nashton | 12 |
| Jason Todd | 70 |
| Bruce Wayne | 100 |

## Provenance & caveats

Part A (autograde / honor / commits) = audit-grade facts. Part B (writeup scores + comments) = advisory, instructor-confirmed. Rendered deterministically by `reg-lab-report`.
