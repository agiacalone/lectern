"""exam_pack — multi-form / A-B exam orchestration + Gradescope product emission.

Drives the existing lectern.exam_build (build_variant / build_roster) per form,
assigns forms to students, and emits Gradescope region/bubble products.

See docs/design/exam-multiform-gradescope-design.md for the
full design spec.
"""
from __future__ import annotations

import csv
import random
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml
from lectern.exam_serial import canonical_name
from lectern.exam_build import ExamBuildConfig, build_variant, build_roster

_VALID_ASSIGN = {"alternating", "seeded-random", "every-form"}
_VALID_GRADESCOPE = {"region", "bubble", "none"}


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class FormSpec:
    id: str
    source: Path


@dataclass
class ExamManifest:
    course: str
    term: str
    exam: str
    forms: list[FormSpec]
    individualized: bool = False
    roster: Path | None = None
    assign: str = "alternating"          # alternating | seeded-random | every-form
    assign_seed: str | None = None
    gradescope: str = "none"             # region | bubble | none
    points: int | None = None


@dataclass
class OutlineRow:
    q_num: int
    points: int
    type: str                            # mc | tf | fib | code
    answer: str
    name: str = ""
    rubric: str = ""


@dataclass
class PackResult:
    forms: list[str]
    build_dir: Path
    gradescope_dir: Path | None
    register_csv: Path | None
    student_pdf_count: int
    grading_note: Path | None = None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_manifest(path: Path) -> ExamManifest:
    path = Path(path).resolve()
    if not path.is_file():
        raise SystemExit(f"exam_pack: manifest not found: {path}")
    base = path.parent
    data = yaml.safe_load(path.read_text()) or {}

    for key in ("course", "term", "exam", "forms"):
        if not data.get(key):
            raise SystemExit(f"exam_pack: manifest missing required key '{key}'")

    forms: list[FormSpec] = []
    seen: set[str] = set()
    for entry in data["forms"]:
        fid = str(entry.get("id", "")).strip()
        src = entry.get("source")
        if not fid or not src:
            raise SystemExit("exam_pack: each form needs 'id' and 'source'")
        if fid in seen:
            raise SystemExit(f"exam_pack: duplicate form id '{fid}'")
        seen.add(fid)
        src_path = (base / src).resolve()
        if not src_path.is_file():
            raise SystemExit(f"exam_pack: form '{fid}' source not found: {src_path}")
        forms.append(FormSpec(id=fid, source=src_path))

    individualized = bool(data.get("individualized", False))
    roster = data.get("roster")
    roster_path = (base / roster).resolve() if roster else None
    if individualized:
        if roster_path is None:
            raise SystemExit("exam_pack: individualized: true requires a 'roster'")
        if not roster_path.is_file():
            raise SystemExit(f"exam_pack: roster not found: {roster_path}")

    assign = str(data.get("assign", "alternating"))
    if assign not in _VALID_ASSIGN:
        raise SystemExit(f"exam_pack: assign must be one of {sorted(_VALID_ASSIGN)}")
    assign_seed = data.get("assign_seed")
    if assign == "seeded-random" and not assign_seed:
        raise SystemExit("exam_pack: seeded-random requires assign_seed")

    gradescope = str(data.get("gradescope", "none"))
    if gradescope not in _VALID_GRADESCOPE:
        raise SystemExit(f"exam_pack: gradescope must be one of {sorted(_VALID_GRADESCOPE)}")

    return ExamManifest(
        course=str(data["course"]), term=str(data["term"]), exam=str(data["exam"]),
        forms=forms, individualized=individualized, roster=roster_path,
        assign=assign, assign_seed=(str(assign_seed) if assign_seed else None),
        gradescope=gradescope, points=data.get("points"),
    )


def assign_forms(names: list[str], form_ids: list[str], policy: str, seed: str | None) -> dict[str, str]:
    ordered = sorted(names, key=canonical_name)
    if policy == "every-form":
        return {n: list(form_ids) for n in ordered}
    if policy == "seeded-random":
        rng = random.Random(seed)
        rng.shuffle(ordered)
    # alternating (and post-shuffle seeded-random): round-robin
    return {n: form_ids[i % len(form_ids)] for i, n in enumerate(ordered)}


_PTS_RE = re.compile(r"\\textit\{\((\d+)\s*pts?\)\}")
_ANS_RE = re.compile(r"\\textbf\{Answer:\}\s*([^\\}\n]+)")
_NAME_RE = re.compile(r"^\s*%\s*name:\s*(.+?)\s*$")
_RUBRIC_RE = re.compile(r"^\s*%\s*rubric:\s*(.+?)\s*$")
_QSTART_RE = re.compile(r"\\item\b.*?\\textit\{\(\d+\s*pts?\)\}")


def _strip_comments(block: str) -> str:
    """Remove LaTeX comment lines (% ...) from a block before classification."""
    return "\n".join(
        line for line in block.splitlines()
        if not re.match(r"^\s*%", line)
    )


def _classify(block: str) -> str:
    b = _strip_comments(block)
    if "lstlisting" in b:
        return "code"
    if "\\textsc{T" in b or re.search(r"\bT\s*/\s*F\b", b):
        return "tf"
    if "\\correctchoice" in b or re.search(r"\\begin\{enumerate\}\[label=\(\\alph", b):
        return "mc"
    if "\\rule[" in b or "\\_\\_\\_" in b or "fill in the blank" in b.lower():
        return "fib"
    return "mc"


def _parse_annotations(tex_content: str) -> dict[int, tuple[str, str]]:
    """Map 1-based question number -> (name, rubric) from % name:/% rubric:
    comments immediately preceding each (N pts) \\item, in document order."""
    body = tex_content.split("\\begin{document}", 1)[-1]
    out: dict[int, tuple[str, str]] = {}
    q = 0
    pending_name = ""
    pending_rubric: list[str] = []
    for line in body.splitlines():
        m_name = _NAME_RE.match(line)
        if m_name:
            pending_name = m_name.group(1)
            continue
        m_rub = _RUBRIC_RE.match(line)
        if m_rub:
            pending_rubric.append(m_rub.group(1))
            continue
        if _QSTART_RE.search(line):
            q += 1
            out[q] = (pending_name, "\n".join(pending_rubric))
            pending_name = ""
            pending_rubric = []
    return out


def parse_outline_from_tex(tex_content: str) -> list[OutlineRow]:
    body = tex_content.split("\\begin{document}", 1)[-1]
    # Split at every \item, then REGROUP: a question starts at a fragment that
    # carries a \textit{(N pts)} marker; fragments without one (the (a)/(b)
    # choices and the trailing \textbf{Answer:} reveal) belong to the current
    # question and are reattached, so MC answers are not lost.
    frags = re.split(r"\n\s*\\item\b", body)
    blocks = []
    cur = None
    for frag in frags[1:]:
        if _PTS_RE.search(frag):
            if cur is not None:
                blocks.append(cur)
            cur = frag
        elif cur is not None:
            cur += "\n\\item " + frag
    if cur is not None:
        blocks.append(cur)

    annotations = _parse_annotations(tex_content)
    rows = []
    for q, block in enumerate(blocks, start=1):
        m_pts = _PTS_RE.search(block)
        qtype = _classify(block)
        ans_m = _ANS_RE.search(block)
        raw = ans_m.group(1).strip() if ans_m else ""
        # type-aware: FIB keeps all ;-joined blanks; others take first token
        answer = raw if qtype == "fib" else (raw.split()[0].rstrip(".") if raw else "")
        name, rubric = annotations.get(q, ("", ""))
        if not name:
            raise SystemExit(f"exam_pack: question {q} is missing a '% name:' annotation")
        if not rubric:
            if qtype in ("fib", "code"):
                raise SystemExit(
                    f"exam_pack: missing rubric annotation on {qtype} question {q}"
                )
            rubric = f"Correct = {answer} ({int(m_pts.group(1))} pts, all-or-nothing)."
        rows.append(OutlineRow(q_num=q, points=int(m_pts.group(1)), type=qtype,
                               answer=answer, name=name, rubric=rubric))
    return rows


def _write_outline_csv(form_id: str, outline, gs_dir: Path) -> Path:
    out = gs_dir / f"{form_id}_outline.csv"
    with out.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["q_num", "points", "type", "answer"])
        for r in outline:
            w.writerow([r.q_num, r.points, r.type, r.answer])
    return out


def emit_bubble_products(form_id, outline, gs_dir):
    gs_dir.mkdir(parents=True, exist_ok=True)
    key = gs_dir / f"{form_id}_bubble_key.csv"
    non_mc = [r.q_num for r in outline if r.type != "mc"]
    with key.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["version", "q_num", "answer", "points"])
        for r in outline:
            w.writerow([form_id, r.q_num, r.answer, r.points])
    if non_mc:
        sys.stderr.write(
            f"exam_pack: warning — bubble mode: questions {non_mc} are non-MC "
            f"and will not autograde on a bubble sheet\n"
        )
    return [key, _write_outline_csv(form_id, outline, gs_dir)]


def emit_gradescope_roster(roster_path, gs_dir):
    gs_dir.mkdir(parents=True, exist_ok=True)
    out = gs_dir / "gradescope_roster.csv"
    src = list(csv.DictReader(roster_path.open()))
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["First Name", "Last Name", "SID", "Email"])
        for r in src:
            name = (r.get("name") or "").strip()
            sid = (r.get("student_id") or "").strip()
            parts = name.split()
            first = " ".join(parts[:-1]) if len(parts) > 1 else name
            last = parts[-1] if len(parts) > 1 else ""
            w.writerow([first, last, sid, ""])  # Email intentionally blank — see README caveat
    return out


def emit_region_products(form_id, blank_pdf, key_pdf, outline, gs_dir):
    gs_dir.mkdir(parents=True, exist_ok=True)
    template = gs_dir / f"{form_id}_template.pdf"
    answer_key = gs_dir / f"{form_id}_answer_key.pdf"
    shutil.copyfile(blank_pdf, template)   # blank, un-serialized form = Gradescope "negative"
    shutil.copyfile(key_pdf, answer_key)
    outline_csv = _write_outline_csv(form_id, outline, gs_dir)
    return [template, answer_key, outline_csv]


def _pdf_page_count(pdf_path: Path) -> int:
    """Page count via pdfinfo; 0 if unavailable (note still renders)."""
    try:
        out = subprocess.run(["pdfinfo", str(pdf_path)], capture_output=True,
                             text=True, check=True).stdout
    except (FileNotFoundError, subprocess.CalledProcessError):
        return 0
    for line in out.splitlines():
        if line.startswith("Pages:"):
            return int(line.split()[1])
    return 0


def _course_tag(course: str) -> str:
    return course.strip().lower().replace(" ", "-")


def _grading_note_table(rows) -> str:
    head = "| Q | Name | Pts | Type | Answer | Rubric |\n| -: | --- | -: | --- | --- | --- |"
    body = "\n".join(
        f"| {r.q_num} | {r.name} | {r.points} | {r.type} | {r.answer} | "
        f"{r.rubric.replace(chr(10), ' ')} |"
        for r in rows
    )
    return head + "\n" + body


def emit_grading_note(manifest, per_form_outline, per_form_pages, exam_root) -> Path:
    exam_root = Path(exam_root)
    out = exam_root / "GRADING_NOTE.md"
    forms = [f.id for f in manifest.forms]
    total_pts = sum(r.points for r in next(iter(per_form_outline.values())))
    nq = sum(len(v) for v in per_form_outline.values())
    pages = per_form_pages.get(forms[0], 0)
    tag = _course_tag(manifest.course)

    fm = (
        "---\n"
        f"type: grading-note\n"
        f"tags: [teaching, {tag}, exam, gradescope, answer-key, internal]\n"
        "visibility: private\n"
        "icon: LiClipboardCheck\n"
        "iconColor: var(--color-red)\n"
        "---\n"
    )
    parts = [
        fm,
        f"# {manifest.exam} — Gradescope Grading Note ({manifest.course} {manifest.term})\n",
        "> [!warning] Internal — answer key\n"
        "> Grader/ISA only. Never student-facing. Serials/register are grader "
        "infra (see [[project_exam_serial_internal_only]]).\n",
        f"{total_pts} pts · {nq} questions · {len(forms)} forms · {pages}/exam\n",
        "## Gradescope setup\n"
        "1. Two assignments — one per form — linked as a **Version Set**.\n"
        "2. Upload `gradescope/<form>_template.pdf` (the BLANK form) as each template.\n"
        "3. Build the outline: one region per question, points from the table.\n"
        "4. Enter the key in-UI (Gradescope imports nothing); keep "
        "`gradescope/<form>_answer_key.pdf` open.\n"
        f"5. Upload each form's scanned stack to its own version; length = {pages} pages.\n",
    ]
    for fid in forms:
        parts.append(f"## Form {fid}\n" + _grading_note_table(per_form_outline[fid]) + "\n")
    parts.append(
        "## Appeals\n"
        "Each paper's footer `Serial · ID` resolves to one student + form via "
        "`reg-exam-verify --register build/register.csv --dir build/`.\n"
    )
    out.write_text("\n".join(parts), encoding="utf-8")
    return out


def _read_names(roster_path: Path) -> list[str]:
    rows = list(csv.DictReader(roster_path.open()))
    return [(r.get("name") or "").strip() for r in rows if (r.get("name") or "").strip()]


def _student_id_by_name(roster_path: Path) -> dict[str, str]:
    """Map roster name -> student_id (empty string when the column is absent)."""
    rows = list(csv.DictReader(roster_path.open()))
    out: dict[str, str] = {}
    for r in rows:
        name = (r.get("name") or "").strip()
        if name:
            out[name] = (r.get("student_id") or "").strip()
    return out


def run(manifest, workdir):
    workdir = Path(workdir).resolve()
    build_dir = workdir / "build"
    build_dir.mkdir(parents=True, exist_ok=True)

    assignment = {}
    sid_by_name: dict[str, str] = {}
    if manifest.individualized:
        sid_by_name = _student_id_by_name(manifest.roster)
        if len(manifest.forms) > 1:
            names = _read_names(manifest.roster)
            assignment = assign_forms(
                names, [f.id for f in manifest.forms], manifest.assign, manifest.assign_seed
            )

    register_rows = []
    student_pdf_count = 0
    blank_pdfs, key_pdfs = {}, {}

    for form in manifest.forms:
        # NOTE: if a pdflatex build fails mid-loop, build/ is left partially
        # populated. Builds are idempotent and pdflatex fails loudly, so the
        # fix is to re-run after correcting the source — no rollback needed.
        form_tex = build_dir / f"{form.id}.tex"
        shutil.copyfile(form.source, form_tex)

        # (a) blank variant build -> template + key
        build_variant(ExamBuildConfig(source=form_tex))
        blank_pdfs[form.id] = build_dir / f"{form.id}.pdf"
        key_pdfs[form.id] = build_dir / f"{form.id}_key.pdf"

        # (b) individualized -> per-student copies for this form's sub-roster
        if manifest.individualized:
            if len(manifest.forms) > 1:
                sub = [n for n, fid in assignment.items() if fid == form.id]
            else:
                sub = _read_names(manifest.roster)
            sub_roster = build_dir / f"_sub_{form.id}.csv"
            with sub_roster.open("w", newline="") as f:
                w = csv.writer(f); w.writerow(["name", "student_id"])
                for n in sorted(sub):
                    w.writerow([n, sid_by_name.get(n, "")])
            build_roster(ExamBuildConfig(source=form_tex, roster=sub_roster, combined=True))
            for srow in csv.DictReader((build_dir / f"{form.id}_serials.csv").open()):
                srow["form"] = form.id
                register_rows.append(srow)
                student_pdf_count += 1
            sub_roster.unlink(missing_ok=True)

    register_csv = None
    if manifest.individualized:
        register_csv = build_dir / "register.csv"
        fields = ["name", "form", "canonical_name", "source_serial", "student_serial", "output_pdf"]
        with register_csv.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
            register_rows.sort(key=lambda r: r.get("canonical_name", ""))
            w.writeheader()
            w.writerows(register_rows)

    gs_dir = None
    grading_note = None
    if manifest.gradescope != "none":
        gs_dir = workdir / "gradescope"
        gs_dir.mkdir(parents=True, exist_ok=True)
        per_form_outline = {}
        per_form_pages = {}
        for form in manifest.forms:
            outline = parse_outline_from_tex(form.source.read_text())
            per_form_outline[form.id] = outline
            per_form_pages[form.id] = _pdf_page_count(blank_pdfs[form.id])
            if manifest.gradescope == "region":
                emit_region_products(form.id, blank_pdfs[form.id], key_pdfs[form.id], outline, gs_dir)
            elif manifest.gradescope == "bubble":
                emit_bubble_products(form.id, outline, gs_dir)
        if manifest.roster is not None:
            emit_gradescope_roster(manifest.roster, gs_dir)
        grading_note = emit_grading_note(manifest, per_form_outline, per_form_pages, workdir)

    return PackResult(
        forms=[f.id for f in manifest.forms], build_dir=build_dir,
        gradescope_dir=gs_dir, register_csv=register_csv,
        student_pdf_count=student_pdf_count, grading_note=grading_note,
    )
