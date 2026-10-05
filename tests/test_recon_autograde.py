from pathlib import Path
from lectern.recon_autograde import parse_result_json, AutogradeResult

FIX = Path(__file__).parent / "fixtures" / "recon" / "result.json"

def test_parse_result_json():
    r = parse_result_json(FIX.read_text())
    assert isinstance(r, AutogradeResult)
    assert r.honor_ok is True
    assert r.points == 25
    assert r.challenges["ward2"].passed is False
    assert r.challenges["ward3"].points == 15
    assert r.all_failed is False

def test_all_failed_true_when_zero():
    r = parse_result_json('{"schema":1,"honor_ok":false,"challenges":'
        '{"w1":{"pass":false,"points":0,"max":10}},"points":0,"max":10}')
    assert r.all_failed is True
    assert r.honor_ok is False

def test_malformed_returns_none_result():
    r = parse_result_json("not json")
    assert r is None

def test_fetch_result_uses_injected_runner():
    from lectern.recon_autograde import fetch_autograde
    calls = []
    def fake_gh(args):
        calls.append(args)
        return __import__("base64").b64encode(FIX.read_bytes()).decode()
    r = fetch_autograde("Giacalone-CECS", "repo-x", "grading/result.json",
                        branch="main", gh=fake_gh)
    assert r.points == 25
    assert any("repo-x" in " ".join(a) for a in calls)

def test_fetch_result_missing_returns_none():
    from lectern.recon_autograde import fetch_autograde
    def fake_gh(args):
        raise RuntimeError("gh: Not Found (HTTP 404)")
    assert fetch_autograde("O", "r", "grading/result.json", gh=fake_gh) is None


def test_scrape_autograde_parses_log_pass_fail():
    """Legacy fallback parses the run LOG (PASS/FAIL <key>), NOT jobs-API conclusions,
    because continue-on-error masks every step conclusion as success."""
    import json
    from lectern.recon_autograde import scrape_autograde
    steps = [
        {"name": "Ward I",   "key": "ward1", "points": 10},
        {"name": "Ward II",  "key": "ward2", "points": 35},
        {"name": "Ward III", "key": "ward3", "points": 15},
        {"name": "OMEGA",    "key": "ward4", "points": 10, "optional": True},
    ]
    fake_log = (
        "grade\tUNKNOWN STEP\t2026-06-11T06:21:47Z FAIL ward1: oracle rejected the submitted proof\n"
        "grade\tUNKNOWN STEP\t2026-06-11T06:28:30Z PASS ward2\n"
        "grade\tUNKNOWN STEP\t2026-06-11T06:28:31Z FAIL ward3: oracle rejected the submitted proof\n"
        "grade\tUNKNOWN STEP\t2026-06-11T06:28:32Z FAIL ward4: exploit produced no output\n"
    )
    def fake_gh(args):
        a = " ".join(args)
        if args[:1] == ["api"]:
            return json.dumps({"workflow_runs": [{"id": 999, "head_sha": "deadbeef"}]})
        if args[:2] == ["run", "view"]:
            return fake_log
        raise RuntimeError("unexpected gh call: " + a)
    r = scrape_autograde("O", "r", "autograde.yml", steps, gh=fake_gh)
    assert r.commit == "deadbeef"
    assert r.challenges["ward2"].points == 35
    assert r.challenges["ward1"].points == 0
    assert r.points == 35          # only ward2 passed
    assert r.max == 70
    assert r.honor_ok is True      # no "honor flag missing" in log

def test_scrape_autograde_honor_gate_fail():
    """All wards FAIL with honor-flag-missing → honor_ok False, 0 points."""
    import json
    from lectern.recon_autograde import scrape_autograde
    steps = [{"name": "Ward I", "key": "ward1", "points": 10},
             {"name": "Ward II", "key": "ward2", "points": 35}]
    fake_log = ("grade\tx\tFAIL ward1: honor flag missing or incorrect in student/WRITEUP.md\n"
                "grade\tx\tFAIL ward2: honor flag missing or incorrect in student/WRITEUP.md\n")
    def fake_gh(args):
        if args[:1] == ["api"]:
            return json.dumps({"workflow_runs": [{"id": 1, "head_sha": "abc"}]})
        return fake_log
    r = scrape_autograde("O", "r", "autograde.yml", steps, gh=fake_gh)
    assert r.points == 0
    assert r.honor_ok is False

def test_scrape_autograde_no_runs_returns_none():
    import json
    from lectern.recon_autograde import scrape_autograde
    def fake_gh(args):
        return json.dumps({"workflow_runs": []})
    assert scrape_autograde("O", "r", "autograde.yml", [{"name":"Ward I","key":"w1","points":10}], gh=fake_gh) is None


def test_fetch_autograde_artifact_reads_result_json():
    import json
    from lectern.recon_autograde import fetch_autograde_artifact
    result = json.dumps({"schema":1,"honor_ok":True,
        "challenges":{"ward1":{"pass":True,"points":10,"max":10}},"points":10,"max":100})
    def fake_gh(args):
        return json.dumps({"workflow_runs":[{"id":555,"head_sha":"cafef00d"}]})
    seen = {}
    def fake_dl(org, repo, run_id, artifact, member):
        seen.update(run_id=run_id, artifact=artifact)
        return result
    r = fetch_autograde_artifact("O","r", gh=fake_gh, download=fake_dl)
    assert r.points == 10
    assert r.commit == "cafef00d"      # falls back to run head_sha
    assert seen["run_id"] == 555 and seen["artifact"] == "grading-result"

def test_fetch_autograde_artifact_missing_returns_none():
    import json
    from lectern.recon_autograde import fetch_autograde_artifact
    def fake_gh(args): return json.dumps({"workflow_runs":[{"id":1,"head_sha":"x"}]})
    def fake_dl(*a): return None       # artifact absent
    assert fetch_autograde_artifact("O","r", gh=fake_gh, download=fake_dl) is None


# ── gradebox source + cancelled-run filter (2026-10-05) ──────────────────────
import json as _json
from lectern.recon_autograde import fetch_gradebox, _graded_runs


def _gb(tmp_path, gid, **d):
    p = tmp_path / gid
    p.mkdir()
    (p / "result.json").write_text(_json.dumps(d))
    return tmp_path


def test_gradebox_result_maps_scored_tests_to_challenges(tmp_path):
    out = _gb(tmp_path, "alice", score=65, max=360, build_passed=True, build_points=20,
              tests=[{"name": "runs", "points": 40, "passed": True, "stdout": ""},
                     {"name": "treasure", "points": 100, "passed": False, "stdout": ""},
                     {"name": "evidence", "points": 0, "passed": True, "stdout": ""}])
    r = fetch_gradebox(out, "alice")
    assert r.points == 65 and r.max == 360
    assert set(r.challenges) == {"build", "runs", "treasure"}      # 0-point evidence dropped
    assert r.challenges["build"].points == 20 and r.challenges["treasure"].points == 0


def test_gradebox_exact_score_overrides_the_bands(tmp_path):
    out = _gb(tmp_path, "bob", score=60, max=360, build_passed=True, build_points=20,
              tests=[{"name": "evidence", "points": 0, "passed": True,
                      "stdout": "Score before semaphores: 140/140\nTotal score: 305/360"}])
    r = fetch_gradebox(out, "bob", exact_score=[r"Total score: (\d+)/", r"before semaphores: (\d+)/"])
    assert r.points == 305


def test_gradebox_exact_score_is_capped_at_max(tmp_path):
    out = _gb(tmp_path, "eve", score=0, max=60, build_passed=True, build_points=0,
              tests=[{"name": "e", "points": 0, "passed": True, "stdout": "Total score: 999/60"}])
    assert fetch_gradebox(out, "eve", exact_score=[r"Total score: (\d+)/"]).points == 60


def test_gradebox_infers_build_points_from_older_results(tmp_path):
    out = _gb(tmp_path, "old", score=60, max=360, build_passed=True,
              tests=[{"name": "runs", "points": 40, "passed": True, "stdout": ""}])
    assert fetch_gradebox(out, "old").challenges["build"].points == 20


def test_gradebox_missing_student_is_none(tmp_path):
    assert fetch_gradebox(tmp_path, "nobody") is None


def test_cancelled_runs_are_never_the_latest_graded_run():
    runs = [{"id": 3, "conclusion": "cancelled"}, {"id": 2, "conclusion": "skipped"},
            {"id": 1, "conclusion": "success"}]
    assert [r["id"] for r in _graded_runs(runs)] == [1]
