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


def test_head_with_trailing_suffix_parses(tmp_path):
    # Regression: _HEAD anchored on `**$`, so a head with content after the
    # closing `**` (e.g. an at-a-glance `· ACE +N/15`) silently failed to match
    # — the block was skipped and the student vanished from delivery with NO
    # error. The required `**<total> / <grand>**` must parse regardless of any
    # trailing suffix.
    note = (
        "## Per-student feedback & grades\n\n"
        "### Harvey Dent — **96 / 100**  ·  ACE +14/15\n"
        "`hdent` · [repo](https://example.com/hdent)\n"
        "ROM 33/33 · IPS 8/8 · Screenshots 17/17 · Writeup 38/42 · ACE +14/15\n\n"
        "_Comments:_ Flawless on the machine slice, generous on the bonus.\n\n"
        "## Provenance\n"
    )
    p = tmp_path / "REPORT.md"
    p.write_text(note)
    rows = {r["github_id"]: r for r in parse_feedback_note(str(p))}
    assert "hdent" in rows, "trailing-suffix head was skipped (the regression)"
    assert rows["hdent"]["total"] == 96 and rows["hdent"]["grand"] == 100
    assert rows["hdent"]["graded"] is True
    assert rows["hdent"]["components"][-1] == {"label": "ACE", "score": 14,
                                               "max": 15, "ec": True}


# The block shape `reg-lab-report render` writes (lectern/report_render.py).
RENDERED = """\
## Per-student feedback & grades

> [!note] callout under the section heading, not a student block

### bwayne — **51 / 60**
*github: [`bwayne`](https://example.com/bwayne) · Auto 45/45 · Writeup 6/15 · [Feedback PR](https://example.com/bwayne/pull/1)*

> Your code now builds.
> Q1 needs the full trace: `x = x + 1` is three steps.
>
> Come to office hours.

<!-- internal: forensic notes, never shipped -->

### skyle — **__ / 60**
*github: [`skyle`](https://example.com/skyle) · Auto 45/45 · Writeup __/15*

> _Comments:_ 

### flawton — **0 / 60**
*github: `flawton` · Auto 0/45 · Writeup 0/15*

> _no submission_

## Canvas entry sheet
"""


def _rendered(tmp_path):
    p = tmp_path / "RENDERED.md"
    p.write_text(RENDERED)
    return {r["github_id"]: r for r in parse_feedback_note(str(p))}


def test_rendered_block_components_and_comment(tmp_path):
    bw = _rendered(tmp_path)["bwayne"]
    assert bw["graded"] is True and (bw["total"], bw["grand"]) == (51, 60)
    assert [(c["label"], c["score"], c["max"]) for c in bw["components"]] == [
        ("Auto", 45, 45), ("Writeup", 6, 15)]
    assert bw["comment"] == ("Your code now builds.\n"
                             "Q1 needs the full trace: `x = x + 1` is three steps.\n\n"
                             "Come to office hours.")
    assert "internal" not in bw["comment"]


def test_rendered_placeholder_and_non_submission(tmp_path):
    rows = _rendered(tmp_path)
    assert rows["skyle"]["graded"] is False and rows["skyle"]["comment"] == ""
    assert rows["flawton"]["comment"] == ""
    assert rows["flawton"]["components"][0]["label"] == "Auto"


def test_scoreline_decoration_only_skipped_on_rendered_lines():
    assert _parse_scoreline("*github: [`x`](u) · Auto 1/2 · [Feedback PR](p)*") == [
        {"label": "Auto", "score": 1, "max": 2, "ec": False}]
    # Prose with a `·` still is not a score line.
    assert _parse_scoreline("Nice work · see the notes below") is None
    assert _parse_scoreline("github: me") is None   # decoration alone carries no scores


def test_plain_comment_keeps_its_own_quote(tmp_path):
    p = tmp_path / "Q.md"
    p.write_text("### A — **5 / 10**\n`a1` · [repo](u)\nScore 5/10\n"
                 "_Comments:_ You wrote:\n> it works\nwhich is not a mechanism.\n")
    assert "> it works" in parse_feedback_note(str(p))[0]["comment"]
