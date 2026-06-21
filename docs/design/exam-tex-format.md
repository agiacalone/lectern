# Exam `.tex` Format — House Standard

Conventions for exam `.tex` files built with `reg-exam-build`. The canonical
reference skeleton is `references/reference_exam.tex` — copy it, rename it, and
author your exam questions from there.

---

## Single-source architecture

**One `.tex` file per exam form.** Both the student PDF and the answer key PDF
are produced from the same source by toggling `\answersmode` at compile time.
There are no paired `<exam>.tex` / `<exam>_key.tex` files to keep in sync.

**Preamble switch** (place just before `\begin{document}`):

```latex
\newif\ifanswers
\ifdefined\answersmode
  \answerstrue
  \fancyhead[R]{\textit{\small Midterm 1 (Form A) --- KEY}}
\else
  \answersfalse
\fi
\def\examserial{XXXXXXXX}  % placeholder; reg-exam-build injects the real hash
```

**Build commands** (what `reg-exam-build` runs internally):

```bash
# Student PDF:
pdflatex -interaction=nonstopmode <exam>.tex

# Answer key:
pdflatex -interaction=nonstopmode -jobname=<exam>_key \
  '\def\answersmode{1}\input{<exam>.tex}'
```

Both passes run twice for reference stability. Intermediate `.aux`/`.log`/`.out`
files are cleaned up automatically.

---

## Per-student build support (A.2 preamble macros)

For `reg-exam-build --roster` and pack-mode individualized builds, the preamble
must declare four macros with `\@ifundefined+\def` defaults (not
`\providecommand`, which produces a `\long` macro that defeats the `\ifx\@empty`
guards). The `references/reference_exam.tex` skeleton ships with all four.

```latex
% --- per-student build support ---
\providecommand{\examserial}{XXXXXXXX}
\makeatletter
  \@ifundefined{studentname}{\def\studentname{}}{}
  \@ifundefined{studentid}{\def\studentid{}}{}
  \@ifundefined{studentserial}{\def\studentserial{}}{}
\makeatother
% --- end per-student build support ---
```

`reg-exam-build` injects `\def\examserial`, `\def\studentname`, `\def\studentid`,
and `\def\studentserial` on the pdflatex command line before `\input`. The
`\@ifundefined+\def` form means stand-alone `pdflatex <exam>.tex` still works
(the defaults take effect); the builder's injected `\def` overrides them at
build time.

**Existing `.tex` files** authored before this convention was established need a
one-time hand-patch: insert the four-line block above near the top of the preamble,
before any usage. After the patch the file builds in both stand-alone and
`--roster` / pack mode.

---

## NAME / STUDENT ID header block

The NAME / STUDENT ID / DATE block uses plain hairline rules — no background fill,
no colorbox. On individualized builds, the student's name and student ID are
**pre-printed on the lines** so the student only writes the date.

**Canonical LaTeX (preamble):**

```latex
% \fieldline{width}{value} — value rests ON the rule.
\newcommand{\fieldline}[2]{%
  \rlap{\hspace{0.5em}\raisebox{2.2pt}{#2}}\rule[-3pt]{#1}{0.8pt}%
}
% \identityinstruction — swaps between "VERIFY" and "PRINT CLEARLY"
\makeatletter
\newcommand{\identityinstruction}{%
  \ifx\studentname\@empty
    {\sffamily\bfseries\small\ding{43}~~PRINT CLEARLY. UNNAMED EXAMS CANNOT BE RETURNED OR GRADED.}%
  \else
    {\sffamily\bfseries\small\ding{43}~~VERIFY YOUR NAME AND STUDENT ID BELOW ARE CORRECT, THEN ADD TODAY'S DATE.}%
  \fi%
}
\makeatother
```

**Canonical LaTeX (document body):**

```latex
\noindent\identityinstruction
\par\vspace{12pt}
\noindent{\sffamily\bfseries\large NAME:}~\fieldline{13.5cm}{\large\studentname}
\par\vspace{14pt}
\noindent{\sffamily\bfseries\large STUDENT ID\#:}~\fieldline{5.5cm}{\large\ttfamily\studentid}%
\hfill{\sffamily\bfseries\large DATE:}~\rule[-3pt]{4cm}{0.8pt}
```

**Design note:** an earlier iteration used a light-grey background fill on the
NAME/ID block to increase visual prominence. This was reverted — photocopiers
re-quantize grey tones toward higher contrast, and the resulting darker background
made pencil marks illegible on copied exams. The plain hairline rule version is
the standard; do not re-add a background fill.

---

## Footer convention — timestamp + version serial + per-student ID

Every page of every printed exam carries a three-part footer:

```
[L] Generated YYYY-MM-DD HH:MM    [C] p. N    [R] Serial XXXXXXXX
```

In individualized builds the right element extends to:

```
[R] Serial XXXXXXXX · ID YYYYYYYY
```

**Generated timestamp** — pdfTeX primitive, refreshes on each compile. Not part
of the content hash (see canonicalization below).

**Version serial (source serial)** — SHA-256 of canonicalized `.tex` content,
first 8 hex chars, uppercase.

**Canonicalization rules** for serial computation:

1. Strip the existing `\def\examserial{...}` line (circular dependency prevention)
2. Strip `\answersfalse` / `\answerstrue` (toggle differs but content is shared)
3. Strip the `— KEY` suffix in the variant header (cosmetic)
4. SHA-256 the remainder → take first 8 hex chars, uppercase

This ensures that the student PDF and the answer key PDF carry the **same serial**
(they share the same source content), and that cosmetic changes to the key header
do not invalidate the serial.

**Per-student ID** — `SHA-256(source_serial + ":" + canonical_name(student_name))[:8].upper()`.

`canonical_name` strips diacritics, lowercases, collapses whitespace, and drops
trailing generational suffixes (`Jr`, `III`, etc.). The same canonicalization is
used by `reg-exam-verify` so verification always round-trips.

**Footer LaTeX:**

```latex
\fancyfoot[L]{\textit{\footnotesize Generated \buildtime}}
\fancyfoot[C]{\thepage}
\fancyfoot[R]{\textit{\footnotesize
  Serial \texttt{\examserial}%
  \ifx\studentserial\@empty\else~\textperiodcentered~ID \texttt{\studentserial}\fi
}}
```

---

## Answer key toggle — colors and macros

Student PDFs must be black and white. Key PDFs use color to make grading faster.
All color is gated inside `\ifanswers`, so the student PDF is byte-equivalent to
a fully B&W source.

**Palette (preamble):**

```latex
\definecolor{keyred}{HTML}{B71C1C}    % key landmarks: KEY banner, Answer:, Key: labels
\definecolor{keygreen}{HTML}{1B5E20}  % rubric +N items, correct MC choice
\definecolor{keygrey}{HTML}{616161}   % rubric +0 items, wrong MC choices

\newcommand{\correctchoice}[1]{\ifanswers\textcolor{keygreen}{\textbf{#1}}\else #1\fi}
\newcommand{\wrongchoice}[1]{\ifanswers\textcolor{keygrey}{#1}\else #1\fi}
```

**Always use `\correctchoice` / `\wrongchoice` for MC options** instead of bare
item content. The inline `Answer:` line is still required — it is the canonical
answer record that `parse_outline_from_tex` reads to generate `_outline.csv`.

**Color conventions:**

| Element | Color | Rationale |
|---|---|---|
| Page-1 KEY banner | Red filled box, white text | Impossible-to-miss; deters accidental student distribution |
| Header `KEY` tag | Red bold | Every-page landmark |
| Inline `Answer:` / `Key:` labels | Red | Grader's at-a-glance landmark |
| MC correct choice | Green bold | Eye lands on the right answer first |
| MC wrong choices | Grey | Distractors recede |
| Rubric `+N` (points awarded) | Green bold | Positive signal stands out |
| Rubric `+0` (failure mode) | Grey | De-emphasized unless grader needs them |

---

## True/False question structure — stacked choices

True/False items are typed `tf` by the `\textsc{T~/~F.}` label (which `_classify`
matches before the MC test, so the question stays `tf` even though it carries an
`(\alph*)` choice list). **The two options must be a stacked `enumerate` — one
option per line, always `(a) True` then `(b) False` — never inlined.** Gradescope's
region detection only finds answer choices that sit on their own lines; an inline
`T / F` with no listed options is invisible to it.

```latex
% name: Worm propagation (T/F)
\item \textit{(2 pts)}~\textsc{T~/~F.}~A worm can propagate across a network with no host program and no user action.
  \begin{enumerate}[label=(\alph*)]
    \item \correctchoice{True}
    \item \wrongchoice{False}
  \end{enumerate}
  \ifanswers \textcolor{keyred}{\textbf{Answer:} True} \fi
```

Wrap the correct option in `\correctchoice` (green in the key) and the other in
`\wrongchoice`. Keep the inline `\textbf{Answer:} True`/`False` reveal — that line,
not the choice list, is what `parse_outline_from_tex` reads for the `_outline.csv`
answer column, so it stays the word `True`/`False` (not a letter). Directions
should tell students to "circle the correct option, (a) True or (b) False."

---

## SA question structure — Gradescope-additive rubrics

Every short-answer question in the **key** carries a Gradescope-compatible additive
rubric block immediately after the answer prose.

```latex
\ifanswers \par\smallskip \textit{Key:} <answer prose>
  \par\smallskip \textsc{\footnotesize Coverage:}~{\footnotesize <where taught>}
  \par\smallskip \textbf{Gradescope rubric} \textit{(additive, N pts):}
  \begin{itemize}[noitemsep, leftmargin=1.5em, topsep=2pt]
    \item \textbf{+M}~<criterion — correct> \textit{(category)}
    \item \textbf{+0}~<failure mode for same category> \textit{(category)}
    \item \textbf{+1}~Bonus: <depth indicator> \textit{(Depth bonus)}
    \item \textbf{+0}~Blank / off-topic \textit{(catchall)}
  \end{itemize}
\else \writelines{16} \fi
```

**Paired rubric style:** each criterion appears as one or more `+N` items
immediately followed by `+0` partner items for known failure modes at that
criterion. Graders scan top-down: "did the student earn this criterion (+N)?
or did they make this specific mistake (+0)?"

**Category labels** in italic parentheses group related items. Enables
Gradescope's keyboard navigation when applying rubric items at speed.

**Coverage line:** every SA question carries a `Coverage:` line citing where
the material was taught. Format: `<lecture ref> · <textbook section> · <reading>`.
This is the fairness-audit chain: "this question was never taught" appeals are
answered with a specific slide and date.

---

## Compile discipline

Delete derived files before regenerating — synced binary files have a race
condition with cloud-sync tools that can corrupt the file if a stale version
is modified in place.

```bash
rm -f <exam>.pdf <exam>_key.pdf
pdflatex -interaction=nonstopmode <exam>.tex
pdflatex -interaction=nonstopmode <exam>.tex     # 2× for refs
pdflatex -interaction=nonstopmode -jobname=<exam>_key '\def\answersmode{1}\input{<exam>.tex}'
pdflatex -interaction=nonstopmode -jobname=<exam>_key '\def\answersmode{1}\input{<exam>.tex}'
rm -f *.aux *.log *.out
```

`reg-exam-build` performs all of this automatically, including delete-before-regen,
two-pass compile, and auxiliary file cleanup.

---

## Grade-appeals reproduction runbook

Exams are most frequently challenged at grade-appeal time, often weeks after
administration. This six-step runbook makes every delivered exam reproducible and
defensible.

**Step 1 — Obtain the disputed paper.** Get a legible image or the returned physical
copy. You need page 1 for the footer.

**Step 2 — Read the footer.**

```
Serial XXXXXXXX · ID YYYYYYYY
```

`Serial` is the source-level variant fingerprint (content hash of the `.tex`).
`ID` is the per-student fingerprint (hash of source serial + student canonical name).
Papers predating the roster-build era will show only `Serial`.

**Step 3 — Confirm form and student identity against the register.**

```bash
reg-exam-verify --register build/register.csv --dir build/
```

Walks every PDF in `build/`, extracts footer IDs, recomputes them from the register,
and reports any drift. To check a single paper by name:

```bash
reg-exam-verify --student "Doe, Jane" --register build/register.csv
```

Exits 0 on a clean match, 1 on any mismatch with a diagnostic. The PDF is
self-authenticating; the register is a convenience cross-check.

**Step 4 — Open the form's answer key and outline.**

- `build/<id>_key.pdf` — annotated key with correct choices bolded in green,
  failure modes in grey.
- `gradescope/<id>_outline.csv` — `q_num, points, type, answer`; use this to
  confirm the denominator on any disputed question.

**Step 5 — Cite per-question coverage from `PROVENANCE.md`** (or the `Coverage:`
lines in the `.tex` source). Every SA question carries a coverage citation mapping
to lecture slides, textbook sections, and reading-list anchors. This answers "this
was not covered" challenges with a specific source reference.

**Step 6 — Reproduce the student's exact paper if the original PDF is unavailable.**

```bash
reg-exam-build exam.build.yaml
```

The build is fully deterministic. Same manifest + `.tex` sources + roster +
`assign_seed` always produces the same output (the only variation is the
compile-time timestamp in the footer, which does not affect any forensic ID).
Pull the archived exam directory from the term archive bundle, re-run the build,
and the per-student PDF will match what was printed.

---

## Serial stability and content integrity

| Property | Guarantee |
|---|---|
| Deterministic | Same source content always hashes to the same serial |
| Cosmetic-invariant | Build timestamp does not affect the serial |
| Content-sensitive | Any edit to a question, answer, rubric, or coverage line changes the serial |
| Variant-distinct | Each hand-authored form (A, B, C) has its own serial |
| Tamper-evident | A `.tex` edited after administration produces a different serial than the printed copy carries — the mismatch is detectable by re-running the serial computation |

---

## Three-year-review archive checklist

When archiving an exam for accreditation or institutional review:

1. Archive both the `.tex` source and the compiled `.pdf`. The `.pdf` is what students
   received; the `.tex` is the canonical source.
2. Record the serial alongside the archived files (e.g., in the term archive
   `manifest.yaml`: `source_serial: "DC8C3554"`).
3. **To verify authenticity later:** re-run the serial computation against the
   archived `.tex`. If the computed serial matches the recorded serial, the file is
   unchanged. This is the audit-trail proof.
4. Keep the `exam.build.yaml` manifest and the `register.csv` alongside the
   `.tex` files. The serial alone proves the content is unchanged; the manifest
   proves what form and which students it was administered to.
