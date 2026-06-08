import json
from pathlib import Path
import pytest
from lectern.lms_grades import (
    parse_canvas_csv,
    normalize_grades,
    write_grades_csv,
    write_filtered_csv,
    GradeRow,
    FilteredRow,
    NormalizedGrades,
)

FIX = Path(__file__).parent / "fixtures" / "exam_archive"


def test_parse_skips_metadata_rows_real():
    parsed = parse_canvas_csv(FIX / "grades_478-04_sp26.csv")
    # 14 actual student rows from row 3 onward (includes 1 ISA which gets filtered later)
    assert len(parsed["students"]) == 14
    # Points possible row populated (Final Exam in 478-04 Sp26 was scaled to 50)
    assert parsed["points_possible"].get("Final Exam (1689189)") == "50.00"


def test_parse_minimal_metadata_rows():
    parsed = parse_canvas_csv(FIX / "grades_minimal.csv")
    # 2 students + 1 ISA = 3 raw rows
    assert len(parsed["students"]) == 3
    assert parsed["points_possible"].get("Lab 1 (1001)") == "20.00"


def test_normalize_filters_isa_real():
    parsed = parse_canvas_csv(FIX / "grades_478-04_sp26.csv")
    norm = normalize_grades(parsed)
    # 13 students remain after ISA (040100010SA) filtered
    assert len(norm.grades) == 13
    assert len(norm.filtered) == 1
    assert norm.filtered[0].reason == "isa"
    assert norm.filtered[0].student_id.endswith("SA")
    # No SA in normalized output
    assert all(not r.student_id.endswith("SA") for r in norm.grades)


def test_normalize_assignment_scores_json():
    parsed = parse_canvas_csv(FIX / "grades_minimal.csv")
    norm = normalize_grades(parsed)
    alderman_like = next(r for r in norm.grades if r.student_id == "111111111")
    scores = json.loads(alderman_like.assignment_scores)
    # Keys are stripped of (canvas_id) suffix
    assert "Lab 1" in scores
    assert scores["Lab 1"] == "18.00"


def test_normalize_letter_columns_present_real():
    parsed = parse_canvas_csv(FIX / "grades_478-04_sp26.csv")
    norm = normalize_grades(parsed)
    alderman = next(r for r in norm.grades if r.student_id == "040100001")
    # Pre-finals all-F state — final_grade should be 'F' on this snapshot
    assert alderman.final_grade == "F"
    # final_score and current_score populated
    assert alderman.final_score != ""
    assert alderman.current_score != ""


def test_write_grades_csv(tmp_path):
    parsed = parse_canvas_csv(FIX / "grades_478-04_sp26.csv")
    norm = normalize_grades(parsed)
    out = tmp_path / "grades.csv"
    write_grades_csv(norm, out)
    text = out.read_text()
    assert text.split("\n")[0].startswith("student_id,display_name")
    # Sample row
    assert "040100001" in text
    # No ISA in output
    assert "SA" not in [line.split(",")[0] for line in text.split("\n")[1:]]


def test_write_filtered_csv(tmp_path):
    parsed = parse_canvas_csv(FIX / "grades_478-04_sp26.csv")
    norm = normalize_grades(parsed)
    out = tmp_path / "grades.filtered.csv"
    write_filtered_csv(norm, out)
    text = out.read_text()
    assert "040100010SA" in text
    assert "isa" in text


def test_empty_canvas_csv_fails(tmp_path):
    bad = tmp_path / "bad.csv"
    bad.write_text("Header1,Header2\n")  # only headers, no data + no metadata rows
    with pytest.raises(SystemExit, match="not enough rows"):
        parse_canvas_csv(bad)
