import os
import subprocess
from pathlib import Path

from lectern.triage_signals import SIGNALS, RepoFacts, SignalResult, deletions_signal, signal, spread_days_signal


def test_registry_collects_decorated_signals():
    @signal(name="dummy", default_weight=10, profiles="all")
    def _dummy(facts, cfg):
        return SignalResult(points=10, evidence="ok", present=True)
    assert "dummy" in SIGNALS
    fn, weight, profiles = SIGNALS["dummy"]
    assert weight == 10 and profiles == "all"
    res = fn(None, None)
    assert res.points == 10 and res.present is True
    # Clean up: remove the transient test signal so it doesn't pollute other tests
    del SIGNALS["dummy"]


def _mk_repo(tmp_path, commits):
    """commits: list of (iso_datetime, {filename: content})."""
    repo = tmp_path / "r"; repo.mkdir()
    env = {**os.environ, "GIT_AUTHOR_NAME": "stu", "GIT_AUTHOR_EMAIL": "s@e.x",
           "GIT_COMMITTER_NAME": "stu", "GIT_COMMITTER_EMAIL": "s@e.x"}
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    for dt, files in commits:
        for fn, content in files.items():
            (repo / fn).write_text(content)
        env2 = {**env, "GIT_AUTHOR_DATE": dt, "GIT_COMMITTER_DATE": dt,
                "GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "commit.gpgsign",
                "GIT_CONFIG_VALUE_0": "false"}
        subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-q", "-m", f"c {dt}"], cwd=repo, env=env2, check=True)
    return repo

def test_spread_days_fires_across_three_days(tmp_path):
    repo = _mk_repo(tmp_path, [
        ("2026-03-01T10:00:00", {"a.c": "1"}),
        ("2026-03-03T10:00:00", {"a.c": "12"}),
        ("2026-03-05T10:00:00", {"a.c": "123"}),
    ])
    facts = RepoFacts.from_repo(repo)
    res = spread_days_signal(facts, {"weights": {"spread_days": 20}, "thresholds": {"min_spread_days": 3}})
    assert res.present is True and res.points == 20

def test_deletions_signal_absent_when_no_deletions(tmp_path):
    repo = _mk_repo(tmp_path, [("2026-03-01T10:00:00", {"a.c": "line1\nline2\n"})])
    facts = RepoFacts.from_repo(repo)
    res = deletions_signal(facts, {"weights": {"deletions": 15}})
    assert res.present is False and res.points == 0


# ---------------------------------------------------------------------------
# Fix 2: score_repo defensive thresholds — no KeyError when thresholds absent
# ---------------------------------------------------------------------------

def test_score_repo_no_thresholds_key(tmp_path):
    """score_repo must not KeyError when cfg has no 'thresholds' key."""
    from lectern.triage_engine import score_repo

    repo = _mk_repo(tmp_path, [
        ("2026-03-01T10:00:00", {"a.c": "x=1\n"}),
        ("2026-03-03T10:00:00", {"a.c": "x=1\ny=2\n"}),
    ])
    cfg = {
        "assignment": {"assigned_date": "2026-03-01", "due_date": "2026-03-16",
                       "expected_commits": 2},
        "weights": {},
        # intentionally no "thresholds" key
    }
    score, reasoning, bucket = score_repo(repo, cfg, profile="short-project")
    assert bucket in {"PASS", "REVIEW", "FLAG"}, f"unexpected bucket: {bucket!r}"
    assert isinstance(score, int)


# ---------------------------------------------------------------------------
# Task 3: Scoring engine + parity guard
# ---------------------------------------------------------------------------

def test_engine_parity_with_upstream(tmp_path):
    repo = _mk_repo(tmp_path, [
        ("2026-03-01T10:00:00", {"a.c": "x=1\n"}),
        ("2026-03-02T14:00:00", {"a.c": "x=1\ny=2\n"}),
        ("2026-03-05T09:00:00", {"a.c": "x=1\n"}),  # deletion
        ("2026-03-09T20:00:00", {"b.c": "z\n", "a.c": "x=1\nq\n"}),
    ])
    cfg = {"assignment": {"assigned_date": "2026-03-01", "due_date": "2026-03-16",
                          "expected_commits": 4},
           "thresholds": {"pass": 60, "flag": 20}, "weights": {}}
    from lectern.triage_engine import score_repo
    score, reasoning, bucket = score_repo(repo, cfg, profile="short-project")
    assert isinstance(score, int) and bucket in {"PASS", "REVIEW", "FLAG"}
    assert "spread across" in reasoning


def test_engine_score_equals_grader_py(tmp_path):
    """Parity guard: lectern engine must produce the same numeric score as the
    upstream assignment-triage/grader.py on the same repo and weights.

    Both use default weights (weights={}) so every signal uses the same
    default_weight values that are hard-coded in grader.py and mirrored in
    triage_signals.py.

    The upstream grader.py has a window_cap_hours threshold (default 2 h) that
    caps score at 20 when all commits land within 2 hours. Our fixture spans
    8 days so the cap never fires. We disable it explicitly (window_cap_hours=0)
    to make the comparison unconditional.
    """
    import sys
    import os

    grader_dir = "/home/anthony/git/assignment-triage"
    if not os.path.isfile(os.path.join(grader_dir, "grader.py")):
        import pytest
        pytest.skip("upstream grader.py not found — skipping parity cross-check")

    # Import grader without polluting the module cache permanently
    if grader_dir not in sys.path:
        sys.path.insert(0, grader_dir)
    try:
        import grader as upstream_grader
    except Exception as exc:
        import pytest
        pytest.skip(f"could not import upstream grader: {exc}")

    commits = [
        ("2026-03-01T10:00:00", {"a.c": "x=1\n"}),
        ("2026-03-02T14:00:00", {"a.c": "x=1\ny=2\n"}),
        ("2026-03-05T09:00:00", {"a.c": "x=1\n"}),  # deletion
        ("2026-03-09T20:00:00", {"b.c": "z\n", "a.c": "x=1\nq\n"}),
    ]
    repo = _mk_repo(tmp_path, commits)

    # Upstream config: disable the window cap so it can't diverge from lectern
    upstream_cfg = {
        "assignment": {
            "assigned_date": "2026-03-01",
            "due_date": "2026-03-16",
            "expected_commits": 4,
        },
        "thresholds": {"pass": 60, "flag": 20, "min_spread_days": 3, "window_cap_hours": 0},
        "weights": {},
    }
    upstream_score, _, _ = upstream_grader.score_repo(repo, upstream_cfg)

    from lectern.triage_engine import score_repo as lectern_score_repo
    lectern_cfg = {
        "assignment": {
            "assigned_date": "2026-03-01",
            "due_date": "2026-03-16",
            "expected_commits": 4,
        },
        "thresholds": {"pass": 60, "flag": 20},
        "weights": {},
    }
    lectern_score, _, _ = lectern_score_repo(repo, lectern_cfg, profile="short-project")

    assert lectern_score == upstream_score, (
        f"lectern score {lectern_score} != upstream score {upstream_score}; "
        "triage_signals.py default weights may have drifted from grader.py"
    )


# ---------------------------------------------------------------------------
# Task 4: Profiles as YAML
# ---------------------------------------------------------------------------

def test_profile_weights_loaded_from_yaml():
    from lectern.triage_engine import load_profile
    p = load_profile("term-project")
    assert p["weights"]["spread_days"] == 30   # term projects emphasize spread
    assert p["weights"]["cleanup_commits"] == 15
