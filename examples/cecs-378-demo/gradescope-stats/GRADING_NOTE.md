---
type: grading-note
tags: [teaching, cecs-378, exam, gradescope, answer-key, internal]
visibility: private
icon: LiClipboardCheck
iconColor: var(--color-red)
---

# Exam 1 — Gradescope Grading Note (CECS 378 su26) — Item Analysis Format

> [!warning] Internal — answer key (gradescope-stats format)
> This file is the `reg-gradescope-stats`-compatible version of GRADING_NOTE.md.
> The exam-build tool emits a summary-table format; this per-question rubric-item
> format is required by `reg-gradescope-stats`. See demo README for the gap note.

#### A·Q1 · Symmetric-key cipher definition · 4 pts · MC

| Pts | Key | Rubric item (paste into Gradescope) |
| --: | --- | --- |
| 0 | `A·Q1·a` | (a) Uses separate public and private keys |
| +4 | `A·Q1·b` | (b) Both parties share the same secret key |
| 0 | `A·Q1·c` | (c) Requires no key; security via obscurity |
| 0 | `A·Q1·d` | (d) A side effect of digital signature schemes |
| 0 | `A·Q1·none` | No answer / multiple marks |

#### A·Q2 · Hash collision resistance · 4 pts · MC

| Pts | Key | Rubric item (paste into Gradescope) |
| --: | --- | --- |
| 0 | `A·Q2·a` | (a) It is computationally hard to find any input that maps to a given hash |
| 0 | `A·Q2·b` | (b) All inputs produce a hash of the same length |
| +4 | `A·Q2·c` | (c) It is computationally hard to find two distinct inputs with the same hash |
| 0 | `A·Q2·d` | (d) Hash computation always takes constant time |
| 0 | `A·Q2·none` | No answer / multiple marks |

#### A·Q3 · RSA encryption key choice · 4 pts · MC

| Pts | Key | Rubric item (paste into Gradescope) |
| --: | --- | --- |
| 0 | `A·Q3·a` | (a) The sender's private key |
| 0 | `A·Q3·b` | (b) A Diffie-Hellman session key |
| 0 | `A·Q3·c` | (c) The recipient's private key |
| +4 | `A·Q3·d` | (d) The recipient's public key |
| 0 | `A·Q3·none` | No answer / multiple marks |

#### A·Q4 · Stack buffer overflow target · 4 pts · MC

| Pts | Key | Rubric item (paste into Gradescope) |
| --: | --- | --- |
| 0 | `A·Q4·a` | (a) The heap allocator header |
| 0 | `A·Q4·b` | (b) Environment variables |
| +4 | `A·Q4·c` | (c) The saved return address on the stack |
| 0 | `A·Q4·d` | (d) The syscall dispatch table |
| 0 | `A·Q4·none` | No answer / multiple marks |

#### A·Q5 · Principle of least privilege · 4 pts · MC

| Pts | Key | Rubric item (paste into Gradescope) |
| --: | --- | --- |
| 0 | `A·Q5·a` | (a) Grant each process the maximum privileges it might ever need |
| 0 | `A·Q5·b` | (b) Share a single root account across all administrators |
| 0 | `A·Q5·c` | (c) Assign a mandatory label to every subject and object |
| +4 | `A·Q5·d` | (d) Grant only the minimum privileges required for the task |
| 0 | `A·Q5·none` | No answer / multiple marks |

#### A·Q6 · AES is a symmetric cipher · 2 pts · TF

| Pts | Key | Rubric item (paste into Gradescope) |
| --: | --- | --- |
| 0 | `A·Q6·true` | True |
| +2 | `A·Q6·false` | False |
| 0 | `A·Q6·none` | No answer / multiple marks |

#### A·Q7 · Hash maps to fixed-length output · 2 pts · TF

| Pts | Key | Rubric item (paste into Gradescope) |
| --: | --- | --- |
| +2 | `A·Q7·true` | True |
| 0 | `A·Q7·false` | False |
| 0 | `A·Q7·none` | No answer / multiple marks |

#### A·Q8 · RSA confidentiality uses recipient public key · 2 pts · TF

| Pts | Key | Rubric item (paste into Gradescope) |
| --: | --- | --- |
| 0 | `A·Q8·true` | True |
| +2 | `A·Q8·false` | False |
| 0 | `A·Q8·none` | No answer / multiple marks |

#### A·Q9 · NX stack does not stop ROP · 2 pts · TF

| Pts | Key | Rubric item (paste into Gradescope) |
| --: | --- | --- |
| 0 | `A·Q9·true` | True |
| +2 | `A·Q9·false` | False |
| 0 | `A·Q9·none` | No answer / multiple marks |

#### A·Q10 · Least privilege limits blast radius · 2 pts · TF

| Pts | Key | Rubric item (paste into Gradescope) |
| --: | --- | --- |
| +2 | `A·Q10·true` | True |
| 0 | `A·Q10·false` | False |
| 0 | `A·Q10·none` | No answer / multiple marks |
