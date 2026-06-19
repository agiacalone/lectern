# Lectern Suite-Linking + Title-Capitalization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Capitalize Lectern's product title, add the name-trivia hook, embed the suite cross-link, and fix the Oracle-attribution split — without renaming any identifier (lectern keeps its repo/command/package names).

**Architecture:** A single branch (`suite/linking`) carries documentation-only edits. The product **title** becomes **Lectern** (capital) in prose + README H1; the lowercase `lectern` identifier (repo, `reg-*` commands, package) is unchanged. The suite section and the name-trivia line come verbatim from the suite spec.

**Tech Stack:** Python `reg-*` CLI toolchain; Markdown/LaTeX/CSV/YAML open formats; Claude Code skill (`SKILL.md`).

## Global Constraints

- See `agiacalone/oracle` repo `docs/superpowers/specs/2026-06-19-lms-suite-rebrand-design.md` for suite-wide rules. Summary:
- Product **title** is **`Lectern`** (capital) in prose + README H1. The **identifier** `lectern` stays lowercase (repo, `reg-*` commands, package, skill name). Capitalize only where "Lectern" is the *product* in a sentence ("Lectern handles…"); keep lowercase for command/package/code references.
- **No identifier rename** — this is the one suite repo keeping its name; this plan is docs-only.
- **Do NOT touch** historical/dated files: `docs/superpowers/**`, `archive/**`.
- Embed the canonical **suite section** (suite spec §4) + the **Lectern name-trivia blockquote** (suite spec §4.1), both verbatim.
- **Oracle-entry fix (suite spec §5):** clarify that **code/lab autograding is performed by Oracle**; lectern *coordinates* the artifacts and does **exam + MC-bubble (Gradescope)** grading. Do **not** remove lectern's legitimate bubble-sheet autograde docs.
- Commits GPG-signed (`git commit -S`), per task.

---

### Task 1: Branch + README title, trivia, suite section

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Branch**

```bash
cd ~/git/lectern
git switch -c suite/linking
```

- [ ] **Step 2: Capitalize the title + add trivia**

`# lectern` → `# Lectern`. Keep the `**The Registrar** — …` subtitle line. Directly under the H1 (above or just under the subtitle), add the **Lectern name-trivia blockquote verbatim** from suite spec §4.1.

- [ ] **Step 3: Embed the suite section**

Insert the **canonical suite section verbatim** from suite spec §4 (the three-way Lectern · Scriptorium · Oracle table), with *You are here: **Lectern***. Place it near the top (after the intro, before "Why open formats") so faculty see the suite framing immediately.

- [ ] **Step 4: Capitalize product-title uses in the README intro**

In prose where "lectern" is the *product* (e.g. "lectern handles the full administrative lifecycle…", "lectern's answer is…"), capitalize to "Lectern". Leave `reg-*` command names and any code/package references lowercase.

```bash
git grep -n '\blectern\b' -- README.md   # review each; capitalize product-title uses only
```

- [ ] **Step 5: Commit**

```bash
git add README.md
git commit -S -m "docs(readme): capitalize Lectern title, add trivia + suite section"
```

---

### Task 2: Oracle-attribution fix

**Files:**
- Modify: `README.md` (the "Autograding integration" entry, ~line 219)

**Interfaces:**
- Consumes: suite spec §5 (the autograding split).

- [ ] **Step 1: Rewrite the "Autograding integration" entry**

The current entry implies lectern owns autograding. Rewrite so it states the split explicitly: **Oracle** (`agiacalone/oracle`) performs the **code/lab autograding** (verify-by-proof oracle service + sandboxed `gradebox` runner); **Lectern** *coordinates and records* it — the archive bundle's `manifest.yaml` tracks template-repo commits, lab names, exam serials, and grade distributions, and ISA-published artifacts (keys, rubrics) live in the structured Drive folder. Add an inline link to the Oracle repo. Keep the existing manifest/Drive detail — only add the attribution and the Oracle link.

- [ ] **Step 2: Confirm legitimate lectern autograde docs are untouched**

```bash
git grep -n -i 'autograde' -- docs/gradescope-workflow.md docs/design/exam-system.md
```
Expected: unchanged — those describe lectern's own MC-bubble/Gradescope autograde, which is correct and stays.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -S -m "docs(readme): attribute code/lab autograding to Oracle, clarify the grading split"
```

---

### Task 3: Skill/agent-doc title sweep + dual-operability check

**Files:**
- Modify: `SKILL.md` (and `AGENTS.md` if present; create if absent)

- [ ] **Step 1: Capitalize product-title uses in SKILL.md**

In `SKILL.md`, capitalize "Lectern" where it's the product name in prose; keep the skill `name:` frontmatter and `reg-*` command references lowercase. If a "grading"/"autograding" line miscredits lectern, align it to the §5 split.

- [ ] **Step 2: Dual-operability — AGENTS.md**

Confirm an `AGENTS.md` (AI-operation guide) exists naming the `reg-*` CLI entry points and stating every skill action maps to a `reg-*` command. If absent, create a minimal one (lectern is already fully CLI-operable — this just documents the AI path).

- [ ] **Step 3: Commit**

```bash
git add SKILL.md AGENTS.md
git commit -S -m "docs: capitalize Lectern in skill/agent docs, ensure AGENTS.md"
```

---

### Task 4: Final verification

- [ ] **Step 1: Suite-consistency check**

```bash
grep -n "Part of the teaching suite" README.md          # suite section present
grep -n "Trivia:" README.md                              # trivia line present
grep -n "agiacalone/oracle" README.md                    # Oracle cross-link present
head -3 README.md                                        # title reads "# Lectern"
```
Expected: all present; H1 is `# Lectern`.

- [ ] **Step 2: No identifier breakage**

```bash
git grep -n 'reg-' -- README.md | head        # reg-* command names intact (lowercase)
```
Expected: command names unchanged.

- [ ] **Step 3: Push + PR (only when Anthony says)**

```bash
git push -u origin suite/linking
gh pr create --title "Lectern: capitalize title + suite cross-link + Oracle attribution" --body "<summary + suite-spec pointer>"
```

---

## Self-Review

**Spec coverage:** suite §2 casing (title capital, identifier lowercase) → Tasks 1,3 + Global Constraints. §4 suite section → Task 1 Step 3. §4.1 trivia → Task 1 Step 2. §5 Oracle-attribution fix → Task 2. §3 dual-operability → Task 3 Step 2. Covered.

**Placeholder scan:** No vague directives; each capitalization step says "capitalize product-title uses only, keep commands lowercase" with a grep to review. The Oracle-attribution rewrite names exactly what to add (Oracle link + split) and what to keep (manifest/Drive detail).

**Identifier consistency:** `Lectern` (title) vs `lectern`/`reg-*` (identifier/commands) distinction stated and checked; no rename anywhere.
