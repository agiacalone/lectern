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

## Canvas entry sheet

| Student (Last, First) | Proposed |
| --- | --: |
| Jervis Tetch | 14 |
| Selina Kyle | 100 |
| Edward Nashton | 100 |
| Alfreda Pennyworth | 43 |
| Stephanie Brown | 0 |
| Oswald Cobblepot | 70 |
| Floyd Lawton | 90 |
| Renee Montoya | 84 |
| Pamela Isley | 87 |
| Harleen Quinzel | 87 |
| Barbara Gordon | 88 |
| Harvey Bullock | 100 |
| Jason Todd | 98 |
| Kate Kane | 94 |
| Victoria Zsasz | 100 |
| Slade Wilson | 79 |
| Harvey Dent | 100 |
| Roman Sionis | 100 |
| Luke Fox | 100 |
| Dick Grayson | 94 |
| Bruce Wayne | 82 |
| Waylon Jones | 78 |
| James Gordon | 100 |
| Cassandra Cain | 87 |
| Basil Karlo | 90 |

## Provenance & caveats

Part A (autograde / honor / commits) = audit-grade facts. Part B (writeup scores + comments) = advisory, instructor-confirmed. Rendered deterministically by `reg-lab-report`.
