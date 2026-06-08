"""Tests for lectern.exam_verify — round-trip a built PDF and verify the printed ID."""
import csv
import shutil
import subprocess
from pathlib import Path

import pytest

from lectern.exam_build import ExamBuildConfig, build_roster, build_variant
from lectern.exam_verify import (
    extract_footer_serials,
    verify_pdf,
    verify_register,
)

FIX = Path(__file__).parent / "fixtures" / "exam_archive"


def _has_pdflatex() -> bool:
    try:
        subprocess.run(["pdflatex", "--version"], capture_output=True, check=True)
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False


pytestmark = pytest.mark.skipif(not _has_pdflatex(), reason="pdflatex not installed")


def _build_one_student(tmp_path: Path, name: str = "Jane Smith") -> Path:
    """Build a per-student PDF for a single-row roster, return its path."""
    tex = tmp_path / "exam.tex"
    shutil.copy(FIX / "dummy_exam.tex", tex)
    roster = tmp_path / "roster.csv"
    roster.write_text(f"name\n{name}\n")
    build_roster(ExamBuildConfig(source=tex, roster=roster))
    pdfs = [
        p
        for p in tmp_path.glob("exam_*.pdf")
        if "_key" not in p.name and p.name != "exam_combined.pdf"
    ]
    assert len(pdfs) == 1, f"expected 1 per-student PDF, found {pdfs}"
    return pdfs[0]


def test_extract_footer_serials_per_student(tmp_path):
    pdf = _build_one_student(tmp_path)
    serials = extract_footer_serials(pdf)
    assert len(serials["source"]) == 8
    assert len(serials["student"]) == 8
    assert all(c in "0123456789ABCDEF" for c in serials["source"])
    assert all(c in "0123456789ABCDEF" for c in serials["student"])


def test_extract_footer_serials_variant_only(tmp_path):
    tex = tmp_path / "exam.tex"
    shutil.copy(FIX / "dummy_exam.tex", tex)
    build_variant(ExamBuildConfig(source=tex))
    pdf = tmp_path / "exam.pdf"
    serials = extract_footer_serials(pdf)
    assert len(serials["source"]) == 8
    assert serials["student"] is None


def test_verify_match(tmp_path):
    pdf = _build_one_student(tmp_path, name="Jane Smith")
    r = verify_pdf(pdf, student_name="Jane Smith")
    assert r.ok is True
    assert r.computed_student == r.printed_student
    assert r.student_name == "Jane Smith"


def test_verify_mismatch(tmp_path):
    pdf = _build_one_student(tmp_path, name="Jane Smith")
    r = verify_pdf(pdf, student_name="John Doe")
    assert r.ok is False
    assert r.computed_student != r.printed_student


def test_verify_canonical_name_insensitivity(tmp_path):
    """canonical_name normalization: case + accents + whitespace shouldn't matter."""
    pdf = _build_one_student(tmp_path, name="María José")
    r = verify_pdf(pdf, student_name="  maria jose  ")
    assert r.ok is True


def test_verify_register_bulk(tmp_path):
    tex = tmp_path / "exam.tex"
    shutil.copy(FIX / "dummy_exam.tex", tex)
    roster = tmp_path / "roster.csv"
    roster.write_text("name\nJane Smith\nJohn Doe\nMaría López\n")
    build_roster(ExamBuildConfig(source=tex, roster=roster))
    register = tmp_path / "exam_serials.csv"
    ok, fail, issues = verify_register(register, tmp_path)
    assert ok == 3
    assert fail == 0
    assert issues == []


def test_verify_register_detects_name_swap(tmp_path):
    """Editing the register's name column should be caught by the verifier."""
    tex = tmp_path / "exam.tex"
    shutil.copy(FIX / "dummy_exam.tex", tex)
    roster = tmp_path / "roster.csv"
    roster.write_text("name\nJane Smith\nJohn Doe\n")
    build_roster(ExamBuildConfig(source=tex, roster=roster))
    register = tmp_path / "exam_serials.csv"
    rows = list(csv.DictReader(register.open()))
    # Swap names between the two rows — PDFs still bind to their original hashes,
    # so verify_pdf(pdf_for_Jane, "John Doe") and vice versa should both fail.
    rows[0]["name"], rows[1]["name"] = rows[1]["name"], rows[0]["name"]
    with register.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    ok, fail, issues = verify_register(register, tmp_path)
    assert ok == 0
    assert fail == 2
    assert len(issues) == 2
    assert all("mismatch" in i for i in issues)
