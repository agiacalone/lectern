---
type: grading-note
tags: [teaching, cecs-378, exam, gradescope, answer-key, internal]
visibility: private
icon: LiClipboardCheck
iconColor: var(--color-red)
---

# Exam 1 — Gradescope Grading Note (CECS 378 su26)

> [!warning] Internal — answer key
> Grader/ISA only. Never student-facing. Serials/register are grader infra (see [[project_exam_serial_internal_only]]).

60 pts · 13 questions · 1 forms · 4/exam

## Gradescope setup
1. Two assignments — one per form — linked as a **Version Set**.
2. Upload `gradescope/<form>_template.pdf` (the BLANK form) as each template.
3. Build the outline: one region per question, points from the table.
4. Enter the key in-UI (Gradescope imports nothing); keep `gradescope/<form>_answer_key.pdf` open.
5. Upload each form's scanned stack to its own version; length = 4 pages.

## Form A
| Q | Name | Pts | Type | Answer | Rubric |
| -: | --- | -: | --- | --- | --- |
| 1 | Symmetric-key cipher definition | 4 | mc | b | Correct = b (4 pts, all-or-nothing). |
| 2 | Hash collision resistance | 4 | mc | c | Correct = c (4 pts, all-or-nothing). |
| 3 | RSA encryption key choice | 4 | mc | d | Correct = d (4 pts, all-or-nothing). |
| 4 | Stack buffer overflow target | 4 | mc | c | Correct = c (4 pts, all-or-nothing). |
| 5 | Principle of least privilege | 4 | mc | d | Correct = d (4 pts, all-or-nothing). |
| 6 | AES is a symmetric cipher (T/F) | 2 | tf | False | Correct = False (2 pts, all-or-nothing). |
| 7 | Hash maps to fixed-length output (T/F) | 2 | tf | True | Correct = True (2 pts, all-or-nothing). |
| 8 | RSA confidentiality uses recipient public key (T/F) | 2 | tf | False | Correct = False (2 pts, all-or-nothing). |
| 9 | NX stack does not stop ROP (T/F) | 2 | tf | False | Correct = False (2 pts, all-or-nothing). |
| 10 | Least privilege limits blast radius (T/F) | 2 | tf | True | Correct = True (2 pts, all-or-nothing). |
| 11 | Hybrid encryption rationale (short answer) | 10 | mc |  | Symmetric is orders of magnitude faster; asymmetric is slow but solves key distribution. Hybrid uses asymmetric once (exchange a session key) then symmetric for bulk. 10 pts; 5–7 for identifying the speed gap + that hybrid exists without full mechanism. |
| 12 | Stack buffer overflow mitigations (short answer) | 10 | mc |  | Any two of stack canary / NX (W^X) / ASLR, each named + described, each with one circumvention (canary leak, ROP, address leak/brute-force). 5 pts each. |
| 13 | DAC vs. MAC access control (short answer) | 10 | mc |  | DAC = owner-controlled (Unix chmod/ACLs); MAC = system-policy-controlled, kernel-enforced (SELinux). (i) who decides + (ii) one example each. 3–4 pts per model without a concrete example. |

## Appeals
Each paper's footer `Serial · ID` resolves to one student + form via `reg-exam-verify --register build/register.csv --dir build/`.
