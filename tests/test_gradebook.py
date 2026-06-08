import json
from pathlib import Path
import pytest
from lectern.gradebook import (
    GradebookSchema,
    load_schema,
    compute_weighted,
    apply_letter_cuts,
    dfw_rate,
    GradebookRow,
    import_canvas,
)

FIX = Path(__file__).parent / "fixtures" / "exam_archive"


@pytest.fixture
def schema_478(tmp_path):
    p = tmp_path / "schema.yaml"
    p.write_text("""\
course: CECS 478
term_default: sp26
columns:
  - {canvas_title: "Lab 1", short_name: lab1, title: "Lab 1", points: 20, group: labs}
  - {canvas_title: "Final Exam", short_name: final, title: "Final Exam", points: 100, group: final}
weights:
  labs: 0.5
  final: 0.5
letter_cuts: {A: 90, B: 80, C: 70, D: 60, F: 0}
flags: [dss, incomplete, withdrew]
""")
    return p


def test_load_schema(schema_478):
    s = load_schema(schema_478)
    assert s.course == "CECS 478"
    assert s.weights == {"labs": 0.5, "final": 0.5}
    assert s.letter_cuts["A"] == 90
    assert s.flags == ["dss", "incomplete", "withdrew"]


def test_load_schema_weights_validation(tmp_path):
    """Weights that don't sum to ~1.0 → SystemExit."""
    bad = tmp_path / "bad.yaml"
    bad.write_text("""\
course: X
term_default: sp26
columns: []
weights: {labs: 0.3, final: 0.3}
letter_cuts: {A: 90, F: 0}
flags: []
""")
    with pytest.raises(SystemExit, match="weights"):
        load_schema(bad)


def test_compute_weighted_simple():
    schema = GradebookSchema(
        course="X", term_default="sp26",
        columns=[
            {"short_name": "lab1", "points": 20, "group": "labs"},
            {"short_name": "final", "points": 100, "group": "final"},
        ],
        weights={"labs": 0.5, "final": 0.5},
        letter_cuts={"A": 90, "F": 0},
        flags=[],
    )
    # lab1: 20/20 = 100%, final: 90/100 = 90%
    # weighted: 0.5*100 + 0.5*90 = 95
    score = compute_weighted({"lab1": 20.0, "final": 90.0}, schema)
    assert score == 95.0


def test_compute_weighted_missing_treated_as_zero():
    schema = GradebookSchema(
        course="X", term_default="sp26",
        columns=[
            {"short_name": "lab1", "points": 20, "group": "labs"},
            {"short_name": "final", "points": 100, "group": "final"},
        ],
        weights={"labs": 0.5, "final": 0.5},
        letter_cuts={"A": 90, "F": 0},
        flags=[],
    )
    # Missing lab1, final 100%
    # labs: 0/20 = 0%, final: 100/100 = 100%
    # weighted: 0.5*0 + 0.5*100 = 50
    score = compute_weighted({"final": 100.0}, schema)
    assert score == 50.0


def test_apply_letter_cuts():
    s = GradebookSchema(course="X", term_default="sp26", columns=[],
                        weights={}, letter_cuts={"A": 90, "B": 80, "C": 70, "D": 60, "F": 0},
                        flags=[])
    assert apply_letter_cuts(92.5, s) == "A"
    assert apply_letter_cuts(85.0, s) == "B"
    assert apply_letter_cuts(70.0, s) == "C"
    assert apply_letter_cuts(60.0, s) == "D"
    assert apply_letter_cuts(59.99, s) == "F"
    assert apply_letter_cuts(0.0, s) == "F"


def test_dfw_rate():
    grades = [
        {"letter_grade": "A"},
        {"letter_grade": "B"},
        {"letter_grade": "D"},
        {"letter_grade": "F"},
        {"letter_grade": "W"},
    ]
    # 3 D/F/W out of 5
    assert dfw_rate(grades) == 0.6


def test_dfw_rate_empty():
    assert dfw_rate([]) == 0.0
