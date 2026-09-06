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


def test_compute_weighted_graded_only_renormalizes(schema_478):
    """Only `final` graded → standing == final_pct (labs weight dropped)."""
    s = load_schema(schema_478)
    standing = compute_weighted(
        {"final": 90.0}, s, graded_only=True, graded_cols={"final"}
    )
    assert standing == 90.0  # 0.5/0.5 * 90, labs renormalized out


def test_compute_weighted_graded_only_converges_to_full(schema_478):
    """All columns graded → graded_only == legacy full-schema weighted."""
    s = load_schema(schema_478)
    scores = {"lab1": 20.0, "final": 80.0}  # labs 100%, final 80%
    full = compute_weighted(scores, s)
    standing = compute_weighted(
        scores, s, graded_only=True, graded_cols={"lab1", "final"}
    )
    assert standing == full == 90.0  # 0.5*100 + 0.5*80


def test_compute_weighted_graded_only_excludes_ungraded_column(schema_478):
    """A graded group counts ONLY its graded columns in earned/max."""
    s = load_schema(schema_478)
    standing = compute_weighted(
        {"lab1": 10.0}, s, graded_only=True, graded_cols={"lab1"}
    )
    assert standing == 50.0  # lab1 10/20 = 50%, only graded group


# ── schema/vault-root resolution ─────────────────────────────────────────────
# Regression cover for two bugs found 2026-09-06:
#   1. `_default_archives_root` hardcoded the pre-2026-07-09 vault path as its
#      ONLY candidate, so every `import`/`build`/`export-canvas` died with
#      "schema not found" pointing at a directory gone for two months.
#   2. `_schema_for_course` tried the shared `378-478/gradebook-schema.yaml`
#      BEFORE `<num>/gradebook-schema.yaml`, so CECS 326 silently resolved to
#      the *478* schema — wrong weights, no error.

from lectern.gradebook import (  # noqa: E402
    _course_dirs,
    _course_num,
    _default_archives_root,
    _schema_for_course,
)


@pytest.fixture
def fake_vault(tmp_path):
    """A vault shaped like Anthony's: 326/ standalone, 378-478/ shared."""
    classes = tmp_path / "classes"
    (classes / "326").mkdir(parents=True)
    (classes / "378-478").mkdir(parents=True)
    (classes / "326" / "gradebook-schema.yaml").write_text("course: CECS 326\n")
    (classes / "378-478" / "gradebook-schema.yaml").write_text("course: CECS 478\n")
    (classes / "378-478" / "gradebook-schema-378.yaml").write_text("course: CECS 378\n")
    return tmp_path


def test_course_num_accepts_every_spelling():
    assert _course_num("CECS_478") == "478"
    assert _course_num("CECS 478") == "478"
    assert _course_num("478") == "478"


def test_course_dirs_prefers_exact_folder_over_shared(fake_vault):
    classes = fake_vault / "classes"
    assert _course_dirs(classes, "326")[0].name == "326"
    # 378 has no folder of its own; the shared one is the only candidate.
    assert [d.name for d in _course_dirs(classes, "378")] == ["378-478"]


def test_schema_own_folder_beats_shared_generic(fake_vault):
    """BUG 2 regression: 326 must NOT resolve to 378-478's (478) schema."""
    got = _schema_for_course("CECS_326", vault_root=fake_vault)
    assert got == fake_vault / "classes" / "326" / "gradebook-schema.yaml"
    assert "378-478" not in str(got)


def test_schema_per_course_override_beats_generic(fake_vault):
    got = _schema_for_course("CECS_378", vault_root=fake_vault)
    assert got.name == "gradebook-schema-378.yaml"


def test_schema_shared_generic_when_course_has_no_own_folder(fake_vault):
    """478 legitimately lives on the shared file."""
    got = _schema_for_course("CECS_478", vault_root=fake_vault)
    assert got == fake_vault / "classes" / "378-478" / "gradebook-schema.yaml"


def test_archives_root_prefers_explicit_vault_root(fake_vault):
    assert _default_archives_root(fake_vault) == fake_vault / "classes"


def test_archives_root_reads_env(fake_vault, monkeypatch):
    monkeypatch.setenv("LECTERN_VAULT_ROOT", str(fake_vault))
    assert _default_archives_root() == fake_vault / "classes"


def test_archives_root_explicit_beats_env(fake_vault, tmp_path, monkeypatch):
    other = tmp_path / "other"
    (other / "classes").mkdir(parents=True)
    monkeypatch.setenv("LECTERN_VAULT_ROOT", str(other))
    assert _default_archives_root(fake_vault) == fake_vault / "classes"


def test_archives_root_is_not_hardcoded_to_the_legacy_path(monkeypatch):
    """BUG 1 regression: the pre-migration path must never be the sole candidate."""
    monkeypatch.delenv("LECTERN_VAULT_ROOT", raising=False)
    from lectern import gradebook as gb
    legacy = Path.home() / "documents" / "obsidian" / "vault" / "classes"
    assert gb._DEFAULT_VAULTS[0] != legacy.parent, "legacy path must not be first"
    assert any("es1" in str(v) for v in gb._DEFAULT_VAULTS), "current vault must be a candidate"


def test_schema_missing_returns_named_guess_not_crash(tmp_path):
    """No schema anywhere → a sensible path for the error message, not a traceback."""
    (tmp_path / "classes").mkdir()
    got = _schema_for_course("CECS_999", vault_root=tmp_path)
    assert got.name in ("gradebook-schema-999.yaml", "gradebook-schema.yaml")
    assert not got.exists()


def test_course_num_rejects_empty_input_cleanly():
    """Reached straight from argv — must be a clean exit, not an IndexError."""
    for bad in ("", "   ", "_"):
        with pytest.raises(SystemExit, match="cannot read a course number"):
            _course_num(bad)
