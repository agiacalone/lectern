# Lab Digest — Harness Grader-Prompt Contract

> Reference: `docs/design/lab-digest.md` §6 (fan-out harness).
> This document specifies the contract an agent grader must honour when
> processing tasks from `reg-lab-digest emit` and returning results for
> `reg-lab-digest merge`.

---

## 1. Inputs the grader receives

The harness reads **`digest_tasks.jsonl`** (one JSON object per line) and the
co-located **`digest.schema.json`** (output shape contract).

Each task object has this shape:

```json
{
  "github_id":    "string — student GitHub handle",
  "student":      "string — display name",
  "skip":         false,
  "writeup_text": "string — full WRITEUP.md body, frontmatter stripped",
  "autograde": {
    "points":    70,
    "cleared":   ["ward1", "ward2", "ward3"],
    "honor_ok":  true
  },
  "rubric": {
    "lab":                       "Lab 1 — Symmetric Cryptography (Spellbreaker)",
    "total":                     30,
    "comment_max_chars":         140,
    "student_comment_max_chars": 600,
    "cap":                       30,
    "sections": [
      {
        "key":               "ward1",
        "label":             "Ward I — The Wisp (ECB detection)",
        "max":               5,
        "requires_cleared":  "ward1",
        "anchors": {
          "strong":   "…",
          "adequate": "…",
          "weak":     "…",
          "missing":  "…"
        }
      }
    ],
    "bonus": [
      {
        "key":               "omega",
        "label":             "OMEGA WARD — CBC padding oracle (bonus)",
        "max":               4,
        "requires_cleared":  "ward4",
        "anchors": { "strong": "…", "adequate": "…", "weak": "…", "missing": "…" }
      }
    ]
  },
  "schema": { "…": "embedded digest.schema.json for self-validation" }
}
```

**Skip rule:** if `skip: true`, do **not** call the model.  Write a result with
`abstain: true`, `confidence: "low"`, all section scores 0, `comment: ""`,
`student_comment: ""`, and `total: 0`.  Merge will handle it.

---

## 2. Scoring philosophy — mechanism over outcome

The rubric's standing instruction (inherited from `spellbreaker_lab_grading_rubric.md`):

> *"Tell me HOW the ward broke, not merely that it did.  'I ran the attack'
> earns nothing; 'the ward leaked X, which let me do Y' earns everything."*

Grade every section on **mechanism, not outcome**.  Use the `anchors` embedded
in each section:

| Tier | Fraction of `max` | Meaning |
|---|---|---|
| `strong`   | 100 % | Names the mechanism precisely; explains the causal chain (leak → exploit step → result). |
| `adequate` | ~70 % | Right idea, thin on the *why*; mechanism named but causal chain partial or slightly off. |
| `weak`     | ~35 % | Restates the prompt / "I did the attack" / conflates concepts / shows misunderstanding. |
| `missing`  |   0 % | Blank, or no entry for a ward the student defeated. |

These percentages are guides; use judgment within the tier.  Do **not** award
more than `max` for any section.

**Partial-ward rule (enforced by `merge`, not the grader):** if a ward is not
in `autograde.cleared`, `merge` will force that section's score to 0 regardless
of what the grader returns.  Score the writeup as written; do not try to
second-guess the autograde.

**Bonus sections:** score only if the writeup contains a genuine attempt.
`missing` anchor → 0; do not penalise a student who skipped the bonus.

---

## 3. Abstain rather than guess

If the writeup is too ambiguous, too short, or not in English to score with
confidence, set `abstain: true` and `confidence: "low"`.  `merge` will flag the
result as `needs-human-read` and leave the score *pending* for human review.
**Never fabricate a score to avoid abstaining.**

Abstain triggers:

- Writeup body is effectively empty (< 20 words of substantive content).
- The text is in a language the grader cannot reliably assess.
- The grader genuinely cannot distinguish `adequate` from `weak` for a
  high-weight section (ward2 ≥ 10 pts) after one careful read.

Use `confidence: "medium"` when the score is defensible but uncertain in one
section.  Use `confidence: "high"` when the mechanism analysis is clear.

---

## 4. Output shape

Emit **one JSON object per line** to **`digest_results.jsonl`**, conforming to
`digest.schema.json`.  Every field is required.

```json
{
  "github_id":  "string — must match the task's github_id exactly",
  "sections": {
    "ward1":  0,
    "ward2":  0,
    "ward3":  0,
    "craft":  0
  },
  "bonus": {
    "omega": 0
  },
  "total":          0,
  "comment":        "string — ≤ comment_max_chars (140); INTERNAL instructor note",
  "student_comment":"string — ≤ student_comment_max_chars (600); STUDENT-FACING prose",
  "confidence":     "high | medium | low",
  "abstain":        false
}
```

Rules:

- `sections` must include **every** core section key from the rubric, in any
  order; each value is an integer 0 ≤ score ≤ section.max.
- `bonus` must include **every** bonus key, or may be an empty object `{}` if
  no bonus sections exist in the rubric.
- `total` is **advisory** — `merge` recomputes the authoritative total as
  `min(cap, sum(sections) + sum(bonus))`.  Provide your arithmetic anyway; a
  mismatch is flagged as `digest:total-drift` but does not block the merge.
- `comment` must be ≤ `comment_max_chars`; `merge` truncates at that boundary.
  This is the **internal instructor note** — terse shorthand, one sentence per
  weak section (e.g. "Ward II: explains outcome only, no byte-alignment
  mechanism; craft: no sources cited.").
- `student_comment` must be ≤ `student_comment_max_chars`. This is the
  **student-facing** feedback that gets delivered verbatim to the student's
  repo. Write it accordingly:
  - Constructive and mechanism-focused; speak to the student in second person.
  - The lab's in-world vocabulary (wards, grimoire, OMEGA, sins) is fine.
  - **No cross-student comparison** and **no internal jargon** (triage verdicts,
    "honor-gate", grader/tool names, advisory framing) — `merge` runs a
    sanitize lint and **withholds** any `student_comment` that leaks these.
  - **Never penalize honest AI disclosure.** A student who discloses LLM use
    transparently is following policy, not cheating.
- When `abstain: true`, set `confidence: "low"`, all numeric fields to 0, and
  `student_comment: ""` (it will be withheld regardless).

---

## 5. Worked example — one task

**Input task (excerpt):**

```json
{
  "github_id": "HarleyQ",
  "student": "Harley Quinn",
  "skip": false,
  "writeup_text": "## Ward I\nECB encrypts each 16-byte block independently with no IV. I fed 32 identical bytes; the two output blocks were identical — this is the ECB penguin property. Real-world: AES-ECB image encryption (CWE-327).\n\n## Ward II\nMeasured block size: kept prepending 'A' until output grew by 16 bytes (block size = 16). Recovery: align the target byte at the last position of a known block, brute-force 256 candidates, keep the one whose ciphertext block matches the oracle's. Shift by one byte and repeat to recover each byte of the secret. Real-world: ECB-mode session token leakage.\n\n## Ward III\nCBC decrypts as P[i] = D(C[i]) XOR C[i-1]. I flipped byte 6 of C[0] by XOR-ing delta = ord('a') XOR ord('A'). That exact bit flipped in P[1][6], letting me forge the sigil from lowercase to uppercase without the key. Real-world: unauthenticated CBC cookie tampering.\n\n## Sources\nAnderson, *Security Engineering* §5.3; OWASP Cryptographic Failures; POODLE CVE-2014-3566.",
  "autograde": { "points": 70, "cleared": ["ward1","ward2","ward3","ward4"], "honor_ok": true },
  "rubric": { "comment_max_chars": 140, "sections": ["…"], "bonus": ["…"] }
}
```

**Expected output:**

```json
{
  "github_id": "HarleyQ",
  "sections": { "ward1": 5, "ward2": 10, "ward3": 9, "craft": 6 },
  "bonus":    { "omega": 0 },
  "total":    30,
  "comment":  "All sections strong; mechanism-causal chain present throughout. Omega not attempted.",
  "student_comment": "Excellent work — every ward explained at the mechanism level, with the CBC bit-flip equation and concrete real-world classes. Strong, well-sourced grimoire. OMEGA wasn't attempted; give the padding oracle a try next time.",
  "confidence": "high",
  "abstain":  false
}
```

Rationale: Ward I names ECB determinism + ECB penguin (strong, 5/5). Ward II
gives the block-size probe, the byte-alignment + 256-guess recovery, and a
concrete real-world case (strong, 10/10). Ward III cites the XOR equation, the
specific byte + delta, and names the real-world class (strong, 9/9). Craft has
multiple relevant sources with context (strong, 6/6). Omega not attempted →
0 (no penalty).

---

## 6. Parallelisation note

The harness (e.g. `superpowers:dispatching-parallel-agents`) may fan tasks out
to N agents running concurrently.  Each agent scores its assigned slice and
appends to its own partial `digest_results.jsonl`; the coordinator concatenates
them before calling `reg-lab-digest merge`.  **Each line is independent** —
ordering in the results file does not matter; `merge` matches on `github_id`.

---

## 7. Quick-reference checklist

Before writing a result line, confirm:

- [ ] `github_id` copied exactly from the task (no case change).
- [ ] All core section keys present in `sections` (check against rubric).
- [ ] All bonus keys present in `bonus` (even if 0).
- [ ] Each score ≤ section.max.
- [ ] `comment` length ≤ `comment_max_chars` (internal note).
- [ ] `student_comment` ≤ `student_comment_max_chars`; student-facing, no internal
      jargon, no cross-student names, AI disclosure not penalized.
- [ ] `confidence` set; `abstain` set.
- [ ] If `skip: true` on the task → `abstain: true`, all zeros, `confidence: "low"`.
- [ ] Output line is valid JSON (no trailing commas, no Python-style `True`/`None`).
