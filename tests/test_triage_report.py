def test_ledger_flags_bot_commits(tmp_path, mk_repo):
    from lectern.triage_signals import RepoFacts
    repo = mk_repo(tmp_path, [("2026-03-01T10:00:00", {"a.c": "1"})])
    facts = RepoFacts.from_repo(repo)
    assert facts.ledger, "ledger should not be empty"
    entry = facts.ledger[0]
    assert entry.sha and entry.subject          # has a short sha and a subject line
    assert entry.iso.startswith("2026-03-01")   # author date, ISO
    assert entry.is_bot in (True, False)         # bot flag present


def test_deliverable_forensics_detects_late_makefile(tmp_path, mk_repo):
    from lectern.triage_report import deliverable_forensics
    repo = mk_repo(tmp_path, [
        ("2026-05-16T01:48:00", {"a.c": "x"}),                      # grading commit, no makefile
        ("2026-05-20T14:19:00", {"a.c": "x", "makefile": "all:"}),  # added later
    ])
    res = deliverable_forensics(
        repo,
        [{"name": "makefile", "match": "makefile", "required": True, "auto_zero": True}],
        grading_ref="HEAD~1",
    )
    mk = res[0]
    assert mk["present_at_grading"] is False
    assert mk["first_added_sha"] is not None
    assert mk["triggers_auto_zero"] is True
    assert "git ls-tree" in mk["reproduce"]["presence"]
    assert "git log" in mk["reproduce"]["first_added"]


def test_deliverable_forensics_present_makefile_no_autozero(tmp_path, mk_repo):
    from lectern.triage_report import deliverable_forensics
    repo = mk_repo(tmp_path, [
        ("2026-05-10T10:00:00", {"a.c": "x", "makefile": "all:"}),
        ("2026-05-12T10:00:00", {"a.c": "xy", "makefile": "all:\n\tgcc"}),
    ])
    res = deliverable_forensics(
        repo,
        [{"name": "makefile", "match": "makefile", "required": True, "auto_zero": True}],
        grading_ref="HEAD",
    )
    mk = res[0]
    assert mk["present_at_grading"] is True
    assert mk["triggers_auto_zero"] is False


def test_forensics_reproduce_command_is_runnable_for_glob(tmp_path, mk_repo):
    import subprocess
    from lectern.triage_report import deliverable_forensics
    repo = mk_repo(tmp_path, [("2026-05-10T10:00:00", {"main.c": "x", "notes.txt": "y"})])
    res = deliverable_forensics(repo, [{"name": "sources", "match": "*.c"}], grading_ref="HEAD")
    cmd = res[0]["reproduce"]["presence"].replace("<repo>", str(repo))
    out = subprocess.run(cmd, shell=True, capture_output=True, text=True).stdout
    assert "main.c" in out and "notes.txt" not in out   # glob reproduce really matches *.c only
    assert "'*.c'" not in res[0]["reproduce"]["presence"]  # raw glob no longer used as grep arg


# ---------------------------------------------------------------------------
# Task 12 — render_report (Part A/B/C assembler)
# ---------------------------------------------------------------------------

def _report_inputs(tmp_path, mk_repo):
    from lectern.triage_signals import RepoFacts
    from lectern.triage_report import deliverable_forensics
    repo = mk_repo(tmp_path, [
        ("2026-05-16T01:48:00", {"a.c": "x"}),
        ("2026-05-20T14:19:00", {"a.c": "x", "Makefile": "all:"}),
    ])
    facts = RepoFacts.from_repo(repo)
    forensics = deliverable_forensics(
        repo, [{"name": "makefile", "match": "makefile", "required": True, "auto_zero": True}],
        grading_ref="HEAD~1")
    cfg = {"assignment": {"name": "Lab 02 — Semaphores", "course": "CECS 326",
                          "section": "99", "org": "Giacalone-CECS",
                          "repo_prefix": "cecs-326-sp26-99-lab-02-semaphores-"},
           "profile": "short-project", "thresholds": {"pass": 60, "flag": 20},
           "weights": {"spread_days": 20}, "schema_version": 1, "engine_sha": "abc1234567"}
    student = {"display_name": "Harley Quinn", "student_id": "000000001",
               "github_username": "harley-quinn"}
    return student, cfg, facts, forensics

def test_render_report_has_three_tiers_and_ssid(tmp_path, mk_repo):
    from lectern.triage_report import render_report
    student, cfg, facts, forensics = _report_inputs(tmp_path, mk_repo)
    md = render_report(student, cfg, facts, forensics,
                       score=(105, "all signals present", "PASS"), release=False)
    assert "Part A" in md and "Part B" in md and "Part C" in md
    assert "000000001" in md                 # SSID present in internal variant
    assert "not proof" in md                  # advisory framing
    assert "Harley Quinn" in md
    assert facts.ledger[0].sha in md          # commit ledger rendered
    assert "triage" in md.lower()

def test_render_report_release_omits_ssid(tmp_path, mk_repo):
    from lectern.triage_report import render_report
    student, cfg, facts, forensics = _report_inputs(tmp_path, mk_repo)
    md = render_report(student, cfg, facts, forensics,
                       score=(105, "all signals present", "PASS"), release=True)
    assert "000000001" not in md              # SSID stripped in release
    assert "Part A" in md and "Part B" in md  # structure intact


# ---------------------------------------------------------------------------
# Task 13 — sanitize_release + render_report release sanitization
# ---------------------------------------------------------------------------

def test_sanitize_release_strips_wikilinks_and_callouts():
    from lectern.triage_report import sanitize_release
    raw = "See [[notes/foo|the note]] and [[bar]].\n> [!warning] heads up\nplain"
    out = sanitize_release(raw)
    assert "[[" not in out and "]]" not in out
    assert "the note" in out and "bar" in out
    assert "[!warning]" not in out and "heads up" in out


def test_render_report_release_is_sanitized(tmp_path, mk_repo):
    from lectern.triage_report import render_report
    student, cfg, facts, forensics = _report_inputs(tmp_path, mk_repo)
    cfg = {**cfg, "assignment": {**cfg["assignment"], "name": "Lab [[secret]] 02"}}
    md = render_report(student, cfg, facts, forensics, score=(105, "x", "PASS"), release=True)
    assert "[[" not in md and "000000001" not in md
