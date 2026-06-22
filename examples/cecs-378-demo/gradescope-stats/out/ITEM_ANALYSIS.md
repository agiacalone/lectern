---
type: item-analysis
tags: [teaching, cecs-378, exam, gradescope, item-analysis, internal]
visibility: private
icon: LiChartBar
iconColor: var(--color-blue)
---

# Exam 1 — Item Analysis (CECS 378 su26)

> [!info] Internal — generated from Gradescope *Export Evaluations*
> Per-question difficulty + per-distractor selection counts, joined to the `form·Qn·slot` keys in [[GRADING_NOTE]]. Regenerate with `reg-gradescope-stats`.

**Reading the tables.** *p* = fraction earning full marks (difficulty; lower = harder). A distractor chosen by **0** students is non-functioning (✗). A distractor chosen by **more** students than the key (⚠) is a miskey-or-genuinely-confusing item worth review.

> [!abstract]- Difficulty summary (hardest first)
>
> | Q | Topic | Type | p | mean |
> | --- | --- | --- | --: | --: |
> | A·Q2 | Hash collision resistance | MC | 0.60 | 2.40/4 |
> | A·Q5 | Principle of least privilege | MC | 0.60 | 2.40/4 |
> | A·Q9 | NX stack does not stop ROP | TF | 0.60 | 1.20/2 |
> | A·Q1 | Symmetric-key cipher definition | MC | 0.70 | 2.80/4 |
> | A·Q4 | Stack buffer overflow target | MC | 0.70 | 2.80/4 |
> | A·Q3 | RSA encryption key choice | MC | 0.80 | 3.20/4 |
> | A·Q6 | AES is a symmetric cipher | TF | 0.80 | 1.60/2 |
> | A·Q8 | RSA confidentiality uses recipient public key | TF | 0.80 | 1.60/2 |
> | A·Q7 | Hash maps to fixed-length output | TF | 0.90 | 1.80/2 |
> | A·Q10 | Least privilege limits blast radius | TF | 0.90 | 1.80/2 |

## Form A

#### A·Q1 · Symmetric-key cipher definition · MC · 4 pts
*n = 10 · p = 0.70 · mean = 2.80/4*

| Key | Distractor | n | % | |
| --- | --- | --: | --: | --- |
| `A·Q1·a` | (a) Uses separate public and private keys | 2 | 20% |  |
| `A·Q1·b` | (b) Both parties share the same secret key | 7 | 70% | ✔ key |
| `A·Q1·c` | (c) Requires no key; security via obscurity | 0 | 0% | ✗ dead |
| `A·Q1·d` | (d) A side effect of digital signature schemes | 0 | 0% | ✗ dead |
| `A·Q1·none` | No answer / multiple marks | 1 | 10% |  |

#### A·Q2 · Hash collision resistance · MC · 4 pts
*n = 10 · p = 0.60 · mean = 2.40/4*

| Key | Distractor | n | % | |
| --- | --- | --: | --: | --- |
| `A·Q2·a` | (a) It is computationally hard to find any input that maps to a given hash | 3 | 30% |  |
| `A·Q2·b` | (b) All inputs produce a hash of the same length | 0 | 0% | ✗ dead |
| `A·Q2·c` | (c) It is computationally hard to find two distinct inputs with the same hash | 6 | 60% | ✔ key |
| `A·Q2·d` | (d) Hash computation always takes constant time | 1 | 10% |  |
| `A·Q2·none` | No answer / multiple marks | 0 | 0% | ✗ dead |

#### A·Q3 · RSA encryption key choice · MC · 4 pts
*n = 10 · p = 0.80 · mean = 3.20/4*

| Key | Distractor | n | % | |
| --- | --- | --: | --: | --- |
| `A·Q3·a` | (a) The sender's private key | 1 | 10% |  |
| `A·Q3·b` | (b) A Diffie-Hellman session key | 0 | 0% | ✗ dead |
| `A·Q3·c` | (c) The recipient's private key | 1 | 10% |  |
| `A·Q3·d` | (d) The recipient's public key | 8 | 80% | ✔ key |
| `A·Q3·none` | No answer / multiple marks | 0 | 0% | ✗ dead |

#### A·Q4 · Stack buffer overflow target · MC · 4 pts
*n = 10 · p = 0.70 · mean = 2.80/4*

| Key | Distractor | n | % | |
| --- | --- | --: | --: | --- |
| `A·Q4·a` | (a) The heap allocator header | 1 | 10% |  |
| `A·Q4·b` | (b) Environment variables | 2 | 20% |  |
| `A·Q4·c` | (c) The saved return address on the stack | 7 | 70% | ✔ key |
| `A·Q4·d` | (d) The syscall dispatch table | 0 | 0% | ✗ dead |
| `A·Q4·none` | No answer / multiple marks | 0 | 0% | ✗ dead |

#### A·Q5 · Principle of least privilege · MC · 4 pts
*n = 10 · p = 0.60 · mean = 2.40/4*

| Key | Distractor | n | % | |
| --- | --- | --: | --: | --- |
| `A·Q5·a` | (a) Grant each process the maximum privileges it might ever need | 2 | 20% |  |
| `A·Q5·b` | (b) Share a single root account across all administrators | 1 | 10% |  |
| `A·Q5·c` | (c) Assign a mandatory label to every subject and object | 1 | 10% |  |
| `A·Q5·d` | (d) Grant only the minimum privileges required for the task | 6 | 60% | ✔ key |
| `A·Q5·none` | No answer / multiple marks | 0 | 0% | ✗ dead |

#### A·Q6 · AES is a symmetric cipher · TF · 2 pts
*n = 10 · p = 0.80 · mean = 1.60/2*

| Key | Distractor | n | % | |
| --- | --- | --: | --: | --- |
| `A·Q6·true` | True | 2 | 20% |  |
| `A·Q6·false` | False | 8 | 80% | ✔ key |
| `A·Q6·none` | No answer / multiple marks | 0 | 0% | ✗ dead |

#### A·Q7 · Hash maps to fixed-length output · TF · 2 pts
*n = 10 · p = 0.90 · mean = 1.80/2*

| Key | Distractor | n | % | |
| --- | --- | --: | --: | --- |
| `A·Q7·true` | True | 9 | 90% | ✔ key |
| `A·Q7·false` | False | 1 | 10% |  |
| `A·Q7·none` | No answer / multiple marks | 0 | 0% | ✗ dead |

#### A·Q8 · RSA confidentiality uses recipient public key · TF · 2 pts
*n = 10 · p = 0.80 · mean = 1.60/2*

| Key | Distractor | n | % | |
| --- | --- | --: | --: | --- |
| `A·Q8·true` | True | 1 | 10% |  |
| `A·Q8·false` | False | 8 | 80% | ✔ key |
| `A·Q8·none` | No answer / multiple marks | 1 | 10% |  |

#### A·Q9 · NX stack does not stop ROP · TF · 2 pts
*n = 10 · p = 0.60 · mean = 1.20/2*

| Key | Distractor | n | % | |
| --- | --- | --: | --: | --- |
| `A·Q9·true` | True | 3 | 30% |  |
| `A·Q9·false` | False | 6 | 60% | ✔ key |
| `A·Q9·none` | No answer / multiple marks | 1 | 10% |  |

#### A·Q10 · Least privilege limits blast radius · TF · 2 pts
*n = 10 · p = 0.90 · mean = 1.80/2*

| Key | Distractor | n | % | |
| --- | --- | --: | --: | --- |
| `A·Q10·true` | True | 9 | 90% | ✔ key |
| `A·Q10·false` | False | 1 | 10% |  |
| `A·Q10·none` | No answer / multiple marks | 0 | 0% | ✗ dead |
