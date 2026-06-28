import os

from lectern.feedback_deliver import (render_feedback_md, render_feedback_md_from_note,
                                       deliver, MERGE_MSG)
from lectern.report_manifest import ReportManifest

M = ReportManifest("CECS 378", "01", "su26", "Lab 1", "Giacalone-CECS",
                   "cecs-378-su26-01-lab-01-symmetric-crypto", 70, 30, [], {}, 1.0, "feedback", 1)

# Note-authoritative manifest: grand/components come from the note, not auto/writeup.
MN = ReportManifest("CECS 378", "01", "su26", "Lab 2 — Malware", "Giacalone-CECS",
                    "cecs-378-su26-01-lab-03-malware", 0, 0, [], {}, 1.0, "feedback", 1)


def note_row(**k):
    base = dict(github_id="skyle", student="Selina Kyle", total=91, grand=100,
                components=[{"label": "ROM", "score": 30, "max": 33, "ec": False},
                            {"label": "Writeup", "score": 38, "max": 42, "ec": False},
                            {"label": "ACE", "score": 0, "max": 15, "ec": True}],
                comment="You lifted those sprite bytes like a diamond from a locked case — "
                        "clean, quiet, and gone before the alarm. The offset table purrs.",
                graded=True)
    base.update(k)
    return base


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


# --- note-authoritative path (--from-note) ---

def test_from_note_render_has_all_components_and_ec():
    md = render_feedback_md_from_note(note_row(), MN)
    assert "Lab 2 — Malware — Feedback" in md and "91 / 100" in md
    assert "| ROM | 30 / 33 |" in md and "| Writeup | 38 / 42 |" in md
    assert "| ACE (extra credit) | +0 / 15 |" in md
    assert "the offset table purrs" in md.lower()


def test_from_note_zero_total_gets_non_submission_note():
    md = render_feedback_md_from_note(
        note_row(github_id="flawton", student="Floyd Lawton", total=0,
                 components=[{"label": "ROM", "score": 0, "max": 33, "ec": False}],
                 comment="You never miss a shot — except this deadline."), MN)
    assert "No submission" in md and "0 / 100" in md


def test_deliver_uses_injected_renderer_and_note_total(tmp_path):
    # deliver must read total from the note row and render via the from-note renderer
    entries = deliver([note_row()], MN, str(tmp_path), execute=False,
                      render=render_feedback_md_from_note, gh=lambda *a, **k: None,
                      git=lambda *a, **k: None)
    assert entries[0]["total"] == 91 and entries[0]["grand"] == 100
    assert entries[0]["components"][0]["label"] == "ROM"
    assert "offset table purrs" in entries[0]["student_comment"]


def test_deliver_from_note_executes_signed(tmp_path):
    gid = "skyle"
    os.makedirs(tmp_path / gid)
    gcalls = []
    git = make_git(gcalls)
    gh = make_gh([])
    entries = deliver([note_row()], MN, str(tmp_path), execute=True,
                      render=render_feedback_md_from_note, git=git, gh=gh)
    # writes FEEDBACK.md to the malware repo's feedback branch, signed
    assert any(c[:4] == ("git", "-C", str(tmp_path / gid), "commit") and "-S" in c for c in gcalls)
    assert entries[0]["posted"] is True and entries[0]["main_state"] == "merged"


def test_default_gh_git_callbacks_prepend_binary(monkeypatch):
    # Regression: deliver()'s default callbacks were bare `_sh`, so `gh("repo",
    # "clone", …)` shelled out to a program literally named `repo` (FileNotFound)
    # and `git(...)` to one named `-C`. The --execute path therefore never worked;
    # tests masked it by always injecting gh=/git= mocks. The defaults must wrap
    # _sh with the binary name.
    import inspect, types
    import lectern.feedback_deliver as fd
    calls = []
    monkeypatch.setattr(fd.subprocess, "run",
                        lambda args, **k: (calls.append(list(args)),
                                           types.SimpleNamespace(stdout="", stderr="", returncode=0))[1])
    fd._gh("repo", "clone", "org/r", "/d")
    fd._git("-C", "/d", "status")
    assert calls[0][:2] == ["gh", "repo"]
    assert calls[1][:2] == ["git", "-C"]
    sig = inspect.signature(fd.deliver)
    assert sig.parameters["gh"].default is fd._gh, "deliver default gh must wrap the gh binary"
    assert sig.parameters["git"].default is fd._git, "deliver default git must wrap the git binary"


def test_execute_skips_unclonable_repo_and_continues(tmp_path):
    # A non-submission repo that doesn't exist: gh clone returns non-zero (and no
    # dest dir). deliver must record it as no-repo and CONTINUE to the next repo,
    # not abort the whole cohort run (the crash hit live on the Lab 2 delivery).
    import os as _os
    _os.makedirs(tmp_path / "skyle")
    def gh(*a, **k):
        if a[:2] == ("repo", "clone") and str(a[2]).endswith("-bwayne"):
            return _R("Could not resolve to a Repository", 1)
        return _R("", 0)
    gcalls = []
    git = make_git(gcalls)
    entries = deliver([row(), row(github_id="skyle", student="Selina Kyle")],
                      M, str(tmp_path), execute=True, gh=gh, git=git)
    by = {e["github_id"]: e for e in entries}
    assert by["bwayne"]["main_state"] == "no-repo" and by["bwayne"]["posted"] is False
    assert by["skyle"]["posted"] is True   # run continued; next repo delivered
