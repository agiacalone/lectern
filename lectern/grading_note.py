"""Per-outcome GRADING_NOTE.md: the ISA work order for Gradescope.

One rubric row per possible outcome of each question: every MC choice, both
True/False sides, each FIB blank, and each authored rubric item on written
questions. Credit is carried by the points (``+N`` credited, ``0`` not), so a
grader who did not write the exam only decides which row applies. Every row
has a stable ``form·Qn·slot`` key that ``reg-gradescope-stats`` joins back to
Gradescope's *Export Evaluations* columns for per-distractor statistics.

Graduated from the Su26 prototype (``exam1_su26/build_grading_note.py``) so
that every ``reg-exam-build`` emits it.
"""
from __future__ import annotations

import re
from pathlib import Path

LETTERS = "abcdefgh"
_CHOICE_RE = re.compile(r"\\(correct|wrong)choice\{(.+?)\}\s*$", re.M)
_ORDER_RE = re.compile(r"^\s*%\s*order:\s*(.+?)\s*$")
_QSTART_RE = re.compile(r"\\item\b.*?\\textit\{\(\d+\s*pts?\)\}")
# Authored "Gradescope rubric" block (see docs/design/exam-tex-format.md):
#   \item \textbf{+1}~<criterion> \textit{(category)}
_GS_ITEM_RE = re.compile(r"^\s*\\item\s*\\textbf\{\+(\d+)\}~(.+?)\s*$", re.M)
_CAT_RE = re.compile(r"\\textit\{\((.+?)\)\}")


def sanitize(s: str) -> str:
    """LaTeX fragment -> plain text fit for a Gradescope rubric item."""
    s = s.replace("``", "“").replace("''", "”")
    s = s.replace(r"\oplus", "⊕").replace(r"\bmod", " mod ")
    s = s.replace(r"\_", "_").replace(r"\&", "&").replace(r"\%", "%").replace(r"\#", "#")
    s = s.replace("~", " ").replace("---", "—").replace("--", "–")
    s = re.sub(r"\$(.+?)\$", r"\1", s)
    s = s.replace("$", "")
    # exponents/subscripts: 2^{n} -> 2^n, 2^{2n} -> 2^(2n)
    s = re.sub(r"([\^_])\{([^{}]+)\}",
               lambda m: m.group(1) + (m.group(2) if len(m.group(2)) == 1 else f"({m.group(2)})"), s)
    for _ in range(3):  # unwrap nested \cmd{...}
        s = re.sub(r"\\[a-zA-Z]+\*?\{([^{}]*)\}", r"\1", s)
    s = re.sub(r"\\[a-zA-Z]+\*?", "", s)
    s = s.replace("{", "").replace("}", "")
    return re.sub(r"\s+", " ", s).strip()


def _strip_comments(block: str) -> str:
    return "\n".join(l for l in block.splitlines() if not re.match(r"^\s*%", l))


def parse_orders(tex_content: str) -> dict[int, str]:
    """1-based question number -> ``% order:`` value (default ``strict``)."""
    body = tex_content.split("\\begin{document}", 1)[-1]
    out: dict[int, str] = {}
    q, pending = 0, "strict"
    for line in body.splitlines():
        m = _ORDER_RE.match(line)
        if m:
            pending = m.group(1).strip().lower()
            continue
        if _QSTART_RE.search(line) and not line.lstrip().startswith("%"):
            q += 1
            out[q] = pending
            pending = "strict"
    return out


def _authored_items(block: str) -> list[tuple[str, str]]:
    """(pts, text) rows from an authored ``Gradescope rubric`` itemize, if any."""
    b = _strip_comments(block)
    if "Gradescope rubric" not in b:
        return []
    body = b.split("Gradescope rubric", 1)[1].split("\\end{itemize}", 1)[0]
    rows = []
    for pts, rest in _GS_ITEM_RE.findall(body):
        cats = _CAT_RE.findall(rest)
        text = sanitize(_CAT_RE.split(rest)[0] if cats else rest)
        if cats:
            text += " [" + "; ".join(sanitize(c) for c in cats) + "]"
        rows.append((f"+{pts}" if pts != "0" else "0", text))
    return rows


def outcome_rows(form: str, row, order: str = "strict") -> list[tuple[str, str, str]]:
    """(pts, key, item text) for every outcome of one question."""
    n, pts, t = row.q_num, row.points, row.type
    key = lambda slot: f"{form}·Q{n}·{slot}"
    block = getattr(row, "block", "") or ""

    authored = _authored_items(block)
    if authored:
        return [(p, key(f"r{j}"), txt) for j, (p, txt) in enumerate(authored, 1)]

    rows: list[tuple[str, str, str]] = []
    answer = (row.answer or "").strip()
    tf_answer = re.match(r"[A-Za-z]+", answer)
    tf_answer = tf_answer.group(0).lower() if tf_answer else ""

    if t == "mc":
        for idx, (kind, text) in enumerate(_CHOICE_RE.findall(_strip_comments(block))):
            c = LETTERS[idx]
            rows.append((f"+{pts}" if kind == "correct" else "0", key(c), f"({c}) {sanitize(text)}"))
        if not rows and answer:  # choices not marked up: credit the keyed letter only
            rows.append((f"+{pts}", key(answer.lower()), f"({answer.lower()})"))
    elif t == "tf" or (t == "code" and tf_answer in ("true", "false")):
        for side in ("true", "false"):
            slot = side[0].upper() if t == "tf" else side
            rows.append((f"+{pts}" if side == tf_answer else "0", key(slot), side.capitalize()))
    elif t == "fib" or t == "code":
        seg = [sanitize(s) for s in answer.split(";") if s.strip()]
        blanks = [re.split(r"\.\s|\(", s)[0].strip() for s in seg] or ["(see Scoring)"]
        per = pts / len(blanks)
        even = abs(per - round(per)) < 1e-9
        for j, b in enumerate(blanks, 1):
            rows.append((f"+{int(round(per))}" if even else "·", key(f"b{j}"),
                         f"blank {j} = “{b}”" + ("" if even else " (see Scoring)")))
        if len(blanks) >= 2 and order != "any":
            rows.append(("0", key("order"), "Incorrect order / wrong mapping (right values, wrong blanks)"))
    rows.append(("0", key("none"), "No answer / multiple marks"))
    return rows


def _course_tag(course: str) -> str:
    return course.strip().lower().replace(" ", "-")


def render(manifest, per_form_outline, per_form_pages, per_form_orders=None) -> str:
    forms = [f.id for f in manifest.forms]
    per_form_orders = per_form_orders or {}
    first = per_form_outline[forms[0]]
    total_pts = sum(r.points for r in first)
    nq = len(first)
    pages = per_form_pages.get(forms[0], 0)
    multi = len(forms) > 1

    shape = f"{len(forms)} forms ({'/'.join(forms)})" if multi else f"single form {forms[0]}"
    H = [
        "---", "type: grading-note",
        f"tags: [teaching, {_course_tag(manifest.course)}, exam, gradescope, answer-key, internal]",
        "visibility: private", "icon: LiClipboardCheck", "iconColor: var(--color-red)",
        "---", "",
        f"# {manifest.exam} — Gradescope Grading Note ({manifest.course} {manifest.term})", "",
        "> [!warning] Internal — ISA work order",
        "> Grader/ISA only, never student-facing. Enter each question's rubric items "
        "into Gradescope **verbatim**. Grade by matching: your only decision per paper "
        "is *which item applies*. Keys (`form·Qn·slot`) round-trip to per-distractor "
        "statistics, so keep them intact. Serials/register are grader infra (see "
        "[[project_exam_serial_internal_only]]).", "",
        f"{total_pts} pts · {nq} questions · {shape} · {pages} pages/exam", "",
        "## Gradescope setup",
        ("1. One assignment per form, linked as a **Version Set**." if multi
         else "1. One assignment: *Exam / Quiz*, fixed template."),
        "2. Upload `gradescope/<form>_template.pdf` (the BLANK form) as the template.",
        "3. Per question: draw the region, then add **one rubric item per row** "
        "(`Pts` + item text). Credit is the `+N` rows; `0` rows are no-credit "
        "(apply them for feedback and statistics). A `[Group]` tag names the "
        "criterion a written-answer item belongs to.",
        (f"4. Upload each form's scanned stack to its own version; length = {pages} pages."
         if multi else f"4. Upload the scanned stack; length = {pages} pages."), "",
        "> [!note] Written-answer scoring",
        "> `fib`/`code` questions carry a **Scoring** caption, which is the "
        "authoritative rule. Where blanks don't divide evenly the per-blank rows are "
        "reference only (marked `·`). When two credited items share a group, only "
        "one counts.", "",
    ]
    for f in forms:
        H.append(f"## Form {f}")
        H.append("")
        orders = per_form_orders.get(f, {})
        for r in per_form_outline[f]:
            H.append(f"#### {f}·Q{r.q_num} · {r.name} · {r.points} pts · {r.type.upper()}")
            if r.type in ("fib", "code") and r.rubric:
                H.append(f"*Scoring:* {sanitize(r.rubric)}")
            H.append("")  # blank line before the table, or Obsidian won't render it
            H += ["| Pts | Key | Rubric item (paste into Gradescope) |", "| --: | --- | --- |"]
            for p, k, txt in outcome_rows(f, r, orders.get(r.q_num, "strict")):
                H.append(f"| {p} | `{k}` | {txt.replace('|', '/')} |")
            H.append("")
    H += [
        "## Appeals",
        "Each paper's footer `Serial · ID` resolves to one student + form via "
        "`reg-exam-verify --register build/register.csv --dir build/`.", "",
    ]
    return "\n".join(H)


def emit(manifest, per_form_outline, per_form_pages, exam_root, per_form_orders=None) -> Path:
    out = Path(exam_root) / "GRADING_NOTE.md"
    out.write_text(render(manifest, per_form_outline, per_form_pages, per_form_orders),
                   encoding="utf-8")
    return out
