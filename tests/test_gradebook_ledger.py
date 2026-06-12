import json
from pathlib import Path
import pytest
from lectern.gradebook import load_schema
from lectern.gradebook_build import RegistryEntry
from lectern.gradebook_ledger import (
    render_overview, render_assignment_page, render_student_view_block,
    reconcile_assignment,
)


@pytest.fixture
def schema_378(tmp_path):
    p = tmp_path / "schema.yaml"
    p.write_text("""\
course: CECS 378
term_default: su26
columns:
  - {canvas_title: "Lab 1", short_name: lab1, title: "Lab 1", points: 60, group: assignments}
  - {canvas_title: "Exam 1", short_name: exam1, title: "Exam 1", points: 50, group: midterms}
  - {canvas_title: "Final Exam", short_name: final, title: "Final", points: 100, group: final}
weights: {assignments: 0.35, midterms: 0.40, final: 0.25}
letter_cuts: {A: 90, B: 80, C: 70, D: 60, F: 0}
flags: [dss]
""")
    return load_schema(p)


def _rows():
    return [
        {"student_id": "040100020", "display_name": "Kate Kane", "enrollment_status": "enrolled",
         "raw_scores": json.dumps({"exam1": 40.0}), "standing_score": 80.0, "weighted_score": 80.0,
         "letter_grade": "B", "in_progress": "true", "graded_cols": "1", "total_cols": "3", "flags": ""},
    ]


def test_render_overview_grouped_with_links(schema_378):
    md = render_overview(_rows(), schema_378, [], assign_dir_rel="classes/378-478/archives/su26-01/assignments")
    # component header wikilinks to its assignment page
    assert "[[classes/378-478/archives/su26-01/assignments/exam1|" in md
    # graded cell shows the points; ungraded shows the bullet
    assert "40" in md and "·" in md
    # midterms subtotal = exam1 pct = 80; bottom line carries standing + in-progress letter
    assert "80" in md and "B*" in md


def _exam_rows():
    return [
        {"student_id": "040100020", "display_name": "Kate Kane", "raw_scores": json.dumps({"exam1": 40.0})},
        {"student_id": "040100010", "display_name": "Alfreda P", "raw_scores": json.dumps({"exam1": 0.0})},
    ]


def test_render_assignment_page_exam_with_grid(tmp_path, schema_378):
    matrix = tmp_path / "item_scores_A.csv"
    matrix.write_text("student_id,Q1,Q2,total\n040100020,2,2,40\n", encoding="utf-8")
    entry = RegistryEntry(short_name="exam1", scores_path=tmp_path / "x.csv",
                          link="classes/378-478/exams/exam1_su26/GRADING_NOTE",
                          analysis="classes/378-478/exams/exam1_su26/ITEM_ANALYSIS",
                          breakdown=(matrix,), kind="exam")
    md = render_assignment_page(entry, schema_378, _exam_rows())
    assert "# Exam 1" in md
    assert "[[classes/378-478/exams/exam1_su26/GRADING_NOTE" in md   # links the grading note
    assert "[[classes/378-478/exams/exam1_su26/ITEM_ANALYSIS" in md  # links the item analysis
    assert "Kate Kane" in md and "40" in md                          # score roster
    assert "Per-question grid" in md and "Q1" in md                  # collapsible grid present


def test_render_assignment_page_lab_no_grid(tmp_path, schema_378):
    entry = RegistryEntry(short_name="lab1", scores_path=tmp_path / "x.csv", kind="lab")
    rows = [{"student_id": "040100020", "display_name": "Kate Kane",
             "raw_scores": json.dumps({"lab1": 55.0})}]
    md = render_assignment_page(entry, schema_378, rows)
    assert "# Lab 1" in md and "Kate Kane" in md and "55" in md
    assert "Per-question grid" not in md   # labs have no item grid


def test_reconcile_assignment_flags_mismatch(tmp_path, schema_378):
    matrix = tmp_path / "item_scores_A.csv"
    matrix.write_text("student_id,Q1,Q2,total\n040100020,2,2,41\n", encoding="utf-8")  # 41 ≠ 40
    entry = RegistryEntry(short_name="exam1", scores_path=tmp_path / "x.csv",
                          breakdown=(matrix,), kind="exam")
    result = reconcile_assignment(entry, _exam_rows())
    assert any("040100020" in f and "41" in f and "40" in f for f in result["mismatches"])


def test_render_student_view_block(schema_378):
    block = render_student_view_block(schema_378)
    assert "```dataviewjs" in block
    assert "raw_scores" in block            # reads the per-component data
    assert "gradebook.csv" in block         # from the ledger CSV
    assert "assignments" in block           # links each component to its page
    # schema-tolerant fallbacks: works for new-build AND legacy/backfilled gradebook.csv
    assert "short_scores" in block          # legacy import key (preferred when present)
    assert "canvas_final_score" in block    # legacy standing fallback
    assert "override_grade" in block        # recorded-letter override honored


# ── BLOCKER 1: RFC-4180 CSV parser in DataviewJS block ───────────────────────

def test_student_view_block_rfc4180_parser(schema_378):
    """Emitted JS must use proper doubled-quote RFC-4180 handling, not the broken
    toggle-q approach. Asserts the corrected parser signature is present and the
    broken strip pattern is absent."""
    block = render_student_view_block(schema_378)
    # Corrected parser uses l[i+1]==' ' doubled-quote lookahead
    assert "l[i+1]==" in block or 'l[i+1]==' in block
    # Must split on /\r?\n/ for CRLF CSV files
    assert r"/\r?\n/" in block
    # The broken .replace(/^"|"$/g, "") stripping must NOT be present
    assert '.replace(/^"|"$/g' not in block


# ── BLOCKER 2: malformed matrix doesn't crash ─────────────────────────────────

def test_reconcile_malformed_matrix_no_total(tmp_path, schema_378):
    """A breakdown matrix missing the 'total' column lands in mismatches, not reconciling."""
    matrix = tmp_path / "bad_matrix.csv"
    matrix.write_text("student_id,Q1\n040100020,20\n", encoding="utf-8")
    entry = RegistryEntry(short_name="exam1", scores_path=tmp_path / "x.csv",
                          breakdown=(matrix,), kind="exam")
    result = reconcile_assignment(entry, _exam_rows())
    assert len(result["mismatches"]) == 1
    assert "missing student_id/total column" in result["mismatches"][0]
    assert result["reconciling"] == []


# ── IMPORTANT 3: roster mismatch flagging ─────────────────────────────────────

def test_reconcile_flags_roster_mismatches(tmp_path, schema_378):
    """Sids in grid but not in recorded, and vice versa, land in reconciling (not mismatches)."""
    # 040100020 is in _exam_rows() (recorded), 040100010 is also in _exam_rows()
    # Matrix has 040100020 (in both) + 099999999 (grid-only, not in rows)
    # 040100010 is in rows but NOT in matrix → "recorded but no grid row"
    matrix = tmp_path / "matrix.csv"
    matrix.write_text(
        "student_id,Q1,Q2,total\n040100020,2,2,40\n099999999,1,1,0\n",
        encoding="utf-8",
    )
    entry = RegistryEntry(short_name="exam1", scores_path=tmp_path / "x.csv",
                          breakdown=(matrix,), kind="exam")
    result = reconcile_assignment(entry, _exam_rows())
    sid_reconciling = " ".join(result["reconciling"])
    # 040100010 scored 0.0 in _exam_rows but is absent from the matrix
    assert "040100010" in sid_reconciling and "recorded but no grid row" in sid_reconciling
    # 099999999 is in matrix but has no recorded score in _exam_rows
    assert "099999999" in sid_reconciling and "grid row but no recorded score" in sid_reconciling
    # These are NOT mismatches — value-wise all is fine for the one student in both
    assert result["mismatches"] == []


# ── IMPORTANT 4a: distribution + median + σ ──────────────────────────────────

def test_render_assignment_page_stats(tmp_path, schema_378):
    """Assignment page includes median, σ, and A/B/C/D/F distribution."""
    entry = RegistryEntry(short_name="exam1", scores_path=tmp_path / "x.csv",
                          kind="exam")
    md = render_assignment_page(entry, schema_378, _exam_rows())
    # median and sigma lines must appear
    assert "median" in md
    assert "σ" in md
    # distribution bands present
    assert "A:" in md and "B:" in md and "F:" in md
    # Kate Kane: 40/50 = 80% → B band; Alfreda P: 0/50 = 0% → F band
    assert "B:1" in md
    assert "F:1" in md


# ── IMPORTANT 4b: item-analysis embed (exam only) ────────────────────────────

def test_render_assignment_page_item_analysis_embed(tmp_path, schema_378):
    """When entry.analysis is set, exam page emits ![[...]] transclusion line."""
    matrix = tmp_path / "matrix.csv"
    matrix.write_text("student_id,Q1,Q2,total\n040100020,2,2,40\n", encoding="utf-8")
    entry = RegistryEntry(short_name="exam1", scores_path=tmp_path / "x.csv",
                          link="classes/378-478/exams/exam1_su26/GRADING_NOTE",
                          analysis="classes/378-478/exams/exam1_su26/ITEM_ANALYSIS",
                          breakdown=(matrix,), kind="exam")
    md = render_assignment_page(entry, schema_378, _exam_rows())
    # Transclusion embed must be present
    assert "![[classes/378-478/exams/exam1_su26/ITEM_ANALYSIS]]" in md
    # Source link must still be there (keep existing)
    assert "[[classes/378-478/exams/exam1_su26/ITEM_ANALYSIS|item analysis]]" in md


# ── IMPORTANT 4c: per-criterion lab table ────────────────────────────────────

def test_render_assignment_page_lab_per_criterion(tmp_path, schema_378):
    """Lab page renders a per-criterion table when scores CSV has extra columns."""
    scores = tmp_path / "lab1_scores.csv"
    # Extra column: participation
    scores.write_text(
        "last,first,sid,version,score,status,participation\n"
        "Kane,Kate,040100020,,55,Graded,10\n",
        encoding="utf-8",
    )
    entry = RegistryEntry(short_name="lab1", scores_path=scores, kind="lab")
    rows = [{"student_id": "040100020", "display_name": "Kate Kane",
             "raw_scores": json.dumps({"lab1": 55.0})}]
    md = render_assignment_page(entry, schema_378, rows)
    assert "Per-criterion breakdown" in md
    assert "participation" in md
    assert "10" in md


def test_render_assignment_page_lab_no_extra_columns(tmp_path, schema_378):
    """Lab page with only standard columns does NOT render a per-criterion table."""
    scores = tmp_path / "lab1_scores.csv"
    scores.write_text(
        "last,first,sid,version,score,status\n"
        "Kane,Kate,040100020,,55,Graded\n",
        encoding="utf-8",
    )
    entry = RegistryEntry(short_name="lab1", scores_path=scores, kind="lab")
    rows = [{"student_id": "040100020", "display_name": "Kate Kane",
             "raw_scores": json.dumps({"lab1": 55.0})}]
    md = render_assignment_page(entry, schema_378, rows)
    assert "Per-criterion breakdown" not in md


# ── multi-form exam (Form A / Form B) ─────────────────────────────────────────

def test_render_assignment_page_two_forms(tmp_path, schema_378):
    """Two breakdown matrices render two labeled grids; reconcile covers both forms."""
    matrix_a = tmp_path / "item_scores_A.csv"
    matrix_a.write_text(
        "student_id,Q1,Q2,total\n040100020,20,20,40\n",
        encoding="utf-8",
    )
    matrix_b = tmp_path / "item_scores_B.csv"
    matrix_b.write_text(
        "student_id,Q1,Q2,Q3,total\n040100010,0,0,0,0\n",
        encoding="utf-8",
    )
    entry = RegistryEntry(
        short_name="exam1",
        scores_path=tmp_path / "x.csv",
        breakdown=(matrix_a, matrix_b),
        kind="exam",
    )
    rows = _exam_rows()  # 040100020 → 40.0, 040100010 → 0.0
    md = render_assignment_page(entry, schema_378, rows)
    # Both form-labeled grids appear
    assert "Form A" in md
    assert "Form B" in md
    # Form A has Q1,Q2; Form B has Q1,Q2,Q3
    assert "Q1" in md and "Q2" in md and "Q3" in md
    # Both grids are collapsible callouts
    assert md.count("Per-question grid") == 2

    # reconcile: both students covered — no false-positive flags; both lists empty
    result = reconcile_assignment(entry, rows)
    assert result["mismatches"] == []
    assert result["reconciling"] == []


# ── NEW: dict-shape + render callout routing ──────────────────────────────────

def test_reconcile_mismatch_vs_reconciling_routing(tmp_path, schema_378):
    """A value mismatch lands in mismatches; a no-show (recorded/no grid row) lands
    in reconciling; the two buckets are independent."""
    # 040100020: grid says 41, recorded says 40 → value mismatch
    # 040100010: recorded 0.0 but absent from matrix → reconciling item (no-show)
    matrix = tmp_path / "item_scores_A.csv"
    matrix.write_text(
        "student_id,Q1,Q2,total\n040100020,20,21,41\n",
        encoding="utf-8",
    )
    entry = RegistryEntry(short_name="exam1", scores_path=tmp_path / "x.csv",
                          breakdown=(matrix,), kind="exam")
    result = reconcile_assignment(entry, _exam_rows())
    # 040100020 grid 41 ≠ recorded 40 → mismatches
    assert any("040100020" in m and "41" in m for m in result["mismatches"])
    # 040100010 in recorded but not in grid → reconciling
    assert any("040100010" in r and "recorded but no grid row" in r for r in result["reconciling"])
    # Sanity: buckets don't bleed
    assert not any("040100010" in m for m in result["mismatches"])
    assert not any("040100020" in r for r in result["reconciling"])


def test_render_page_only_reconciling_items_uses_note_not_danger(tmp_path, schema_378):
    """When there are only reconciling items (no value mismatches), the page emits
    the [!note] callout and NO [!danger] callout."""
    # 040100020: grid total matches recorded (40 = 40) — balanced
    # 040100010: recorded 0.0 but absent from matrix — reconciling item only
    matrix = tmp_path / "item_scores_A.csv"
    matrix.write_text(
        "student_id,Q1,Q2,total\n040100020,20,20,40\n",
        encoding="utf-8",
    )
    entry = RegistryEntry(short_name="exam1", scores_path=tmp_path / "x.csv",
                          breakdown=(matrix,), kind="exam")
    md = render_assignment_page(entry, schema_378, _exam_rows())
    assert "[!note]" in md and "Reconciling items" in md
    assert "[!danger]" not in md
