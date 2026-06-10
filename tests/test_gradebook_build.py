import json
from pathlib import Path
import pytest
from lectern.gradebook import load_schema, main as gradebook_main
from lectern.gradebook_build import (
    load_registry, RegistryEntry,
    read_component_scores,
    build_gradebook,
    export_canvas,
)


@pytest.fixture
def schema_378(tmp_path):
    p = tmp_path / "schema.yaml"
    p.write_text("""\
course: CECS 378
term_default: su26
columns:
  - {canvas_title: "Lab 1 - Symmetric Cryptography", short_name: lab1, title: "Lab 1", points: 60, group: assignments}
  - {canvas_title: "Exam 1", short_name: exam1, title: "Exam 1", points: 50, group: midterms}
  - {canvas_title: "Final Exam", short_name: final, title: "Final Exam", points: 100, group: final}
weights: {assignments: 0.35, midterms: 0.40, final: 0.25}
letter_cuts: {A: 90, B: 80, C: 70, D: 60, F: 0}
flags: [dss, incomplete, withdrew]
""")
    return p


def _write_scores(path, rows):
    path.write_text(
        "last,first,sid,version,score,status\n"
        + "\n".join(rows) + "\n", encoding="utf-8")


def _roster(tmp_path, rows):
    p = tmp_path / "roster.csv"
    p.write_text(
        "student_id,display_name,enrollment_status\n"
        + "\n".join(rows) + "\n", encoding="utf-8")
    return p


# ── registry ────────────────────────────────────────────────────────────────

def test_load_registry_resolves_relative_paths(tmp_path):
    (tmp_path / "exams").mkdir()
    sc = tmp_path / "exams" / "exam1_scores.csv"
    _write_scores(sc, ["Gordon,James,040100204,A,43.0,Graded"])
    reg = tmp_path / "components.yaml"
    reg.write_text(
        "components:\n"
        "  - short_name: exam1\n"
        "    scores: exams/exam1_scores.csv\n", encoding="utf-8")
    entries = load_registry(reg)
    assert entries == [RegistryEntry(short_name="exam1", scores_path=sc.resolve())]


def test_load_registry_missing_file_errors(tmp_path):
    reg = tmp_path / "components.yaml"
    reg.write_text(
        "components:\n  - short_name: exam1\n    scores: nope.csv\n",
        encoding="utf-8")
    with pytest.raises(SystemExit, match="nope.csv"):
        load_registry(reg)


# ── component scores reader ─────────────────────────────────────────────────

def test_read_component_scores_basic(tmp_path):
    sc = tmp_path / "exam1_scores.csv"
    _write_scores(sc, [
        "Gordon,James,040100204,A,43.0,Graded",
        "Todd,Jason,040100215,A,,No-show",
        "Cain,Cassandra,30766500,A,15.0,Graded",   # short SID → padded
    ])
    got = read_component_scores(sc)
    assert got["040100204"] == (43.0, "Graded")
    assert got["040100215"] == (0.0, "No-show")   # no-show → earned 0
    assert got["040100214"] == (15.0, "Graded")   # padded to 9 digits


def test_read_component_scores_blank_is_ungraded(tmp_path):
    sc = tmp_path / "exam1_scores.csv"
    _write_scores(sc, ["Doe,Jane,012345678,A,,"])   # blank score + blank status
    got = read_component_scores(sc)
    assert "012345678" not in got   # ungraded: excluded entirely


def test_read_component_scores_bad_number_errors(tmp_path):
    sc = tmp_path / "exam1_scores.csv"
    _write_scores(sc, ["Doe,Jane,012345678,A,abc,Graded"])
    with pytest.raises(SystemExit, match="012345678"):
        read_component_scores(sc)


# ── builder ─────────────────────────────────────────────────────────────────

def test_build_gradebook_in_progress_standing(tmp_path, schema_378):
    schema = load_schema(schema_378)
    sc = tmp_path / "exam1_scores.csv"
    _write_scores(sc, [
        "Gordon,James,040100204,A,40.0,Graded",     # 40/50 = 80%
        "Todd,Jason,040100215,A,,No-show",     # 0 → 0%
    ])
    reg = tmp_path / "components.yaml"
    reg.write_text("components:\n  - short_name: exam1\n    scores: exam1_scores.csv\n",
                   encoding="utf-8")
    roster = _roster(tmp_path, [
        "040100204,James Gordon,enrolled",
        "040100215,Jason Todd,enrolled",
    ])
    out = tmp_path / "out"; out.mkdir()
    rows = build_gradebook(reg, roster, schema, out)
    by = {r["student_id"]: r for r in rows}
    # only midterms graded → standing == exam1_pct (renormalized)
    assert by["040100204"]["standing_score"] == 80.0
    assert by["040100204"]["letter_grade"] == "B"
    assert by["040100204"]["in_progress"] == "true"
    assert by["040100204"]["graded_cols"] == "1" and by["040100204"]["total_cols"] == "3"
    assert by["040100215"]["standing_score"] == 0.0
    assert by["040100204"]["weighted_score"] == 80.0  # cockpit-compat alias
    assert (out / "gradebook.csv").exists() and (out / "GRADEBOOK.md").exists()


def test_build_gradebook_unions_and_flags_stale_roster(tmp_path, schema_378):
    schema = load_schema(schema_378)
    sc = tmp_path / "exam1_scores.csv"
    _write_scores(sc, ["Cain,Cassandra,040100214,A,15.0,Graded"])  # not in roster
    reg = tmp_path / "components.yaml"
    reg.write_text("components:\n  - short_name: exam1\n    scores: exam1_scores.csv\n",
                   encoding="utf-8")
    roster = _roster(tmp_path, ["040100204,James Gordon,enrolled"])  # no scores
    out = tmp_path / "out"; out.mkdir()
    rows = build_gradebook(reg, roster, schema, out)
    by = {r["student_id"]: r for r in rows}
    assert "stale-roster" in by["040100214"]["flags"]      # scored, not in roster
    assert by["040100214"]["display_name"] == "Cassandra Cain"  # name from scores file
    assert by["040100204"]["graded_cols"] == "0"           # roster-only, ungraded


def test_build_gradebook_withdrawn_yields_W(tmp_path, schema_378):
    """roster enrollment_status 'withdrawn' → letter W + 'withdrew' flag, mirroring
    the Canvas-import path. Withdrawal trumps the computed standing (even a passing
    score yields W); an *enrolled* no-show is unaffected (stays 0/F)."""
    schema = load_schema(schema_378)
    sc = tmp_path / "exam1_scores.csv"
    _write_scores(sc, [
        "Gordon,James,040100204,A,40.0,Graded",       # enrolled → B
        "Todd,Jason,040100215,A,45.0,Graded",    # withdrawn but 45/50=90% → still W
    ])
    reg = tmp_path / "components.yaml"
    reg.write_text("components:\n  - short_name: exam1\n    scores: exam1_scores.csv\n",
                   encoding="utf-8")
    roster = _roster(tmp_path, [
        "040100204,James Gordon,enrolled",
        "040100215,Jason Todd,withdrawn",
    ])
    out = tmp_path / "out"; out.mkdir()
    rows = build_gradebook(reg, roster, schema, out)
    by = {r["student_id"]: r for r in rows}
    assert by["040100215"]["letter_grade"] == "W"          # withdrawal trumps the 90%
    assert "withdrew" in by["040100215"]["flags"]
    assert by["040100215"]["enrollment_status"] == "withdrawn"
    assert by["040100204"]["letter_grade"] == "B"          # enrolled student unaffected


# ── canvas export ───────────────────────────────────────────────────────────

def test_export_canvas_only_graded_components(tmp_path, schema_378):
    schema = load_schema(schema_378)
    gb = tmp_path / "gradebook.csv"
    gb.write_text(
        "student_id,display_name,enrollment_status,raw_scores,standing_score,"
        "weighted_score,letter_grade,in_progress,graded_cols,total_cols,flags\n"
        '040100204,James Gordon,enrolled,"{""exam1"": 40.0}",80.0,80.0,B,true,1,3,\n'
        '040100215,Jason Todd,enrolled,"{""exam1"": 0.0}",0.0,0.0,F,true,1,3,\n',
        encoding="utf-8")
    out = tmp_path / "canvas_import.csv"
    export_canvas(gb, schema, out)
    lines = out.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "SIS User ID,Exam 1"        # only the graded component column
    assert "Lab 1 - Symmetric Cryptography" not in lines[0]
    assert lines[1] == "040100204,40.0"
    assert lines[2] == "040100215,0.0"             # no-show exports 0


# ── CLI ─────────────────────────────────────────────────────────────────────

def test_cli_build_then_export(tmp_path, schema_378):
    sc = tmp_path / "exam1_scores.csv"
    _write_scores(sc, ["Gordon,James,040100204,A,40.0,Graded"])
    reg = tmp_path / "components.yaml"
    reg.write_text("components:\n  - short_name: exam1\n    scores: exam1_scores.csv\n",
                   encoding="utf-8")
    roster = _roster(tmp_path, ["040100204,James Gordon,enrolled"])
    out = tmp_path / "out"; out.mkdir()
    rc = gradebook_main([
        "build", "--course", "CECS_378", "--term", "su26", "--section", "01",
        "--registry", str(reg), "--roster", str(roster),
        "--schema", str(schema_378), "--out", str(out),
    ])
    assert rc == 0 and (out / "gradebook.csv").exists()
    rc = gradebook_main([
        "export-canvas", "--gradebook", str(out / "gradebook.csv"),
        "--schema", str(schema_378), "--out", str(out / "canvas_import.csv"),
    ])
    assert rc == 0
    assert (out / "canvas_import.csv").read_text().splitlines()[0] == "SIS User ID,Exam 1"



def test_registry_optional_fields(tmp_path):
    from lectern.gradebook_build import load_registry, RegistryEntry
    sc = tmp_path / "exam1_scores.csv"; sc.write_text("last,first,sid,version,score,status\n", encoding="utf-8")
    bk = tmp_path / "item_scores_A.csv"; bk.write_text("student_id\n", encoding="utf-8")
    reg = tmp_path / "components.yaml"
    reg.write_text(
        "components:\n"
        "  - short_name: exam1\n"
        "    scores: exam1_scores.csv\n"
        "    link: classes/378-478/exams/exam1_su26/GRADING_NOTE\n"
        "    analysis: classes/378-478/exams/exam1_su26/ITEM_ANALYSIS\n"
        "    breakdown: item_scores_A.csv\n"
        "    kind: exam\n", encoding="utf-8")
    e = load_registry(reg)[0]
    assert e.short_name == "exam1"
    assert e.link == "classes/378-478/exams/exam1_su26/GRADING_NOTE"
    assert e.analysis == "classes/378-478/exams/exam1_su26/ITEM_ANALYSIS"
    assert e.breakdown == ((tmp_path / "item_scores_A.csv").resolve(),)
    assert e.kind == "exam"


def test_registry_defaults_when_optional_absent(tmp_path):
    from lectern.gradebook_build import load_registry
    sc = tmp_path / "exam1_scores.csv"; sc.write_text("x\n", encoding="utf-8")
    reg = tmp_path / "components.yaml"
    reg.write_text("components:\n  - short_name: exam1\n    scores: exam1_scores.csv\n", encoding="utf-8")
    e = load_registry(reg)[0]
    assert e.link is None and e.analysis is None and e.breakdown == () and e.kind is None


def test_registry_breakdown_glob(tmp_path):
    """breakdown: item_scores_*.csv expands to a sorted tuple of matching paths."""
    from lectern.gradebook_build import load_registry
    sc = tmp_path / "exam1_scores.csv"; sc.write_text("x\n", encoding="utf-8")
    bk_a = tmp_path / "item_scores_A.csv"; bk_a.write_text("student_id\n", encoding="utf-8")
    bk_b = tmp_path / "item_scores_B.csv"; bk_b.write_text("student_id\n", encoding="utf-8")
    reg = tmp_path / "components.yaml"
    reg.write_text(
        "components:\n"
        "  - short_name: exam1\n"
        "    scores: exam1_scores.csv\n"
        "    breakdown: item_scores_*.csv\n", encoding="utf-8")
    e = load_registry(reg)[0]
    assert e.breakdown == (bk_a.resolve(), bk_b.resolve())


def test_registry_breakdown_list(tmp_path):
    """breakdown: [A.csv, B.csv] (YAML list) yields a tuple of those paths."""
    from lectern.gradebook_build import load_registry
    sc = tmp_path / "exam1_scores.csv"; sc.write_text("x\n", encoding="utf-8")
    bk_a = tmp_path / "item_scores_A.csv"; bk_a.write_text("student_id\n", encoding="utf-8")
    bk_b = tmp_path / "item_scores_B.csv"; bk_b.write_text("student_id\n", encoding="utf-8")
    reg = tmp_path / "components.yaml"
    reg.write_text(
        "components:\n"
        "  - short_name: exam1\n"
        "    scores: exam1_scores.csv\n"
        "    breakdown:\n"
        "      - item_scores_A.csv\n"
        "      - item_scores_B.csv\n", encoding="utf-8")
    e = load_registry(reg)[0]
    assert e.breakdown == (bk_a.resolve(), bk_b.resolve())


def test_build_gradebook_excludes_dropped_noshow_not_in_roster(tmp_path, schema_378):
    """A No-show-only student absent from the roster is dropped — not resurrected."""
    schema = load_schema(schema_378)
    sc = tmp_path / "exam1_scores.csv"
    _write_scores(sc, [
        "Gordon,James,040100204,A,40.0,Graded",            # enrolled, graded
        "Todd,Jason,040100215,A,,No-show",            # enrolled no-show → 0/F
        "Wilson,Slade,028781777,A,,No-show (dropped)",    # NOT in roster → excluded
    ])
    reg = tmp_path / "components.yaml"
    reg.write_text("components:\n  - short_name: exam1\n    scores: exam1_scores.csv\n",
                   encoding="utf-8")
    roster = _roster(tmp_path, [
        "040100204,James Gordon,enrolled",
        "040100215,Jason Todd,enrolled",
    ])
    out = tmp_path / "out"; out.mkdir()
    rows = build_gradebook(reg, roster, schema, out)
    sids = {r["student_id"] for r in rows}
    assert "028781777" not in sids          # dropped no-show excluded
    assert "040100215" in sids              # enrolled no-show kept (0/F)
    by = {r["student_id"]: r for r in rows}
    assert by["040100215"]["standing_score"] == 0.0


def test_build_writes_ledger_surfaces(tmp_path, schema_378):
    schema = load_schema(schema_378)
    sc = tmp_path / "exam1_scores.csv"
    _write_scores(sc, ["Gordon,James,040100204,A,40.0,Graded"])
    reg = tmp_path / "components.yaml"
    reg.write_text("components:\n  - short_name: exam1\n    scores: exam1_scores.csv\n    kind: exam\n",
                   encoding="utf-8")
    roster = _roster(tmp_path, ["040100204,James Gordon,enrolled"])
    out = tmp_path / "out"; out.mkdir()
    build_gradebook(reg, roster, schema, out, section="01", term="su26")
    assert (out / "GRADEBOOK.md").exists()
    assert (out / "assignments" / "exam1.md").exists()
    gb = (out / "GRADEBOOK.md").read_text()
    assert "Per-student statements" in gb and "exam1" in gb
