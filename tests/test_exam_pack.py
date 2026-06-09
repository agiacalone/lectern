"""Tests for lectern.exam_pack — multi-form + Gradescope orchestration."""
import csv
import shutil
import subprocess
from pathlib import Path

import pytest

from lectern.exam_pack import (
    ExamManifest, FormSpec, OutlineRow, PackResult,
    assign_forms, emit_bubble_products, emit_gradescope_roster,
    emit_grading_note, emit_region_products, load_manifest,
    parse_outline_from_tex, run,
)

FIX = Path(__file__).parent / "fixtures" / "exam_pack"


def _has_pdflatex() -> bool:
    try:
        subprocess.run(["pdflatex", "--version"], capture_output=True, check=True)
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False


needs_latex = pytest.mark.skipif(not _has_pdflatex(), reason="pdflatex not installed")


def test_load_manifest_single():
    m = load_manifest(FIX / "manifest_single.yaml")
    assert m.course == "CECS 378"
    assert [f.id for f in m.forms] == ["A"]
    assert m.forms[0].source == (FIX / "form_a.tex")   # resolved relative to manifest
    assert m.individualized is False
    assert m.gradescope == "none"


def test_load_manifest_ab_resolves_roster_and_sources():
    m = load_manifest(FIX / "manifest_ab.yaml")
    assert [f.id for f in m.forms] == ["A", "B"]
    assert m.individualized is True
    assert m.roster == (FIX / "roster4.csv")
    assert m.assign == "alternating"
    assert m.gradescope == "region"


def test_load_manifest_rejects_duplicate_form_ids():
    with pytest.raises(SystemExit, match="duplicate form id"):
        load_manifest(FIX / "manifest_bad_dupe.yaml")


def test_load_manifest_individualized_requires_roster(tmp_path):
    (tmp_path / "f.tex").write_text("x")
    man = tmp_path / "m.yaml"
    man.write_text(
        "course: C\nterm: t\nexam: E\nforms:\n  - {id: A, source: f.tex}\n"
        "individualized: true\n"
    )
    with pytest.raises(SystemExit, match="individualized.*roster"):
        load_manifest(man)


def test_load_manifest_missing_source(tmp_path):
    man = tmp_path / "m.yaml"
    man.write_text("course: C\nterm: t\nexam: E\nforms:\n  - {id: A, source: nope.tex}\n")
    with pytest.raises(SystemExit, match="source not found"):
        load_manifest(man)


def test_load_manifest_bad_gradescope(tmp_path):
    (tmp_path / "f.tex").write_text("x")
    man = tmp_path / "m.yaml"
    man.write_text(
        "course: C\nterm: t\nexam: E\nforms:\n  - {id: A, source: f.tex}\n"
        "gradescope: pdf\n"
    )
    with pytest.raises(SystemExit, match="gradescope must be"):
        load_manifest(man)


def test_load_manifest_seeded_random_requires_seed(tmp_path):
    (tmp_path / "f.tex").write_text("x")
    (tmp_path / "r.csv").write_text("name\nA B\n")
    man = tmp_path / "m.yaml"
    man.write_text(
        "course: C\nterm: t\nexam: E\nforms:\n  - {id: A, source: f.tex}\n"
        "individualized: true\nroster: r.csv\nassign: seeded-random\n"
    )
    with pytest.raises(SystemExit, match="seeded-random requires assign_seed"):
        load_manifest(man)


NAMES = ["Ada Lovelace", "Alan Turing", "Grace Hopper", "Maria Goeppert Mayer"]


def test_assign_alternating_balanced_and_sorted():
    out = assign_forms(NAMES, ["A", "B"], "alternating", None)
    # round-robin over canonical-name-sorted order
    assert sorted(out) == sorted(NAMES)
    counts = {"A": 0, "B": 0}
    for f in out.values():
        counts[f] += 1
    assert abs(counts["A"] - counts["B"]) <= 1


def test_assign_alternating_is_deterministic():
    a = assign_forms(NAMES, ["A", "B"], "alternating", None)
    b = assign_forms(list(reversed(NAMES)), ["A", "B"], "alternating", None)
    assert a == b  # input order must not matter (sorted internally)


def test_assign_seeded_random_same_seed_same_split():
    a = assign_forms(NAMES, ["A", "B"], "seeded-random", "seed-1")
    b = assign_forms(NAMES, ["A", "B"], "seeded-random", "seed-1")
    c = assign_forms(NAMES, ["A", "B"], "seeded-random", "seed-0")
    assert a == b
    assert a != c or len(set(a.values())) == 1  # different seed => (very likely) different split


def test_assign_every_form_gives_all_forms_to_all():
    out = assign_forms(NAMES, ["A", "B"], "every-form", None)
    # every-form is represented as name -> sorted list of all form ids
    assert all(out[n] == ["A", "B"] for n in NAMES)


def test_parse_outline_extracts_points_type_answer():
    rows = parse_outline_from_tex((FIX / "form_a.tex").read_text())
    assert rows[0].q_num == 1
    assert rows[0].points == 2
    assert rows[0].type == "mc"
    assert rows[0].answer == "a"
    assert rows[1].type == "tf"
    assert rows[1].answer.lower() == "true"


def test_parse_outline_total_points():
    rows = parse_outline_from_tex((FIX / "form_a.tex").read_text())
    assert sum(r.points for r in rows) == 3


def test_parse_outline_mixed_types():
    rows = parse_outline_from_tex((FIX / "outline_sample.tex").read_text())
    assert [r.type for r in rows] == ["mc", "tf", "code", "fib"]
    assert [r.points for r in rows] == [2, 1, 2, 2]
    assert [r.q_num for r in rows] == [1, 2, 3, 4]
    assert rows[0].answer == "a"
    assert rows[1].answer.lower().startswith("false")
    assert rows[3].type == "fib"
    assert sum(r.points for r in rows) == 7


def test_parse_outline_captures_name_rubric_and_full_fib_answer():
    tex = (FIX / "annotated_sample.tex").read_text()
    rows = parse_outline_from_tex(tex)
    assert [r.q_num for r in rows] == [1, 2, 3, 4]
    # names from % name:
    assert rows[0].name == "CIA — confidentiality"
    assert rows[3].name == "FIB — Shannon goals"
    # authored rubric where present
    assert rows[0].rubric == "Correct = (a). 2 pts all-or-nothing."
    assert rows[3].rubric == "1 pt per blank."
    # type-aware answers
    assert rows[0].type == "mc" and rows[0].answer == "a"
    assert rows[1].type == "tf" and rows[1].answer == "True"
    assert rows[2].type == "code" and rows[2].answer == "False"
    # FIB keeps BOTH blanks (regression: used to truncate to "confusion;")
    assert rows[3].type == "fib" and rows[3].answer == "confusion; diffusion"


def test_missing_name_errors_with_question_number(tmp_path):
    tex = (
        "\\begin{document}\\begin{enumerate}\n"
        "\\item \\textit{(2 pts)}~No name here.\n"
        "  \\ifanswers \\textbf{Answer:} a \\fi\n"
        "\\end{enumerate}\\end{document}"
    )
    with pytest.raises(SystemExit, match="question 1"):
        parse_outline_from_tex(tex)


def test_missing_rubric_on_fib_errors(tmp_path):
    tex = (
        "\\begin{document}\\begin{enumerate}\n"
        "% name: FIB no rubric\n"
        "\\item \\textit{(2 pts)}~\\textsc{Fill in the blank.}~x \\rule[-2pt]{2cm}{0.4pt}.\n"
        "  \\ifanswers \\textbf{Answer:} foo \\fi\n"
        "\\end{enumerate}\\end{document}"
    )
    with pytest.raises(SystemExit, match="rubric.*question 1"):
        parse_outline_from_tex(tex)


def test_mc_default_rubric_when_unannotated():
    tex = (
        "\\begin{document}\\begin{enumerate}\n"
        "% name: MC default\n"
        "\\item \\textit{(3 pts)}~pick \\correctchoice{x}\n"
        "  \\ifanswers \\textbf{Answer:} b \\fi\n"
        "\\end{enumerate}\\end{document}"
    )
    rows = parse_outline_from_tex(tex)
    assert rows[0].rubric == "Correct = b (3 pts, all-or-nothing)."


OUTLINE = [
    OutlineRow(1, 2, "mc", "a"),
    OutlineRow(2, 1, "tf", "True"),
    OutlineRow(3, 2, "fib", "confusion; diffusion"),
]


def test_emit_bubble_products_schema(tmp_path):
    paths = emit_bubble_products("A", OUTLINE, tmp_path)
    key = tmp_path / "A_bubble_key.csv"
    assert key in paths and key.exists()
    rows = list(csv.DictReader(key.open()))
    assert rows[0] == {"version": "A", "q_num": "1", "answer": "a", "points": "2"}
    assert len(rows) == 3


def test_emit_gradescope_roster_columns(tmp_path):
    roster = tmp_path / "roster.csv"
    roster.write_text("name,student_id\nAda Lovelace,001\nAlan M Turing,002\n")
    out = emit_gradescope_roster(roster, tmp_path)
    rows = list(csv.DictReader(out.open()))
    assert list(rows[0].keys()) == ["First Name", "Last Name", "SID", "Email"]
    assert rows[0]["First Name"] == "Ada"
    assert rows[0]["Last Name"] == "Lovelace"
    assert rows[1]["First Name"] == "Alan M"     # all-but-last token = first/middle
    assert rows[1]["Last Name"] == "Turing"
    assert rows[0]["SID"] == "001"
    assert rows[0]["Email"] == ""                # email not carried — left blank


def test_emit_grading_note_structure(tmp_path):
    a = [
        OutlineRow(1, 2, "mc", "a", "CIA — confidentiality", "Correct = a (2 pts)."),
        OutlineRow(2, 2, "fib", "confusion; diffusion", "FIB — Shannon", "1 pt/blank."),
    ]
    b = [OutlineRow(1, 2, "mc", "c", "CIA — availability", "Correct = c (2 pts).")]
    man = ExamManifest(course="CECS 378", term="su26", exam="Exam 1",
                       forms=[FormSpec("A", tmp_path / "A.tex"),
                              FormSpec("B", tmp_path / "B.tex")],
                       gradescope="region", points=4)
    note = emit_grading_note(
        man, {"A": a, "B": b}, {"A": 4, "B": 4}, tmp_path
    )
    assert note == tmp_path / "GRADING_NOTE.md"
    text = note.read_text()
    assert "type: grading-note" in text
    assert "tags: [teaching, cecs-378, exam, gradescope, answer-key, internal]" in text
    assert "## Form A" in text and "## Form B" in text
    assert "CIA — confidentiality" in text
    assert "confusion; diffusion" in text          # FIB full answer in table
    assert "4 pts · 3 questions · 2 forms · 4/exam" in text
    assert "length = 4 pages" in text
    assert "[!warning] Internal" in text


def test_emit_region_products_copies_and_outlines(tmp_path):
    blank = tmp_path / "A.pdf"; blank.write_bytes(b"%PDF-1.4 blank")
    key = tmp_path / "A_key.pdf"; key.write_bytes(b"%PDF-1.4 key")
    gs = tmp_path / "gs"
    paths = emit_region_products("A", blank, key, OUTLINE, gs)
    assert (gs / "A_template.pdf").read_bytes() == b"%PDF-1.4 blank"
    assert (gs / "A_answer_key.pdf").read_bytes() == b"%PDF-1.4 key"
    assert (gs / "A_outline.csv").exists()
    assert {p.name for p in paths} == {"A_template.pdf", "A_answer_key.pdf", "A_outline.csv"}


def _manifest(tmp_path, **over):
    """Copy fixtures into tmp and write a manifest; return its path."""
    for f in ("form_a.tex", "form_b.tex", "roster4.csv"):
        shutil.copy(FIX / f, tmp_path / f)
    lines = ["course: CECS 378", "term: su26", "exam: Exam 1", "forms:",
             "  - {id: A, source: form_a.tex}"]
    if over.get("two_forms"):
        lines.append("  - {id: B, source: form_b.tex}")
    lines.append(f"individualized: {str(over.get('individualized', False)).lower()}")
    if over.get("individualized"):
        lines.append("roster: roster4.csv")
        lines.append(f"assign: {over.get('assign', 'alternating')}")
    lines.append(f"gradescope: {over.get('gradescope', 'none')}")
    man = tmp_path / "exam.build.yaml"
    man.write_text("\n".join(lines) + "\n")
    return man


@needs_latex
def test_run_emits_grading_note(tmp_path):
    shutil.copytree(FIX, tmp_path / "fix")
    fixd = tmp_path / "fix"
    m = load_manifest(fixd / "manifest_ab.yaml")
    result = run(m, fixd)
    note = fixd / "GRADING_NOTE.md"
    assert note.exists()
    assert result.grading_note == note
    text = note.read_text()
    assert "## Form A" in text and "## Form B" in text
    assert "type: grading-note" in text


@needs_latex
def test_run_single_plain(tmp_path):
    m = load_manifest(_manifest(tmp_path))
    res = run(m, tmp_path)
    assert (res.build_dir / "A.pdf").exists()
    assert (res.build_dir / "A_key.pdf").exists()
    assert res.register_csv is None
    assert res.student_pdf_count == 0


@needs_latex
def test_run_single_individualized_register(tmp_path):
    m = load_manifest(_manifest(tmp_path, individualized=True))
    res = run(m, tmp_path)
    rows = list(csv.DictReader(res.register_csv.open()))
    assert len(rows) == 4
    assert {r["form"] for r in rows} == {"A"}
    assert res.student_pdf_count == 4


@needs_latex
def test_run_individualized_prefills_student_id(tmp_path):
    """Pack mode threads the roster's student_id onto each student's exam."""
    import pdfplumber

    m = load_manifest(_manifest(tmp_path, individualized=True))
    res = run(m, tmp_path)
    rows = list(csv.DictReader(res.register_csv.open()))
    ada = next(r for r in rows if r["name"] == "Ada Lovelace")
    with pdfplumber.open(res.build_dir / ada["output_pdf"]) as f:
        text = f.pages[0].extract_text() or ""
    assert "Ada Lovelace" in text, f"name missing: {text!r}"
    assert "000000001" in text, f"student_id missing: {text!r}"


@needs_latex
def test_run_ab_individualized_splits_roster(tmp_path):
    m = load_manifest(_manifest(tmp_path, two_forms=True, individualized=True))
    res = run(m, tmp_path)
    rows = list(csv.DictReader(res.register_csv.open()))
    assert len(rows) == 4                          # one copy per student
    assert {r["form"] for r in rows} == {"A", "B"} # both forms used
    counts = {"A": 0, "B": 0}
    for r in rows:
        counts[r["form"]] += 1
    assert abs(counts["A"] - counts["B"]) <= 1     # balanced split
    serials = [r["student_serial"] for r in rows]
    assert len(set(serials)) == len(serials)       # serials unique


@needs_latex
def test_run_ab_region_products(tmp_path):
    m = load_manifest(_manifest(tmp_path, two_forms=True, gradescope="region"))
    res = run(m, tmp_path)
    gs = res.gradescope_dir
    for fid in ("A", "B"):
        assert (gs / f"{fid}_template.pdf").exists()
        assert (gs / f"{fid}_answer_key.pdf").exists()
        assert (gs / f"{fid}_outline.csv").exists()


@needs_latex
def test_run_determinism_same_split(tmp_path):
    m = load_manifest(_manifest(tmp_path, two_forms=True, individualized=True))
    r1 = run(m, tmp_path)
    split1 = {row["name"]: row["form"] for row in csv.DictReader(r1.register_csv.open())}
    r2 = run(m, tmp_path)
    split2 = {row["name"]: row["form"] for row in csv.DictReader(r2.register_csv.open())}
    assert split1 == split2


@needs_latex
def test_run_register_sorted_by_canonical_name(tmp_path):
    m = load_manifest(_manifest(tmp_path, two_forms=True, individualized=True))
    res = run(m, tmp_path)
    canon = [row["canonical_name"] for row in csv.DictReader(res.register_csv.open())]
    assert canon == sorted(canon)


@needs_latex
def test_cli_dispatches_yaml_to_pack(tmp_path):
    from lectern.exam_build import main
    for f in ("form_a.tex", "roster4.csv"):
        shutil.copy(FIX / f, tmp_path / f)
    man = tmp_path / "exam.build.yaml"
    man.write_text(
        "course: C\nterm: su26\nexam: E\nforms:\n  - {id: A, source: form_a.tex}\n"
        "individualized: true\nroster: roster4.csv\ngradescope: bubble\n"
    )
    rc = main([str(man)])
    assert rc == 0
    assert (tmp_path / "build" / "register.csv").exists()
    assert (tmp_path / "gradescope" / "A_bubble_key.csv").exists()


@needs_latex
def test_cli_tex_path_unchanged(tmp_path):
    """A .tex source must still hit the legacy variant builder, not pack mode."""
    from lectern.exam_build import main
    shutil.copy(Path(__file__).parent / "fixtures" / "exam_archive" / "dummy_exam.tex",
                tmp_path / "exam.tex")
    rc = main([str(tmp_path / "exam.tex")])
    assert rc == 0
    assert (tmp_path / "exam.pdf").exists()          # legacy output location
    assert not (tmp_path / "build").exists()         # NOT pack mode


@needs_latex
def test_cli_relative_manifest_path(tmp_path, monkeypatch):
    """A relative manifest path must not crash the summary print (regression)."""
    from lectern.exam_build import main
    for f in ("form_a.tex", "roster4.csv"):
        shutil.copy(FIX / f, tmp_path / f)
    (tmp_path / "exam.build.yaml").write_text(
        "course: C\nterm: su26\nexam: E\nforms:\n  - {id: A, source: form_a.tex}\n"
        "individualized: true\nroster: roster4.csv\n"
    )
    monkeypatch.chdir(tmp_path)
    rc = main(["exam.build.yaml"])   # relative path
    assert rc == 0
    assert (tmp_path / "build" / "register.csv").exists()
