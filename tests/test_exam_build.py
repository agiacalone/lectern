"""Tests for lectern.exam_build — variant + roster + combined exam compilation."""
import csv
import shutil
import subprocess
from pathlib import Path

import pytest

from lectern.exam_build import (
    BuildResult,
    ExamBuildConfig,
    build_roster,
    build_variant,
)

FIX = Path(__file__).parent / "fixtures" / "exam_archive"


def _has_pdflatex() -> bool:
    try:
        subprocess.run(["pdflatex", "--version"], capture_output=True, check=True)
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False


def _has_pdf_concat() -> bool:
    for tool in ("pdfunite", "qpdf"):
        try:
            subprocess.run([tool, "--version"], capture_output=True, check=True)
            return True
        except (FileNotFoundError, subprocess.CalledProcessError):
            continue
    return False


pytestmark = pytest.mark.skipif(not _has_pdflatex(), reason="pdflatex not installed")


def test_build_variant_smoke(tmp_path):
    """Variant-only build produces .pdf + _key.pdf with matching source serial."""
    tex = tmp_path / "exam.tex"
    shutil.copy(FIX / "dummy_exam.tex", tex)
    cfg = ExamBuildConfig(source=tex)
    result = build_variant(cfg)
    assert (tmp_path / "exam.pdf").exists()
    assert (tmp_path / "exam_key.pdf").exists()
    assert len(result.source_serial) == 8
    assert not (tmp_path / "exam.aux").exists()
    assert not (tmp_path / "exam.log").exists()


def test_build_roster_produces_n_pdfs(tmp_path):
    """--roster mode produces N PDFs + register CSV + 1 key."""
    tex = tmp_path / "exam.tex"
    shutil.copy(FIX / "dummy_exam.tex", tex)
    roster = tmp_path / "roster.csv"
    roster.write_text("name\nJane Smith\nJohn Doe\nMaría López\n")
    cfg = ExamBuildConfig(source=tex, roster=roster)
    result = build_roster(cfg)
    student_pdfs = sorted(
        p for p in tmp_path.glob("exam_*.pdf") if "_key" not in p.name
    )
    assert len(student_pdfs) == 3
    assert (tmp_path / "exam_key.pdf").exists()
    register = tmp_path / "exam_serials.csv"
    assert register.exists()
    rows = list(csv.DictReader(register.open()))
    assert len(rows) == 3
    assert set(rows[0].keys()) == {
        "name",
        "canonical_name",
        "source_serial",
        "student_serial",
        "output_pdf",
    }
    for r in rows:
        assert (tmp_path / r["output_pdf"]).exists()


def test_build_roster_prefills_student_id(tmp_path):
    """A roster with a student_id column prints the name AND the ID on the page.

    Name sits on the NAME line; the 9-digit ID on the STUDENT ID# line. The DATE
    line is intentionally left blank for the student to fill in.
    """
    import pdfplumber

    tex = tmp_path / "exam.tex"
    shutil.copy(FIX / "dummy_exam.tex", tex)
    roster = tmp_path / "roster.csv"
    roster.write_text("name,student_id\nJane Smith,040100021\n")
    cfg = ExamBuildConfig(source=tex, roster=roster)
    build_roster(cfg)
    with (tmp_path / "exam_serials.csv").open() as f:
        row = next(csv.DictReader(f))
    student_pdf = tmp_path / row["output_pdf"]
    with pdfplumber.open(student_pdf) as f:
        text = f.pages[0].extract_text() or ""
    assert "Jane Smith" in text, f"name not on page: {text!r}"
    assert "040100021" in text, f"student_id not on page: {text!r}"
    assert "VERIFY YOUR NAME AND STUDENT ID" in text


def test_build_roster_without_student_id_column_is_blank(tmp_path):
    """No student_id column => name still prints, but no ID; build still succeeds."""
    import pdfplumber

    tex = tmp_path / "exam.tex"
    shutil.copy(FIX / "dummy_exam.tex", tex)
    roster = tmp_path / "roster.csv"
    roster.write_text("name\nJane Smith\n")
    cfg = ExamBuildConfig(source=tex, roster=roster)
    build_roster(cfg)
    with (tmp_path / "exam_serials.csv").open() as f:
        row = next(csv.DictReader(f))
    with pdfplumber.open(tmp_path / row["output_pdf"]) as f:
        text = f.pages[0].extract_text() or ""
    assert "Jane Smith" in text


def test_build_roster_serial_deterministic(tmp_path):
    """Same source + same name → same student serial across runs.

    Also verifies the canonical source_serial in the register CSV equals the
    Serial printed in the PDF footer (builder-injected, see Option 2 fix).
    """
    import re

    import pdfplumber

    tex = tmp_path / "exam.tex"
    shutil.copy(FIX / "dummy_exam.tex", tex)
    roster = tmp_path / "roster.csv"
    roster.write_text("name\nJane Smith\n")
    cfg = ExamBuildConfig(source=tex, roster=roster)
    build_roster(cfg)
    with (tmp_path / "exam_serials.csv").open() as f:
        row1 = next(csv.DictReader(f))
    ssn1 = row1["student_serial"]
    canonical_src = row1["source_serial"]

    # PDF footer Serial must equal register's source_serial column.
    student_pdf = tmp_path / row1["output_pdf"]
    with pdfplumber.open(student_pdf) as f:
        text = f.pages[0].extract_text() or ""
    m = re.search(r"Serial\s+([A-F0-9]{8})", text)
    assert m, f"no Serial in footer: {text!r}"
    assert m.group(1) == canonical_src, (
        f"PDF footer Serial {m.group(1)} ≠ register source_serial {canonical_src}"
    )

    for p in list(tmp_path.glob("exam_*.pdf")) + [
        tmp_path / "exam_key.pdf",
        tmp_path / "exam_serials.csv",
    ]:
        p.unlink(missing_ok=True)
    build_roster(cfg)
    with (tmp_path / "exam_serials.csv").open() as f:
        ssn2 = next(csv.DictReader(f))["student_serial"]
    assert ssn1 == ssn2


def test_build_variant_printed_serial_matches_canonical(tmp_path):
    """Builder injects canonical source_serial — printed footer matches
    source_serial_from_tex(content) by construction.

    This pins the invariant that pa-exam-verify relies on: the value printed
    in the PDF footer must equal source_serial_from_tex(content). Without
    builder injection, the printed Serial would be whatever placeholder the
    .tex author hand-wrote, breaking the verification loop.
    """
    import re

    import pdfplumber

    from lectern.exam_serial import source_serial_from_tex

    tex = tmp_path / "exam.tex"
    shutil.copy(FIX / "dummy_exam.tex", tex)
    expected = source_serial_from_tex(tex.read_text())
    cfg = ExamBuildConfig(source=tex)
    build_variant(cfg)
    pdf = tmp_path / "exam.pdf"
    with pdfplumber.open(pdf) as f:
        text = f.pages[0].extract_text() or ""
    m = re.search(r"Serial\s+([A-F0-9]{8})", text)
    assert m, f"no Serial in footer: {text!r}"
    assert m.group(1) == expected, (
        f"printed Serial {m.group(1)} ≠ canonical {expected}"
    )


def test_build_roster_missing_macros_fails(tmp_path):
    """If exam .tex lacks per-student macros, --roster fails loudly."""
    tex = tmp_path / "exam.tex"
    src = (FIX / "dummy_exam.tex").read_text()
    src = src.replace(
        r"\@ifundefined{studentname}{\def\studentname{}}{}",
        "% removed studentname default",
    )
    src = src.replace(
        r"\@ifundefined{studentserial}{\def\studentserial{}}{}",
        "% removed studentserial default",
    )
    tex.write_text(src)
    roster = tmp_path / "roster.csv"
    roster.write_text("name\nJane Smith\n")
    cfg = ExamBuildConfig(source=tex, roster=roster)
    with pytest.raises(SystemExit, match="lacks per-student macros"):
        build_roster(cfg)


def test_build_roster_empty_name_fails(tmp_path):
    tex = tmp_path / "exam.tex"
    shutil.copy(FIX / "dummy_exam.tex", tex)
    roster = tmp_path / "roster.csv"
    roster.write_text("name\nJane Smith\n\nJohn Doe\n")
    cfg = ExamBuildConfig(source=tex, roster=roster)
    with pytest.raises(SystemExit, match="empty name"):
        build_roster(cfg)


def test_build_roster_missing_name_column_fails(tmp_path):
    tex = tmp_path / "exam.tex"
    shutil.copy(FIX / "dummy_exam.tex", tex)
    roster = tmp_path / "roster.csv"
    roster.write_text("student_id,whatever\n111,Jane\n")
    cfg = ExamBuildConfig(source=tex, roster=roster)
    with pytest.raises(SystemExit, match="missing 'name' column"):
        build_roster(cfg)


@pytest.mark.skipif(not _has_pdf_concat(), reason="pdfunite/qpdf not installed")
def test_build_roster_combined(tmp_path):
    """--combined produces a single concatenated PDF sorted by canonical name."""
    tex = tmp_path / "exam.tex"
    shutil.copy(FIX / "dummy_exam.tex", tex)
    roster = tmp_path / "roster.csv"
    roster.write_text("name\nZara Anderson\nAaron Baker\nMary Carter\n")
    cfg = ExamBuildConfig(source=tex, roster=roster, combined=True)
    result = build_roster(cfg)
    combined = tmp_path / "exam_combined.pdf"
    assert combined.exists()
    assert result.combined_pdf == combined
    individuals = [
        p
        for p in tmp_path.glob("exam_*.pdf")
        if p.name != "exam_combined.pdf" and "_key" not in p.name
    ]
    assert len(individuals) == 3
