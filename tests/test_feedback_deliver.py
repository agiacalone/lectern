from lectern.feedback_deliver import render_feedback_md, deliver
from lectern.report_manifest import ReportManifest

M = ReportManifest("CECS 378", "01", "su26", "Lab 1", "Giacalone-CECS",
                   "cecs-378-su26-01-lab-01-symmetric-crypto", 70, 30, [], {}, 1.0, "feedback", 1)


def row(**k):
    base = dict(github_id="gh-user-06", student="Selina Kyle", points=70,
                writeup_score=30, student_comment="Full clear.", honor_ok=True)
    base.update(k)
    return base


def test_feedback_md_has_breakdown_and_comment():
    md = render_feedback_md(row(), M)
    assert "100 / 100" in md and "70 / 70" in md and "Full clear." in md


def test_dry_run_makes_no_calls(tmp_path):
    calls = []
    fake = lambda *a, **k: calls.append(a) or type("R", (), {"stdout": "", "returncode": 0})()
    entries = deliver([row()], M, str(tmp_path), execute=False, gh=fake, git=fake)
    assert calls == []                      # nothing remote in dry-run
    assert entries[0]["github_id"] == "gh-user-06" and entries[0]["posted"] is False


def test_non_submission_gets_neutral_note():
    md = render_feedback_md(row(github_id="gh-user-04", student="Stephanie Brown",
                                points=0, writeup_score=0, student_comment="", honor_ok=False), M)
    assert "No submission" in md and "0 / 100" in md


def test_only_filter(tmp_path):
    fake = lambda *a, **k: type("R", (), {"stdout": "OPEN", "returncode": 0})()
    entries = deliver([row(), row(github_id="gh-user-09", student="John B")], M, str(tmp_path),
                      execute=False, only=["gh-user-09"], gh=fake, git=fake)
    assert [e["github_id"] for e in entries] == ["gh-user-09"]
