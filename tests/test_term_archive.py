"""Tests for pa/term_archive.py — per-section archive bundle orchestrator."""
from __future__ import annotations

import csv
from pathlib import Path

import pytest
import yaml

from lectern.manifest_schema import validate_manifest
from lectern.term_archive import (
    ArchiveConfig,
    build_bundle,
    check_bundle,
    render_readme,
)

FIX = Path(__file__).parent / "fixtures" / "exam_archive"


def test_build_bundle_minimal(tmp_path):
    """Build a bundle with only roster — no grades, no exams, no github."""
    cfg = ArchiveConfig(
        course="CECS 478",
        course_dir="378-478",
        term="sp26",
        section="04",
        vault_root=tmp_path,
        roster_xls=FIX / "roster_478-04_sp26.xls",
    )
    bundle = build_bundle(cfg)
    assert bundle == tmp_path / "classes" / "378-478" / "archives" / "sp26-04"
    assert bundle.exists()
    assert (bundle / "manifest.yaml").exists()
    assert (bundle / "roster.csv").exists()
    assert (bundle / "roster.raw.xls").exists()
    assert (bundle / "README.md").exists()

    manifest = yaml.safe_load((bundle / "manifest.yaml").read_text())
    validate_manifest(manifest)
    assert manifest["course"] == "CECS 478"
    assert manifest["term"] == "sp26"
    assert manifest["section"] == "04"
    assert manifest["headcount"]["enrolled"] == 15
    assert manifest["headcount"]["withdrew"] == 2


def test_build_bundle_with_grades(tmp_path):
    """Roster + Canvas grades → grades.csv joined with W for withdrawn."""
    cfg = ArchiveConfig(
        course="CECS 478",
        course_dir="378-478",
        term="sp26",
        section="04",
        vault_root=tmp_path,
        roster_xls=FIX / "roster_478-04_sp26.xls",
        canvas_grades_csv=FIX / "grades_478-04_sp26.csv",
    )
    bundle = build_bundle(cfg)
    assert (bundle / "grades.csv").exists()
    assert (bundle / "grades.raw.csv").exists()
    assert (bundle / "grades.filtered.csv").exists()
    assert (bundle / "grades.points-possible.json").exists()

    with (bundle / "grades.csv").open() as f:
        rows = list(csv.DictReader(f))
    # 13 enrolled + 2 withdrawn-as-W = 15 rows
    assert len(rows) == 15
    withdrawn_rows = [
        r for r in rows
        if r.get("final_grade") == "W" or r.get("letter_grade") == "W"
    ]
    assert len(withdrawn_rows) == 2


def test_check_bundle_clean(tmp_path):
    """A freshly-built bundle should pass check."""
    cfg = ArchiveConfig(
        course="CECS 478",
        course_dir="378-478",
        term="sp26",
        section="04",
        vault_root=tmp_path,
        roster_xls=FIX / "roster_478-04_sp26.xls",
    )
    bundle = build_bundle(cfg)
    ok, fail, issues = check_bundle(bundle)
    assert fail == 0
    assert issues == []
    assert ok >= 1


def test_check_bundle_detects_missing_file(tmp_path):
    """If a manifest-referenced file is deleted, check_bundle reports it."""
    cfg = ArchiveConfig(
        course="CECS 478",
        course_dir="378-478",
        term="sp26",
        section="04",
        vault_root=tmp_path,
        roster_xls=FIX / "roster_478-04_sp26.xls",
    )
    bundle = build_bundle(cfg)
    (bundle / "roster.csv").unlink()
    ok, fail, issues = check_bundle(bundle)
    assert fail >= 1
    assert any("roster.csv" in i for i in issues)


def test_render_readme(tmp_path):
    cfg = ArchiveConfig(
        course="CECS 478",
        course_dir="378-478",
        term="sp26",
        section="04",
        vault_root=tmp_path,
        roster_xls=FIX / "roster_478-04_sp26.xls",
    )
    bundle = build_bundle(cfg)
    readme = (bundle / "README.md").read_text()
    assert "CECS 478" in readme
    assert "sp26" in readme
    assert "04" in readme.lower() or "§04" in readme
    assert "15" in readme  # enrolled count


def test_default_schema_path_absent_means_no_gradebook(tmp_path):
    """If no schema exists, gradebook.csv is not produced (bundle still builds)."""
    cfg = ArchiveConfig(
        course="CECS 478",
        course_dir="378-478",
        term="sp26",
        section="04",
        vault_root=tmp_path,
        roster_xls=FIX / "roster_478-04_sp26.xls",
        canvas_grades_csv=FIX / "grades_478-04_sp26.csv",
    )
    bundle = build_bundle(cfg)
    assert not (bundle / "gradebook.csv").exists()


def test_build_bundle_canvas_not_in_roster_fails(tmp_path):
    """Canvas student not in roster (excluding ISA) → fatal."""
    bad_roster = tmp_path / "bad_roster.xls"
    bad_roster.write_text(
        '<!DOCTYPE html><html><body><table>\n'
        '<tr><th>Notify</th><th>ID</th><th>Name</th><th>Pronouns</th>'
        '<th>Graduation Candidate</th><th>Units</th><th>Program and Plan</th>'
        '<th>Academic Level</th><th>Status Note</th><th>Add Dt</th>'
        '<th>Grade Dt</th><th>Incomplete Grade Agreement</th><th>Additional Info</th></tr>\n'
        '<tr><td></td><td>999999999</td><td>Different,Person</td><td></td><td></td>'
        '<td>3.00</td><td>CS BS</td><td>Senior</td><td></td><td>01/21/2026</td>'
        '<td></td><td>Add</td><td></td>\n'
        '</table></body></html>\n'
    )
    cfg = ArchiveConfig(
        course="CECS 478",
        course_dir="378-478",
        term="sp26",
        section="04",
        vault_root=tmp_path,
        roster_xls=bad_roster,
        canvas_grades_csv=FIX / "grades_478-04_sp26.csv",
    )
    with pytest.raises(SystemExit, match="not in.*roster"):
        build_bundle(cfg)


def test_build_bundle_with_github_form(tmp_path):
    """Roster + form CSV → github.csv + github.audit.csv + github.raw.csv."""
    cfg = ArchiveConfig(
        course="CECS 478",
        course_dir="378-478",
        term="sp26",
        section="04",
        vault_root=tmp_path,
        roster_xls=FIX / "roster_478-04_sp26.xls",
        github_form_csv=FIX / "github_form_sp26.csv",
    )
    bundle = build_bundle(cfg)
    assert (bundle / "github.csv").exists()
    assert (bundle / "github.raw.csv").exists()
    assert (bundle / "github.audit.csv").exists()
    manifest = yaml.safe_load((bundle / "manifest.yaml").read_text())
    assert manifest["github"]["source"] == "form"
    assert manifest["github"]["csv"] == "github.csv"


def test_check_bundle_detects_exam_drift(tmp_path):
    """If a stored .tex changes after manifest serial is recorded, check fails."""
    cfg = ArchiveConfig(
        course="CECS 478",
        course_dir="378-478",
        term="sp26",
        section="04",
        vault_root=tmp_path,
        roster_xls=FIX / "roster_478-04_sp26.xls",
        exam_dirs=[FIX],  # the fixture dir has dummy_exam.tex
    )
    bundle = build_bundle(cfg)
    # Mutate the archived tex so its source serial drifts.
    archived_tex = bundle / "exams" / "dummy_exam.tex"
    assert archived_tex.exists()
    archived_tex.write_text(archived_tex.read_text() + "\n% drift\n")
    ok, fail, issues = check_bundle(bundle)
    assert fail >= 1
    assert any("dummy_exam" in i for i in issues)
