import os

from lectern.feedback_deliver import render_feedback_md, deliver, MERGE_MSG
from lectern.report_manifest import ReportManifest

M = ReportManifest("CECS 378", "01", "su26", "Lab 1", "Giacalone-CECS",
                   "cecs-378-su26-01-lab-01-symmetric-crypto", 70, 30, [], {}, 1.0, "feedback", 1)


def row(**k):
    base = dict(github_id="bwayne", student="Bruce Wayne", points=70,
                writeup_score=30, student_comment="Full clear.", honor_ok=True)
    base.update(k)
    return base


def _R(stdout="", returncode=0):
    return type("R", (), {"stdout": stdout, "stderr": "", "returncode": returncode})()


def make_git(calls, *, merge_rc=0, merge_blob="", main_show=("", 1)):
    """Arg-aware fake for the `git` callback.

    main_show=(stdout, rc) controls `git show main:FEEDBACK.md` (the
    merge-to-main idempotency probe). show-signature always reports a good sig.
    """
    def f(*a, **k):
        calls.append(("git",) + a)
        if "--show-signature" in a:
            return _R("gpg: Good signature from Anthony")
        if "merge" in a:
            return _R(merge_blob, merge_rc)
        if "show" in a and len(a) > 3 and str(a[3]).endswith(":FEEDBACK.md"):
            out, rc = main_show
            return _R(out, rc)
        return _R("", 0)
    return f


def make_gh(calls, *, state="OPEN"):
    def f(*a, **k):
        calls.append(("gh",) + a)
        if a[:2] == ("pr", "view"):
            return _R(state)
        return _R("", 0)
    return f


def test_feedback_md_has_breakdown_and_comment():
    md = render_feedback_md(row(), M)
    assert "100 / 100" in md and "70 / 70" in md and "Full clear." in md


def test_dry_run_makes_no_calls(tmp_path):
    calls = []
    fake = lambda *a, **k: calls.append(a) or _R()
    entries = deliver([row()], M, str(tmp_path), execute=False, gh=fake, git=fake)
    assert calls == []                      # nothing remote in dry-run
    assert entries[0]["github_id"] == "bwayne" and entries[0]["posted"] is False


def test_non_submission_gets_neutral_note():
    md = render_feedback_md(row(github_id="flawton", student="Floyd Lawton",
                                points=0, writeup_score=0, student_comment="", honor_ok=False), M)
    assert "No submission" in md and "0 / 100" in md


def test_only_filter(tmp_path):
    fake = lambda *a, **k: _R("OPEN")
    entries = deliver([row(), row(github_id="skyle", student="Selina Kyle")], M, str(tmp_path),
                      execute=False, only=["skyle"], gh=fake, git=fake)
    assert [e["github_id"] for e in entries] == ["skyle"]


# --- merge-to-main (so FEEDBACK.md shows on each student's default branch) ---

def test_execute_merges_feedback_into_main_signed(tmp_path):
    gid = "bwayne"
    os.makedirs(tmp_path / gid)
    gcalls, hcalls = [], []
    git = make_git(gcalls)                       # main lacks file, clean merge
    gh = make_gh(hcalls)
    entries = deliver([row()], M, str(tmp_path), execute=True, git=git, gh=gh)
    # the signed merge of feedback into main, then a push of main
    assert ("git", "-C", str(tmp_path / gid), "merge", "--no-ff", "--no-edit",
            "-S", "feedback", "-m", MERGE_MSG) in gcalls
    assert ("git", "-C", str(tmp_path / gid), "push", "origin", "main") in gcalls
    assert entries[0]["main_state"] == "merged"


def test_execute_unrelated_history_lands_file_directly(tmp_path):
    gid = "bwayne"
    os.makedirs(tmp_path / gid)
    gcalls = []
    git = make_git(gcalls, merge_rc=1, merge_blob="fatal: refusing to merge unrelated histories")
    gh = make_gh([])
    entries = deliver([row()], M, str(tmp_path), execute=True, git=git, gh=gh)
    # no merge commit survived; instead a direct signed add on main, then push
    assert any(c[:4] == ("git", "-C", str(tmp_path / gid), "commit") and "-S" in c
               and c[-1] == "Add FEEDBACK.md (grade + comments)" for c in gcalls)
    assert ("git", "-C", str(tmp_path / gid), "push", "origin", "main") in gcalls
    assert entries[0]["main_state"] == "added"


def test_execute_merge_idempotent_when_main_already_has_file(tmp_path):
    gid = "bwayne"
    os.makedirs(tmp_path / gid)
    md = render_feedback_md(row(), M)
    gcalls = []
    git = make_git(gcalls, main_show=(md, 0))    # main already carries the exact file
    gh = make_gh([])
    entries = deliver([row()], M, str(tmp_path), execute=True, git=git, gh=gh)
    assert not any("merge" in c for c in gcalls)
    assert ("git", "-C", str(tmp_path / gid), "push", "origin", "main") not in gcalls
    assert entries[0]["main_state"] == "unchanged"


def test_merge_main_false_leaves_main_untouched(tmp_path):
    gid = "bwayne"
    os.makedirs(tmp_path / gid)
    gcalls = []
    git = make_git(gcalls)
    gh = make_gh([])
    entries = deliver([row()], M, str(tmp_path), execute=True, merge_main=False, git=git, gh=gh)
    assert not any("merge" in c for c in gcalls)
    assert ("git", "-C", str(tmp_path / gid), "checkout", "main") not in gcalls
    assert entries[0]["main_state"] == "-"
