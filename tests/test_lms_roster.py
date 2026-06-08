import pytest
from pathlib import Path
from lectern.lms_roster import (
    parse_mycsulb_xls,
    normalize_to_roster_csv,
    infer_from_filename,
    write_roster_csv,
    RosterRow,
)

FIX = Path(__file__).parent / "fixtures" / "exam_archive"


def test_infer_from_filename():
    assert infer_from_filename(Path("class-roster-cecs-478-04-12548.xls")) == {
        "course": "CECS 478", "section": "04", "class_number": "12548"
    }
    assert infer_from_filename(Path("class-roster-cecs-326-01-01116.xls"))["course"] == "CECS 326"
    # Non-matching filename
    assert infer_from_filename(Path("foo.xls")) == {}
    assert infer_from_filename(Path("some-other-roster.xls")) == {}


def test_parse_real_478_04_xls():
    rows = parse_mycsulb_xls(FIX / "roster_478-04_sp26.xls")
    assert len(rows) == 15
    by_id = {r["ID"]: r for r in rows}
    assert "040100001" in by_id
    alderman = by_id["040100001"]
    assert alderman["Name"] == "Alderman,Jake P"
    assert by_id["040100002"]["Status Note"] == "Withdrawn"
    assert by_id["040100012"]["Status Note"] == "Withdrawn"


def test_parse_minimal_xls():
    rows = parse_mycsulb_xls(FIX / "roster_minimal.xls")
    assert len(rows) == 3
    by_id = {r["ID"]: r for r in rows}
    # María José López (UTF-8) — verify Unicode passes through
    assert by_id["333333333"]["Name"] == "López,María José"
    assert by_id["333333333"]["Status Note"] == "Withdrawn"
    assert by_id["333333333"]["Grade Dt"] == "04/16/2026"


def test_normalize_478_04():
    raw = parse_mycsulb_xls(FIX / "roster_478-04_sp26.xls")
    norm = normalize_to_roster_csv(raw, course="CECS 478", section="04",
                                    class_number="12548", term="sp26")
    by_id = {r.student_id: r for r in norm}
    alderman = by_id["040100001"]
    assert alderman.lms_name == "Alderman,Jake P"
    assert alderman.display_name == "Jake P Alderman"
    assert alderman.canonical_name == "jake p alderman"
    assert alderman.enrollment_status == "enrolled"
    blackwell = by_id["040100002"]
    assert blackwell.enrollment_status == "withdrawn"
    assert blackwell.grade_dt == "2026-04-16"   # ISO conversion verified
    lopez = by_id["040100012"]
    assert lopez.enrollment_status == "withdrawn"


def test_normalize_minimal_accents():
    raw = parse_mycsulb_xls(FIX / "roster_minimal.xls")
    norm = normalize_to_roster_csv(raw, course="CECS 999", section="01",
                                    class_number="00001", term="fa26")
    by_id = {r.student_id: r for r in norm}
    lopez = by_id["333333333"]
    assert lopez.lms_name == "López,María José"
    assert lopez.display_name == "María José López"
    assert lopez.canonical_name == "maria jose lopez"   # accents stripped per canonical_name


def test_normalize_missing_name_fails():
    raw = [{"ID": "999999999", "Name": "", "Status Note": "", "Add Dt": "",
            "Grade Dt": "", "Program and Plan": "", "Academic Level": ""}]
    with pytest.raises(SystemExit, match="empty name"):
        normalize_to_roster_csv(raw, course="X", section="01", class_number="0",
                                term="sp26")


def test_write_roster_csv(tmp_path):
    raw = parse_mycsulb_xls(FIX / "roster_478-04_sp26.xls")
    norm = normalize_to_roster_csv(raw, course="CECS 478", section="04",
                                    class_number="12548", term="sp26")
    out = tmp_path / "roster.csv"
    write_roster_csv(norm, out)
    content = out.read_text()
    # Header line
    assert content.split("\n")[0] == "student_id,lms_name,display_name,canonical_name,section,enrollment_status,add_dt,grade_dt,program,academic_level"
    # Sample row presence
    assert "040100001" in content
    assert "Alderman,Jake P" in content
    # CSV escaping for the comma-in-name field — quoted
    assert '"Alderman,Jake P"' in content


def test_date_conversion():
    # The implementation's internal _convert_date should handle:
    from lectern.lms_roster import _convert_date
    assert _convert_date("01/21/2026") == "2026-01-21"
    assert _convert_date("") == ""
    assert _convert_date("invalid") == ""
