from lectern.feedback_note import parse_feedback_note, _parse_scoreline

NOTE = """\
---
type: report
---
# Lab 2 — Malware · Cohort Report

Some preamble with a `backtick` and a table that is not a student block.

## Per-student feedback & grades

> [!info] callout — not a student block, has no ### heading

### Bruce Wayne — **__ / 100**
`bwayne` · [repo](https://github.com/Giacalone-CECS/cecs-378-su26-01-lab-03-malware-bwayne)
ROM __/33 · IPS __/8 · Screenshots __/17 · Writeup __/42 · ACE +__/15

_Comments:_ <!-- fill in as graded -->

### Selina Kyle — **91 / 100**
`skyle` · [repo](https://example.com/skyle)
ROM 30/33 · IPS 8/8 · Screenshots 15/17 · Writeup 38/42 · ACE +0/15

_Comments:_ You lifted those sprite bytes like a diamond from a locked case — clean and gone before the alarm tripped.
The offset table purrs; nine lives, mostly well spent.

### Floyd Lawton — **0 / 100**
`flawton` · [repo](https://example.com/flawton)
ROM 0/33 · IPS 0/8 · Screenshots 0/17 · Writeup 0/42 · ACE +0/15

_Comments:_ You never miss a shot, Deadshot — except this deadline. Nothing on record to grade.

### Edward Nygma — **88 / 100**
`enygma` · [repo](https://example.com/enygma)
ROM 30/33 · IPS 8/8 · Screenshots 14/17 · Writeup 36/42 · ACE +0/15

_Comments:_ Riddle me this: 88 points, every hex offset solved, writeup at `WRITEUP.md` (non-standard path) — a puzzle you answered instead of leaving for me.

## Provenance
not a student block.
"""


def _write(tmp_path):
    p = tmp_path / "REPORT.md"
    p.write_text(NOTE)
    return str(p)


def test_parses_one_row_per_student_block(tmp_path):
    rows = parse_feedback_note(_write(tmp_path))
    assert [r["github_id"] for r in rows] == ["bwayne", "skyle", "flawton", "enygma"]


def test_ungraded_block_flagged_not_graded(tmp_path):
    rows = {r["github_id"]: r for r in parse_feedback_note(_write(tmp_path))}
    assert rows["bwayne"]["graded"] is False and rows["bwayne"]["total"] is None
    assert rows["skyle"]["graded"] is True and rows["skyle"]["total"] == 91


def test_components_parsed_with_ec_and_max(tmp_path):
    sk = {r["github_id"]: r for r in parse_feedback_note(_write(tmp_path))}["skyle"]
    labels = [(c["label"], c["score"], c["max"], c["ec"]) for c in sk["components"]]
    assert labels == [("ROM", 30, 33, False), ("IPS", 8, 8, False),
                      ("Screenshots", 15, 17, False), ("Writeup", 38, 42, False),
                      ("ACE", 0, 15, True)]
    assert sk["grand"] == 100


def test_multiline_comment_captured_and_html_stripped(tmp_path):
    rows = {r["github_id"]: r for r in parse_feedback_note(_write(tmp_path))}
    assert "nine lives" in rows["skyle"]["comment"]   # second line carried over
    assert rows["bwayne"]["comment"] == ""            # HTML comment stripped to empty


def test_gid_not_confused_by_backticks_in_comment(tmp_path):
    # Edward's comment contains `WRITEUP.md` in backticks; the gid must stay enygma.
    rows = {r["github_id"]: r for r in parse_feedback_note(_write(tmp_path))}
    assert "enygma" in rows and rows["enygma"]["total"] == 88


def test_scoreline_rejects_non_score_lines():
    assert _parse_scoreline("`skyle` · [repo](https://x/y)") is None
    assert _parse_scoreline("ROM 30/33 · IPS 8/8")[0]["label"] == "ROM"
