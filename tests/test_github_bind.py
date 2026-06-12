"""Tests for lectern.github_bind — student-id → GitHub username binding."""
import csv
from pathlib import Path
import pytest
from lectern.github_bind import (
    normalize_student_id,
    normalize_username,
    bind_from_form,
    bind_from_classroom,
    write_github_csv,
    write_audit_csv,
    BindingRow,
)

FIX = Path(__file__).parent / "fixtures" / "exam_archive"


def test_normalize_student_id():
    assert normalize_student_id("040100001") == ("040100001", [])
    # Strip non-digits + zero-pad
    assert normalize_student_id("  040100001  ") == ("040100001", [])
    # Letter prefix stripped
    sid, flags = normalize_student_id("C02962436")
    assert sid == "002962436"   # 9-pad after letter strip
    assert flags == []
    # Way too short — flagged
    sid, flags = normalize_student_id("424657")
    assert sid == "000424657"
    assert "malformed_id_6d" in flags or any("6d" in f for f in flags)
    # 10 digits — flagged (didn't fit 9)
    sid, flags = normalize_student_id("0401000255")
    assert "malformed_id_10d" in flags or any("10d" in f for f in flags)


def test_normalize_username():
    assert normalize_username("Smith123") == "smith123"
    assert normalize_username("  jsmith  ") == "jsmith"
    assert normalize_username("@JaneSmith") == "janesmith"
    assert normalize_username("https://github.com/Jane-Doe") == "jane-doe"


def test_bind_from_form_minimal_happy_path(tmp_path):
    """3 clean rows in, 3 bindings out (with synthetic roster matching SIDs)."""
    form = FIX / "github_form_minimal.csv"
    roster = tmp_path / "roster.csv"
    roster.write_text(
        "student_id,lms_name,display_name,canonical_name,section,enrollment_status,"
        "add_dt,grade_dt,program,academic_level\n"
        '111111111,"Smith,Jane",Jane Smith,jane smith,01,enrolled,2026-01-21,,,Senior\n'
        '222222222,"Doe,John",John Doe,john doe,01,enrolled,2026-01-21,,,Senior\n'
        '333333333,"López,María José",María José López,maria jose lopez,01,enrolled,2026-01-21,,,Senior\n'
    )
    out = bind_from_form(form, roster, section="01")
    assert len(out) == 3
    by_sid = {b.student_id: b for b in out}
    assert by_sid["111111111"].github_username == "jsmith01"
    assert by_sid["222222222"].github_username == "jdoe02"
    assert by_sid["333333333"].github_username == "mlopez03"


def test_bind_from_form_dedup_consistent(tmp_path):
    """When the same student submits twice with the same username, dedup keeps latest + sets consistent_dedup."""
    form = FIX / "github_form_sp26.csv"   # has 2 dupes for SID 400222333 (Vale in synthetic)
    # Build a synthetic roster matching the form's SIDs
    roster = tmp_path / "roster.csv"
    # The synthetic form rows include SID 400222333 twice — name "Vale"
    roster.write_text(
        "student_id,lms_name,display_name,canonical_name,section,enrollment_status,"
        "add_dt,grade_dt,program,academic_level\n"
        '400222333,"Vale,Vicki Marie",Vicki Marie Vale,vicki marie vale,04,enrolled,2026-01-21,,,Senior\n'
    )
    out = bind_from_form(form, roster, section="04")
    by_sid = {b.student_id: b for b in out}
    assert "400222333" in by_sid
    b = by_sid["400222333"]
    # Both form rows have the same username → consistent_dedup
    assert b.verified == "consistent_dedup"
    assert b.github_username == "vvale02"


def test_bind_from_form_missing_student(tmp_path):
    """Student in roster but not in form → 'missing'."""
    form = FIX / "github_form_minimal.csv"
    roster = tmp_path / "roster.csv"
    roster.write_text(
        "student_id,lms_name,display_name,canonical_name,section,enrollment_status,"
        "add_dt,grade_dt,program,academic_level\n"
        '999999999,"Nobody,Test",Test Nobody,test nobody,01,enrolled,2026-01-21,,,Senior\n'
    )
    out = bind_from_form(form, roster, section="01")
    assert len(out) == 1
    assert out[0].student_id == "999999999"
    assert out[0].github_username == ""
    assert out[0].verified == "missing"


def test_bind_from_form_emits_one_row_per_roster_student(tmp_path):
    """Output row count == roster row count, regardless of form coverage."""
    form = FIX / "github_form_minimal.csv"
    roster = tmp_path / "roster.csv"
    roster.write_text(
        "student_id,lms_name,display_name,canonical_name,section,enrollment_status,"
        "add_dt,grade_dt,program,academic_level\n"
        '111111111,"Smith,Jane",Jane Smith,jane smith,01,enrolled,2026-01-21,,,Senior\n'
        '999999999,"Missing,Person",Person Missing,person missing,01,enrolled,2026-01-21,,,Senior\n'
    )
    out = bind_from_form(form, roster, section="01")
    assert len(out) == 2


def test_bind_from_classroom(tmp_path):
    """Classroom CSV: roster_identifier, github_username, github_id, joined_at."""
    classroom = tmp_path / "classroom.csv"
    classroom.write_text(
        "roster_identifier,github_username,github_id,joined_at\n"
        "111111111,jsmith01,12345,2026-06-15T10:00:00Z\n"
        "222222222,jdoe02,67890,2026-06-15T11:00:00Z\n"
    )
    roster = tmp_path / "roster.csv"
    roster.write_text(
        "student_id,lms_name,display_name,canonical_name,section,enrollment_status,"
        "add_dt,grade_dt,program,academic_level\n"
        '111111111,"Smith,Jane",Jane Smith,jane smith,01,enrolled,2026-01-21,,,Senior\n'
        '222222222,"Doe,John",John Doe,john doe,01,enrolled,2026-01-21,,,Senior\n'
        '333333333,"Missing,Person",Person Missing,person missing,01,enrolled,2026-01-21,,,Senior\n'
    )
    out = bind_from_classroom(classroom, roster)
    by_sid = {b.student_id: b for b in out}
    assert by_sid["111111111"].github_username == "jsmith01"
    assert by_sid["111111111"].verified == "classroom_oauth"
    assert by_sid["333333333"].github_username == ""
    assert by_sid["333333333"].verified == "missing"
    assert "not joined" in by_sid["333333333"].notes


def test_write_github_csv(tmp_path):
    rows = [
        BindingRow(student_id="111", display_name="Jane Smith",
                   github_username="jsmith", source="form", submitted_at="2026-01-29T10:00",
                   verified="consistent_dedup", notes=""),
        BindingRow(student_id="222", display_name="Test", github_username="",
                   source="form", submitted_at="", verified="missing",
                   notes="missing"),
    ]
    out = tmp_path / "github.csv"
    write_github_csv(rows, out)
    text = out.read_text()
    assert text.split("\n")[0] == "student_id,display_name,github_username,source,submitted_at,verified,notes"
    assert "jsmith" in text
    assert "missing" in text


def test_write_audit_csv_only_flagged(tmp_path):
    """Audit CSV contains only rows with notes != '' OR verified in (missing, github_404)."""
    rows = [
        BindingRow(student_id="111", display_name="Clean", github_username="clean1",
                   source="form", submitted_at="", verified="consistent_dedup", notes=""),
        BindingRow(student_id="222", display_name="Missing", github_username="",
                   source="form", submitted_at="", verified="missing", notes="missing"),
        BindingRow(student_id="333", display_name="Flagged", github_username="dup-user",
                   source="form", submitted_at="", verified="unverified",
                   notes="alternate_usernames:other1"),
    ]
    out = tmp_path / "audit.csv"
    write_audit_csv(rows, out)
    text = out.read_text()
    assert "Clean" not in text   # clean row excluded
    assert "Missing" in text
    assert "Flagged" in text
