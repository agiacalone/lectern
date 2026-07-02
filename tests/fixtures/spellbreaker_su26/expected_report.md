# Lab 1 — Symmetric Cryptography (Spellbreaker) · Instructor Report
*CECS 378 · su26 · §01 — n=25 · mean 82.6 · median 90 · σ 25.6*

## Distribution
```
GRADE DISTRIBUTION  n=25  μ=82.6  σ=25.6
A ▏████████████████████████ 13
B ▏███████████ 6
C ▏██████ 3
D ▏ 0
F ▏██████ 3

SCORE HISTOGRAM
<70    ▏██████ 3
70-79  ▏██████ 3
80-89  ▏███████████ 6
90-100 ▏████████████████████████ 13

WARD-CLEAR FUNNEL
Ward I — ECB detection      ▏████████████████████████ 23
Ward II — byte-at-a-time    ▏████████████████████████ 23
Ward III — CBC bit-flipping ▏██████████████████████ 21
OMEGA — padding oracle      ▏██████████████ 13
```

## ➊ Grade table

| Student | github | Auto | Writeup | **Proposed** | flags |
| --- | --- | --: | --: | --: | --- |
| Selina Kyle | gh-user-06 | 70 | 30 | **100** |  |
| Edward Nashton | gh-user-09 | 70 | 30 | **100** |  |
| Harvey Bullock | gh-user-25 | 70 | 30 | **100** |  |
| Harvey Dent | gh-user-24 | 70 | 30 | **100** |  |
| Roman Sionis | gh-user-11 | 70 | 30 | **100** |  |
| Luke Fox | gh-user-23 | 70 | 30 | **100** |  |
| James Gordon | gh-user-07 | 70 | 30 | **100** |  |
| Victoria Zsasz | gh-user-05 | 70 | 30 | **100** |  |
| Jason Todd | gh-user-22 | 70 | 28 | **98** |  |
| Kate Kane | gh-user-15 | 70 | 24 | **94** |  |
| Dick Grayson | gh-user-19 | 70 | 24 | **94** |  |
| Floyd Lawton | gh-user-12 | 60 | 30 | **90** |  |
| Basil Karlo | gh-user-10 | 60 | 30 | **90** |  |
| Barbara Gordon | gh-user-03 | 60 | 28 | **88** |  |
| Pamela Isley | gh-user-01 | 60 | 27 | **87** |  |
| Harleen Quinzel | gh-user-08 | 60 | 27 | **87** |  |
| Cassandra Cain | gh-user-02 | 70 | 17 | **87** |  |
| Renee Montoya | gh-user-13 | 60 | 24 | **84** |  |
| Bruce Wayne | gh-user-20 | 60 | 22 | **82** |  |
| Slade Wilson | gh-user-14 | 60 | 19 | **79** |  |
| Waylon Jones | gh-user-16 | 60 | 18 | **78** |  |
| Oswald Cobblepot | gh-user-17 | 55 | 15 | **70** |  |
| Alfreda Pennyworth | gh-user-18 | 35 | 8 | **43** |  |
| Jervis Tetch | gh-user-21 | 10 | 4 | **14** |  |
| Stephanie Brown | gh-user-04 | 0 | 0 | **0** |  |

## Grading recommendations

### Confirm (routine)
- **Selina Kyle** (gh-user-06) — proposed 100 — routine
- **Edward Nashton** (gh-user-09) — proposed 100 — routine
- **Harvey Bullock** (gh-user-25) — proposed 100 — routine
- **Harvey Dent** (gh-user-24) — proposed 100 — routine
- **Roman Sionis** (gh-user-11) — proposed 100 — routine
- **Luke Fox** (gh-user-23) — proposed 100 — routine
- **James Gordon** (gh-user-07) — proposed 100 — routine
- **Victoria Zsasz** (gh-user-05) — proposed 100 — routine
- **Jason Todd** (gh-user-22) — proposed 98 — routine
- **Kate Kane** (gh-user-15) — proposed 94 — routine
- **Dick Grayson** (gh-user-19) — proposed 94 — routine
- **Floyd Lawton** (gh-user-12) — proposed 90 — routine
- **Basil Karlo** (gh-user-10) — proposed 90 — routine
- **Barbara Gordon** (gh-user-03) — proposed 88 — routine
- **Pamela Isley** (gh-user-01) — proposed 87 — routine
- **Harleen Quinzel** (gh-user-08) — proposed 87 — routine
- **Cassandra Cain** (gh-user-02) — proposed 87 — routine
- **Renee Montoya** (gh-user-13) — proposed 84 — routine
- **Bruce Wayne** (gh-user-20) — proposed 82 — routine
- **Slade Wilson** (gh-user-14) — proposed 79 — routine
- **Waylon Jones** (gh-user-16) — proposed 78 — routine
- **Oswald Cobblepot** (gh-user-17) — proposed 70 — routine
- **Alfreda Pennyworth** (gh-user-18) — proposed 43 — routine
- **Jervis Tetch** (gh-user-21) — proposed 14 — routine

### Edge cases needing a call
- **Stephanie Brown** (gh-user-04) — honor-gate fail / non-submission — late-policy call

### Low-confidence / needs-human-read
- _none_

### Upward-adjustment candidates
- **Floyd Lawton** (gh-user-12) — 90.0% — within 1.0 of A cut
- **Basil Karlo** (gh-user-10) — 90.0% — within 1.0 of A cut
- **Slade Wilson** (gh-user-14) — 79.0% — within 1.0 of B cut
- **Oswald Cobblepot** (gh-user-17) — 70.0% — within 1.0 of C cut

## Per-student feedback & grades

> [!note] The block quote under each student is the **student-facing** text `reg-lab-report deliver` ships verbatim to their `FEEDBACK.md`; the `<!-- internal -->` line (forensic notes + flags) is **stripped at delivery**. A `> _Comments:_` placeholder marks an **ungraded** submission — the comment prose is filled by **LLM agentic grading** (`reg-lab-digest`, per `docs/lab-digest-grader-prompt.md`), never scripted; `deliver` skips any block still holding the placeholder.

### Selina Kyle — **100 / 100**
*github: `gh-user-06` · Auto 70/70 · Writeup 30/30*

> Student-facing feedback.

<!-- internal: internal note -->

### Edward Nashton — **100 / 100**
*github: `gh-user-09` · Auto 70/70 · Writeup 30/30*

> Student-facing feedback.

<!-- internal: internal note -->

### Harvey Bullock — **100 / 100**
*github: `gh-user-25` · Auto 70/70 · Writeup 30/30*

> Student-facing feedback.

<!-- internal: internal note -->

### Harvey Dent — **100 / 100**
*github: `gh-user-24` · Auto 70/70 · Writeup 30/30*

> Student-facing feedback.

<!-- internal: internal note -->

### Roman Sionis — **100 / 100**
*github: `gh-user-11` · Auto 70/70 · Writeup 30/30*

> Student-facing feedback.

<!-- internal: internal note -->

### Luke Fox — **100 / 100**
*github: `gh-user-23` · Auto 70/70 · Writeup 30/30*

> Student-facing feedback.

<!-- internal: internal note -->

### James Gordon — **100 / 100**
*github: `gh-user-07` · Auto 70/70 · Writeup 30/30*

> Student-facing feedback.

<!-- internal: internal note -->

### Victoria Zsasz — **100 / 100**
*github: `gh-user-05` · Auto 70/70 · Writeup 30/30*

> Student-facing feedback.

<!-- internal: internal note -->

### Jason Todd — **98 / 100**
*github: `gh-user-22` · Auto 70/70 · Writeup 28/30*

> Student-facing feedback.

<!-- internal: internal note -->

### Kate Kane — **94 / 100**
*github: `gh-user-15` · Auto 70/70 · Writeup 24/30*

> Student-facing feedback.

<!-- internal: internal note -->

### Dick Grayson — **94 / 100**
*github: `gh-user-19` · Auto 70/70 · Writeup 24/30*

> Student-facing feedback.

<!-- internal: internal note -->

### Floyd Lawton — **90 / 100**
*github: `gh-user-12` · Auto 60/70 · Writeup 30/30*

> Student-facing feedback.

<!-- internal: internal note -->

### Basil Karlo — **90 / 100**
*github: `gh-user-10` · Auto 60/70 · Writeup 30/30*

> Student-facing feedback.

<!-- internal: internal note -->

### Barbara Gordon — **88 / 100**
*github: `gh-user-03` · Auto 60/70 · Writeup 28/30*

> Student-facing feedback.

<!-- internal: internal note -->

### Pamela Isley — **87 / 100**
*github: `gh-user-01` · Auto 60/70 · Writeup 27/30*

> Student-facing feedback.

<!-- internal: internal note -->

### Harleen Quinzel — **87 / 100**
*github: `gh-user-08` · Auto 60/70 · Writeup 27/30*

> Student-facing feedback.

<!-- internal: internal note -->

### Cassandra Cain — **87 / 100**
*github: `gh-user-02` · Auto 70/70 · Writeup 17/30*

> Student-facing feedback.

<!-- internal: internal note -->

### Renee Montoya — **84 / 100**
*github: `gh-user-13` · Auto 60/70 · Writeup 24/30*

> Student-facing feedback.

<!-- internal: internal note -->

### Bruce Wayne — **82 / 100**
*github: `gh-user-20` · Auto 60/70 · Writeup 22/30*

> Student-facing feedback.

<!-- internal: internal note -->

### Slade Wilson — **79 / 100**
*github: `gh-user-14` · Auto 60/70 · Writeup 19/30*

> Student-facing feedback.

<!-- internal: internal note -->

### Waylon Jones — **78 / 100**
*github: `gh-user-16` · Auto 60/70 · Writeup 18/30*

> Student-facing feedback.

<!-- internal: internal note -->

### Oswald Cobblepot — **70 / 100**
*github: `gh-user-17` · Auto 55/70 · Writeup 15/30*

> Student-facing feedback.

<!-- internal: internal note -->

### Alfreda Pennyworth — **43 / 100**
*github: `gh-user-18` · Auto 35/70 · Writeup 8/30*

> Student-facing feedback.

<!-- internal: internal note -->

### Jervis Tetch — **14 / 100**
*github: `gh-user-21` · Auto 10/70 · Writeup 4/30*

> Student-facing feedback.

<!-- internal: internal note -->

### Stephanie Brown — **0 / 100**
*github: `gh-user-04` · Auto 0/70 · Writeup 0/30*

> Student-facing feedback.

<!-- internal: internal note -->

## Canvas entry sheet

| Student (Last, First) | Proposed |
| --- | --: |
| Stephanie Brown | 0 |
| Harvey Bullock | 100 |
| Cassandra Cain | 87 |
| Oswald Cobblepot | 70 |
| Harvey Dent | 100 |
| Luke Fox | 100 |
| James Gordon | 100 |
| Barbara Gordon | 88 |
| Dick Grayson | 94 |
| Pamela Isley | 87 |
| Waylon Jones | 78 |
| Kate Kane | 94 |
| Basil Karlo | 90 |
| Selina Kyle | 100 |
| Floyd Lawton | 90 |
| Renee Montoya | 84 |
| Edward Nashton | 100 |
| Alfreda Pennyworth | 43 |
| Harleen Quinzel | 87 |
| Roman Sionis | 100 |
| Jervis Tetch | 14 |
| Jason Todd | 98 |
| Bruce Wayne | 82 |
| Slade Wilson | 79 |
| Victoria Zsasz | 100 |

## Provenance & caveats

Part A (autograde / honor / commits) = audit-grade facts. Part B (writeup scores + comments) = advisory, instructor-confirmed. Rendered deterministically by `reg-lab-report`.
