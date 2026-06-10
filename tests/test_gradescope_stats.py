import json
from pathlib import Path
import pytest
from lectern.gradescope_stats import (
    parse_grading_note, join_key, norm, read_eval, exam_summary,
    compute_stats, render_markdown, render_html, link_into_grading_note,
    main as stats_main,
)

NOTE = """\
---
type: grading-note
---
#### A·Q1 · CIA — availability · 2 pts · MC

| Pts | Key | Rubric item (paste into Gradescope) |
| --: | --- | --- |
| 0 | `A·Q1·a` | (a) Confidentiality |
| +2 | `A·Q1·b` | (b) Availability |
| 0 | `A·Q1·c` | (c) Integrity |
| 0 | `A·Q1·none` | No answer / multiple marks |

#### A·Q2 · FIB — DES/AES key sizes · 2 pts · FIB

| Pts | Key | Rubric item (paste into Gradescope) |
| --: | --- | --- |
| +1 | `A·Q2·b1` | blank 1 = “56” |
| +1 | `A·Q2·b2` | blank 2 = “128” |
| 0 | `A·Q2·none` | No answer / multiple marks |
"""

EVAL_HEADER = ("Assignment Submission ID,Question Submission ID,First Name,Last Name,"
               "SID,Email,Sections,Score,Submission Time,")


def _eval(path, item_cols, rows):
    """rows: list of (subid, sid, score, [bool per item col])."""
    head = EVAL_HEADER + ",".join(item_cols) + ",Adjustment,Comments,Grader,Tags"
    lines = [head]
    for subid, sid, score, bools in rows:
        cells = [str(subid), "0", "First", "Last", sid, "e@x", "Sec", str(score),
                 "2026-06-09 11:00:00 -0700"]
        cells += ["true" if b else "false" for b in bools]
        cells += ["", "", "Grader", ""]
        lines.append(",".join(cells))
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


@pytest.fixture
def note_file(tmp_path):
    p = tmp_path / "GRADING_NOTE.md"
    p.write_text(NOTE, encoding="utf-8")
    return p


# ── parsing + join ──────────────────────────────────────────────────────────

def test_parse_grading_note(note_file):
    note = parse_grading_note(note_file)
    assert set(note["A"]) == {1, 2}
    assert note["A"][1]["name"] == "CIA — availability"
    assert note["A"][1]["pts"] == 2 and note["A"][1]["type"] == "MC"
    assert ("+2", "A·Q1·b", "(b) Availability") in note["A"][1]["items"]


def test_join_key_exact_letter_none_order():
    km = {norm("(b) Availability"): ("+2", "A·Q1·b"),
          norm("No answer / multiple marks"): ("0", "A·Q1·none")}
    assert join_key("(b) Availability", km) == ("+2", "A·Q1·b")          # exact
    assert join_key("(b) Availabilty (typo)", km)[1] == "A·Q1·b"         # letter
    assert join_key("Both / No marks / Unknown", km)[1] == "A·Q1·none"   # none bucket
    assert join_key("blank 1 = \"x\" (incorrect)", km)[1].endswith("·order")
    assert join_key("totally unmatched", km) == ("0", "?")


# ── eval reader ─────────────────────────────────────────────────────────────

def test_read_eval_counts_and_skips(tmp_path):
    cols = ["(a) Confidentiality", "(b) Availability", "(c) Integrity", "No answer / multiple marks"]
    p = tmp_path / "1.csv"
    _eval(p, cols, [
        (101, "895444082", 2.0, [False, True, False, False]),   # correct
        (102, "208051944", 0.0, [False, False, True, False]),   # wrong (c)
        ("Rubric Numbers", "", 1.2, [False, False, False, False]),  # legend row → skip
    ])
    n, pairs, scores, anom, skipped = read_eval(p, 2)
    assert n == 2 and skipped == 1 and anom == []
    counts = dict(pairs)
    assert counts["(b) Availability"] == 1 and counts["(c) Integrity"] == 1


def test_read_eval_flags_anomaly(tmp_path):
    cols = ["(b) Availability", "No answer / multiple marks"]
    p = tmp_path / "1.csv"
    _eval(p, cols, [(101, "895444082", 23.2, [True, False])])   # 23.2 on a 2-pt Q
    n, pairs, scores, anom, skipped = read_eval(p, 2)
    assert n == 0 and anom and anom[0][1] == 23.2


# ── exam summary ────────────────────────────────────────────────────────────

def test_exam_summary(tmp_path):
    p = tmp_path / "scores.csv"
    p.write_text(
        "last,first,sid,version,score,status\n"
        "Brown,Stephanie,895444082,A,45.0,Graded\n"     # 90% → A
        "Doe,Jane,208051944,B,35.0,Graded\n"      # 70% → C
        "Zsasz,Victoria,318476936,A,15.0,Graded\n"     # 30% → F
        "Fox,Lucius,406974877,A,,No-show\n",   # excluded
        encoding="utf-8")
    s = exam_summary(p, 50)
    assert s["n"] == 3 and s["maxpts"] == 50
    assert s["dist"] == {"A": 1, "C": 1, "F": 1}
    assert s["form_means"]["A"] == 30.0 and s["form_means"]["B"] == 35.0


# ── end-to-end compute_stats + emitters ─────────────────────────────────────

@pytest.fixture
def stats_tree(tmp_path, note_file):
    ev = tmp_path / "stats"
    (ev / "groupA").mkdir(parents=True)
    _eval(ev / "groupA" / "1_cia.csv",
          ["(a) Confidentiality", "(b) Availability", "(c) Integrity", "No answer / multiple marks"],
          [(1, "895444082", 2.0, [False, True, False, False]),
           (2, "208051944", 2.0, [False, True, False, False]),
           (3, "318476936", 0.0, [False, False, True, False])])
    # FIB Q2 with all scores 0 but key items applied → miskey alarm
    _eval(ev / "groupA" / "2_fib.csv",
          ['blank 1 = "56"', 'blank 2 = "128"', "No answer / multiple marks"],
          [(1, "895444082", 0.0, [True, True, False]),
           (2, "208051944", 0.0, [True, False, False])])
    scores = tmp_path / "scores.csv"
    scores.write_text("last,first,sid,version,score,status\n"
                      "Brown,Stephanie,895444082,A,2.0,Graded\n", encoding="utf-8")
    return ev, note_file, scores


def test_compute_stats_flags(stats_tree):
    ev, note, scores = stats_tree
    s = compute_stats(ev, note, scores, {"course": "CECS 378", "exam": "Exam 1"})
    q1 = next(q for q in s["forms"]["A"] if q["n"] == 1)
    assert q1["nrows"] == 3 and q1["p"] == round(2/3, 2)         # 2 of 3 correct
    key = next(d for d in q1["distractors"] if d["is_key"])
    assert key["key"] == "A·Q1·b" and key["n"] == 2
    assert any(d["dead"] for d in q1["distractors"])             # (a) chosen by 0
    q2 = next(q for q in s["forms"]["A"] if q["n"] == 2)
    assert q2["miskey"] is True                                  # key applied, mean 0


def test_render_markdown_and_html(stats_tree):
    ev, note, scores = stats_tree
    s = compute_stats(ev, note, scores, {"course": "CECS 378", "exam": "Exam 1"})
    md = render_markdown(s)
    assert "type: item-analysis" in md and "Difficulty summary" in md
    assert "Rubric point-value error" in md                      # miskey danger fired
    assert "`A·Q1·b`" in md
    html = render_html(s)
    assert "__DATA__" not in html
    import re
    m = re.search(r'type="application/json">(.*?)</script>', html, re.S)
    assert json.loads(m.group(1).replace("<\\/", "</"))["meta"]["exam"] == "Exam 1"


def test_link_into_grading_note_idempotent(note_file):
    assert link_into_grading_note(note_file, "ITEM_ANALYSIS.md", "item_analysis.html") is True
    assert "Post-exam statistics" in note_file.read_text()
    assert link_into_grading_note(note_file, "ITEM_ANALYSIS.md", "item_analysis.html") is False


def test_read_eval_student_scores(tmp_path):
    from lectern.gradescope_stats import read_eval_student_scores
    cols = ["(a) X", "(b) Y", "No answer / multiple marks"]
    p = tmp_path / "1.csv"
    _eval(p, cols, [
        (101, "895444082", 2.0, [False, True, False]),
        (102, "30611852", 0.0, [True, False, False]),       # short SID → padded
        ("Rubric Numbers", "", 1.2, [False, False, False]),  # legend → skip
    ])
    got = read_eval_student_scores(p)
    assert got == {"895444082": 2.0, "208051944": 0.0}


def test_emit_item_scores(tmp_path):
    from lectern.gradescope_stats import emit_item_scores
    ev = tmp_path / "stats"; (ev / "groupA").mkdir(parents=True)
    _eval(ev / "groupA" / "1_q1.csv", ["(a) X", "(b) Y"],
          [(1, "895444082", 2.0, [False, True])])
    _eval(ev / "groupA" / "2_q2.csv", ["(a) X", "(b) Y"],
          [(1, "895444082", 3.0, [True, False])])
    out = tmp_path / "out"; out.mkdir()
    written = emit_item_scores(ev, out)
    text = (out / "item_scores_A.csv").read_text()
    assert "student_id,Q1,Q2,total" in text
    assert "895444082,2,3,5" in text


def test_cli_end_to_end(stats_tree, tmp_path):
    ev, note, scores = stats_tree
    out = tmp_path / "out"
    rc = stats_main(["--eval-dir", str(ev), "--grading-note", str(note),
                     "--scores", str(scores), "--out-dir", str(out),
                     "--course", "CECS 378", "--exam", "Exam 1"])
    assert rc == 0
    assert (out / "ITEM_ANALYSIS.md").exists()
    assert (out / "item_analysis.html").exists()
    assert (out / "item_analysis.json").exists()
