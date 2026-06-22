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
| Selina Kyle | bwayne | 70 | 30 | **100** |  |
| Dick Grayson | skyle | 70 | 30 | **100** |  |
| Victor Fries | dgrayson | 70 | 30 | **100** |  |
| Damian Wayne | bgordon | 70 | 30 | **100** |  |
| Stephanie Brown | jgordon | 70 | 30 | **100** |  |
| Luke Fox | hdent | 70 | 30 | **100** |  |
| Roman Sionis | pisley | 70 | 30 | **100** |  |
| Cassandra Cain | enashton | 70 | 30 | **100** |  |
| Kate Kane | ocobblepot | 70 | 28 | **98** |  |
| Waylon Jones | hquinzel | 70 | 24 | **94** |  |
| Renee Montoya | jcrane | 70 | 24 | **94** |  |
| Pamela Isley | vfries | 60 | 30 | **90** |  |
| Basil Karlo | kkane | 60 | 30 | **90** |  |
| Jonathan Crane | wjones | 60 | 28 | **88** |  |
| Oswald Cobblepot | ccain | 60 | 27 | **87** |  |
| Harleen Quinzel | jtodd | 60 | 27 | **87** |  |
| Floyd Lawton | tdrake | 70 | 17 | **87** |  |
| Edward Nashton | dwayne | 60 | 24 | **84** |  |
| Harvey Bullock | sbrown | 60 | 22 | **82** |  |
| Tim Drake | lfox | 60 | 19 | **79** |  |
| Lucius Fox | rmontoya | 60 | 18 | **78** |  |
| Harvey Dent | hbullock | 55 | 15 | **70** |  |
| Barbara Gordon | lucfox | 35 | 8 | **43** |  |
| Bruce Wayne | rsionis | 10 | 4 | **14** |  |
| James Gordon | flawton | 0 | 0 | **0** |  |

## Grading recommendations

### Confirm (routine)
- **Selina Kyle** (bwayne) — proposed 100 — routine
- **Dick Grayson** (skyle) — proposed 100 — routine
- **Victor Fries** (dgrayson) — proposed 100 — routine
- **Damian Wayne** (bgordon) — proposed 100 — routine
- **Stephanie Brown** (jgordon) — proposed 100 — routine
- **Luke Fox** (hdent) — proposed 100 — routine
- **Roman Sionis** (pisley) — proposed 100 — routine
- **Cassandra Cain** (enashton) — proposed 100 — routine
- **Kate Kane** (ocobblepot) — proposed 98 — routine
- **Waylon Jones** (hquinzel) — proposed 94 — routine
- **Renee Montoya** (jcrane) — proposed 94 — routine
- **Pamela Isley** (vfries) — proposed 90 — routine
- **Basil Karlo** (kkane) — proposed 90 — routine
- **Jonathan Crane** (wjones) — proposed 88 — routine
- **Oswald Cobblepot** (ccain) — proposed 87 — routine
- **Harleen Quinzel** (jtodd) — proposed 87 — routine
- **Floyd Lawton** (tdrake) — proposed 87 — routine
- **Edward Nashton** (dwayne) — proposed 84 — routine
- **Harvey Bullock** (sbrown) — proposed 82 — routine
- **Tim Drake** (lfox) — proposed 79 — routine
- **Lucius Fox** (rmontoya) — proposed 78 — routine
- **Harvey Dent** (hbullock) — proposed 70 — routine
- **Barbara Gordon** (lucfox) — proposed 43 — routine
- **Bruce Wayne** (rsionis) — proposed 14 — routine

### Edge cases needing a call
- **James Gordon** (flawton) — honor-gate fail / non-submission — late-policy call

### Low-confidence / needs-human-read
- _none_

### Upward-adjustment candidates
- **Pamela Isley** (vfries) — 90.0% — within 1.0 of A cut
- **Basil Karlo** (kkane) — 90.0% — within 1.0 of A cut
- **Tim Drake** (lfox) — 79.0% — within 1.0 of B cut
- **Harvey Dent** (hbullock) — 70.0% — within 1.0 of C cut

## Canvas entry sheet

| Student (Last, First) | Proposed |
| --- | --: |
| Stephanie Brown | 100 |
| Harvey Bullock | 82 |
| Cassandra Cain | 100 |
| Oswald Cobblepot | 87 |
| Jonathan Crane | 88 |
| Harvey Dent | 70 |
| Tim Drake | 79 |
| Luke Fox | 100 |
| Lucius Fox | 78 |
| Victor Fries | 100 |
| Barbara Gordon | 43 |
| James Gordon | 0 |
| Dick Grayson | 100 |
| Pamela Isley | 90 |
| Waylon Jones | 94 |
| Kate Kane | 98 |
| Basil Karlo | 90 |
| Selina Kyle | 100 |
| Floyd Lawton | 87 |
| Renee Montoya | 94 |
| Edward Nashton | 84 |
| Harleen Quinzel | 87 |
| Roman Sionis | 100 |
| Damian Wayne | 100 |
| Bruce Wayne | 14 |

## Provenance & caveats

Part A (autograde / honor / commits) = audit-grade facts. Part B (writeup scores + comments) = advisory, instructor-confirmed. Rendered deterministically by `reg-lab-report`.
