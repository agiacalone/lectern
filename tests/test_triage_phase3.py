"""Tests for Phase 3 triage signal-set versioning discipline."""


def test_crunch_rewards_sustained_effort_term_project(tmp_path, mk_repo):
    from lectern.triage_signals import RepoFacts, crunch_signal
    d = tmp_path / "s"; d.mkdir()
    spread = mk_repo(d, [(f"2026-0{m}-15T10:00:00", {"a.c": "x"*m}) for m in range(1, 6)])
    facts = RepoFacts.from_repo(spread)
    cfg = {"assignment": {"assigned_date": "2026-01-01", "due_date": "2026-05-31"},
           "weights": {"crunch": 10}}
    res = crunch_signal(facts, cfg)
    assert res.present is True and res.points == 10

def test_crunch_silent_on_deadline_compression(tmp_path, mk_repo):
    from lectern.triage_signals import RepoFacts, crunch_signal
    d = tmp_path / "c"; d.mkdir()
    crammed = mk_repo(d, [
        ("2026-05-29T10:00:00", {"a.c": "x"}), ("2026-05-30T11:00:00", {"a.c": "xy"}),
        ("2026-05-31T12:00:00", {"a.c": "xyz"})])
    facts = RepoFacts.from_repo(crammed)
    cfg = {"assignment": {"assigned_date": "2026-01-01", "due_date": "2026-05-31"},
           "weights": {"crunch": 10}}
    res = crunch_signal(facts, cfg)
    assert res.present is False and res.points == 0

def test_crunch_only_applies_to_term_project():
    from lectern.triage_signals import SIGNALS
    _fn, _w, profiles = SIGNALS["crunch"]
    assert profiles == {"term-project"}

def test_crunch_absent_when_no_dates(tmp_path, mk_repo):
    from lectern.triage_signals import RepoFacts, crunch_signal
    d = tmp_path / "x"; d.mkdir()
    repo = mk_repo(d, [("2026-03-01T10:00:00", {"a.c": "x"})])
    facts = RepoFacts.from_repo(repo)
    res = crunch_signal(facts, {"weights": {"crunch": 10}})   # no assignment dates
    assert res.present is False and res.points == 0


def test_rhythm_fingerprint_and_divergence(tmp_path, mk_repo):
    from lectern.triage_signals import RepoFacts
    from lectern.triage_rhythm import commit_fingerprint, rhythm_divergence
    (tmp_path / "m").mkdir(); (tmp_path / "n").mkdir()
    morning = mk_repo(tmp_path / "m", [(f"2026-03-0{d}T09:00:00", {"a.c": "x"}) for d in range(1, 6)])
    night   = mk_repo(tmp_path / "n", [(f"2026-04-0{d}T23:00:00", {"a.c": "x"}) for d in range(1, 6)])
    fp_m = commit_fingerprint(RepoFacts.from_repo(morning))
    fp_n = commit_fingerprint(RepoFacts.from_repo(night))
    assert len(fp_m) == 24 and abs(sum(fp_m) - 1.0) < 1e-9
    same = rhythm_divergence([fp_m, fp_m])
    diff = rhythm_divergence([fp_m, fp_n])
    assert same < 0.05 and diff > 0.8

def test_rhythm_subcommand_writes_advisory(tmp_path, mk_repo):
    from lectern.triage import main
    (tmp_path / "a").mkdir(); (tmp_path / "b").mkdir()
    a = mk_repo(tmp_path / "a", [("2026-03-01T09:00:00", {"x.c": "1"})])
    b = mk_repo(tmp_path / "b", [("2026-04-01T09:00:00", {"x.c": "1"})])
    out = tmp_path / "rhythm.md"
    rc = main(["rhythm", "--student", "jdoe", "--repos", str(a), str(b), "--out", str(out)])
    assert rc == 0 and out.exists()
    body = out.read_text().lower()
    assert "advisory" in body and "not proof" in body and "jdoe" in body

def test_rhythm_divergence_empty_safe():
    from lectern.triage_rhythm import rhythm_divergence
    assert rhythm_divergence([]) == 0.0
    assert rhythm_divergence([[0.0]*24]) == 0.0   # single fingerprint, nothing to compare


def test_fingerprint_uses_local_commit_hour(tmp_path, mk_repo):
    from lectern.triage_signals import RepoFacts
    from lectern.triage_rhythm import commit_fingerprint
    (tmp_path / "lr").mkdir()
    # Commit authored at 22:00 local (-05:00) — UTC equivalent is 03:00 next day.
    # Correct bucketing must land in bucket 22 (local), not bucket 3 (UTC-shifted).
    repo = mk_repo(tmp_path / "lr", [("2026-03-01T22:00:00-05:00", {"a.c": "x"})])
    fp = commit_fingerprint(RepoFacts.from_repo(repo))
    assert fp[22] == 1.0, f"expected bucket 22 == 1.0, got {fp[22]}; full fp: {fp}"


def test_version_constants_are_pinned_in_reports(tmp_path, mk_repo):
    from lectern.triage_version import SCHEMA_VERSION, SIGNAL_SET_VERSION
    assert isinstance(SCHEMA_VERSION, int) and isinstance(SIGNAL_SET_VERSION, int)
    from lectern.triage import write_triage_md
    rows = [{"name": "A", "repo_url": "u", "triage": "PASS", "score": 90, "grade": "", "reasoning": "ok"}]
    cfg = {"assignment": {"name": "L"}, "schema_version": SCHEMA_VERSION,
           "signal_set_version": SIGNAL_SET_VERSION, "profile": "short-project"}
    p = tmp_path / "T.md"
    write_triage_md(rows, p, cfg)
    body = p.read_text()
    assert f"schema_version {SCHEMA_VERSION}" in body
    assert f"signal_set {SIGNAL_SET_VERSION}" in body


# ---------------------------------------------------------------------------
# Task 4: Org-scrape repo discovery (post-GitHub-Classroom seam)
# ---------------------------------------------------------------------------

def test_scrape_filters_repo_names_by_prefix():
    from lectern.triage_scrape import filter_repos_by_prefix
    names = ["cecs-326-sp26-01-lab-02-semaphores-jdoe",
             "cecs-326-sp26-01-lab-02-semaphores-asmith",
             "cecs-326-sp26-01-lab-03-pipes-jdoe",          # different assignment
             "unrelated-repo"]
    keep = filter_repos_by_prefix(names, "cecs-326-sp26-01-lab-02-semaphores-")
    assert keep == ["cecs-326-sp26-01-lab-02-semaphores-jdoe",
                    "cecs-326-sp26-01-lab-02-semaphores-asmith"]


# ---------------------------------------------------------------------------
# Task 5: Term-spec seeding in init
# ---------------------------------------------------------------------------

def test_init_seeds_from_term_spec(tmp_path):
    from lectern.triage import main
    spec = tmp_path / "sp26.spec.yaml"
    spec.write_text(
        "term: sp26\nterm-name: Spring 2026\nyear: 2026\nsemester-code: sp\n"
        "instructor: Anthony Giacalone\nstart: 2026-01-20\nend: 2026-05-08\n"
        "finals-week-start: 2026-05-11\nfinals-week-end: 2026-05-15\n"
        "grade-submission-deadline: 2026-05-21\n"
        "sections:\n  - course: CECS 326\n    section: \"01\"\n    class-number: 1116\n"
        "    room: HC-120\n    meets: \"TuTh 12:30-13:45\"\n    enrolled: 30\n"
        "    final-exam-date: 2026-05-13\n")
    out = tmp_path / "lab.triage.yaml"
    rc = main(["init", "--course", "CECS 326", "--section", "01", "--name", "Lab 02",
               "--term-spec", str(spec), "--out", str(out), "--profile", "term-project"])
    assert rc == 0
    import yaml
    cfg = yaml.safe_load(out.read_text())
    assert cfg["assignment"]["term"] == "sp26"
    assert cfg["assignment"]["assigned_date"] == "2026-01-20"   # seeded from term start
    assert cfg["assignment"]["due_date"] == "2026-05-08"        # seeded from term end
    from lectern.triage_manifest import load_manifest
    assert load_manifest(out)   # still schema-valid

def test_init_without_term_spec_still_works(tmp_path):
    from lectern.triage import main
    out = tmp_path / "x.triage.yaml"
    rc = main(["init", "--course", "CECS 326", "--name", "Lab 02", "--out", str(out),
               "--profile", "short-project"])
    assert rc == 0 and out.exists()


# ---------------------------------------------------------------------------
# Fix 3: crunch engine isolation — short-project vs term-project
# ---------------------------------------------------------------------------

def test_crunch_isolated_from_short_project_at_engine_level(tmp_path, mk_repo):
    from lectern.triage_engine import score_repo, load_profile
    (tmp_path / "r2").mkdir()
    repo = mk_repo(tmp_path / "r2", [(f"2026-0{m}-15T10:00:00", {"a.c": "x"*m}) for m in range(1, 6)])
    base = {"assignment": {"assigned_date": "2026-01-01", "due_date": "2026-05-31", "expected_commits": 5}}
    sp = load_profile("short-project")
    tp = load_profile("term-project")
    _, r_sp, _ = score_repo(repo, {**base, "thresholds": sp["thresholds"], "weights": {**sp["weights"], "crunch": 10}}, profile="short-project")
    _, r_tp, _ = score_repo(repo, {**base, "thresholds": tp["thresholds"], "weights": tp["weights"]}, profile="term-project")
    assert "sustained" not in r_sp and "compressed" not in r_sp   # crunch cannot leak into short-project
    assert "sustained" in r_tp                                     # crunch active in term-project


# ---------------------------------------------------------------------------
# Fix 4: crunch_signal degenerate window guard
# ---------------------------------------------------------------------------

def test_crunch_degenerate_window_returns_not_present(tmp_path, mk_repo):
    from lectern.triage_signals import RepoFacts, crunch_signal
    d = tmp_path / "dw"; d.mkdir()
    repo = mk_repo(d, [("2026-05-01T10:00:00", {"a.c": "x"})])
    facts = RepoFacts.from_repo(repo)
    cfg = {"assignment": {"assigned_date": "2026-05-01", "due_date": "2026-05-01"},
           "weights": {"crunch": 10}}
    res = crunch_signal(facts, cfg)
    assert res.present is False and res.points == 0
    assert "degenerate" in res.evidence


# ---------------------------------------------------------------------------
# Fix 5: discover_scrape_repos raises RuntimeError when gh is absent
# ---------------------------------------------------------------------------

def test_discover_scrape_repos_missing_gh(monkeypatch):
    import subprocess
    from lectern import triage_scrape
    import pytest

    def boom(*a, **k):
        raise FileNotFoundError()

    monkeypatch.setattr(triage_scrape.subprocess, "run", boom)
    with pytest.raises(RuntimeError) as ei:
        triage_scrape.discover_scrape_repos("Giacalone-CECS", "cecs-326-")
    assert "gh" in str(ei.value).lower()


# ---------------------------------------------------------------------------
# Fix 6: source property in manifest schema
# ---------------------------------------------------------------------------

def test_manifest_source_scrape_is_valid(tmp_path):
    from lectern.triage_manifest import load_manifest
    m = tmp_path / "t.triage.yaml"
    m.write_text(
        "assignment:\n"
        "  course: CECS 326\n  section: '01'\n  term: sp26\n  name: Lab 02\n"
        "  org: Giacalone-CECS\n  repo_prefix: cecs-326-sp26-01-lab-02-\n"
        "  assigned_date: '2026-01-20'\n  due_date: '2026-05-08'\n"
        "  total_points: 100\n"
        "profile: short-project\n"
        "source: scrape\n"
    )
    cfg = load_manifest(m)
    assert cfg["source"] == "scrape"


def test_manifest_source_bogus_raises(tmp_path):
    from lectern.triage_manifest import load_manifest, TriageManifestError
    import pytest
    m = tmp_path / "t.triage.yaml"
    m.write_text(
        "assignment:\n"
        "  course: CECS 326\n  section: '01'\n  term: sp26\n  name: Lab 02\n"
        "  org: Giacalone-CECS\n  repo_prefix: cecs-326-sp26-01-lab-02-\n"
        "  assigned_date: '2026-01-20'\n  due_date: '2026-05-08'\n"
        "  total_points: 100\n"
        "profile: short-project\n"
        "source: bogus\n"
    )
    with pytest.raises(TriageManifestError):
        load_manifest(m)
