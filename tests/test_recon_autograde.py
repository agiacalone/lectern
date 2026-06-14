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


def test_scrape_autograde_maps_step_conclusions():
    """Legacy fallback: latest run's job-step conclusions → challenge points."""
    import json
    from lectern.recon_autograde import scrape_autograde
    steps = [
        {"name": "Ward I",   "key": "ward1", "points": 10},
        {"name": "Ward II",  "key": "ward2", "points": 35},
        {"name": "Ward III", "key": "ward3", "points": 15},
        {"name": "OMEGA",    "key": "ward4", "points": 10, "optional": True},
    ]
    def fake_gh(args):
        a = " ".join(args)
        if "/runs?branch=" in a or "/workflows/" in a:
            return json.dumps({"workflow_runs": [{"id": 999, "head_sha": "deadbeef"}]})
        if "/runs/999/jobs" in a:
            return json.dumps({"jobs": [{"steps": [
                {"name": "Ward I",   "conclusion": "success"},
                {"name": "Ward II",  "conclusion": "failure"},
                {"name": "Ward III", "conclusion": "success"},
                {"name": "OMEGA",    "conclusion": "failure"},
            ]}]})
        raise RuntimeError("unexpected gh call: " + a)
    r = scrape_autograde("O", "r", "autograde.yml", steps, gh=fake_gh)
    assert r.commit == "deadbeef"
    assert r.challenges["ward1"].points == 10
    assert r.challenges["ward2"].points == 0
    assert r.points == 25          # 10 + 15
    assert r.max == 70
    assert r.honor_ok is True      # at least one ward passed → flag was present

def test_scrape_autograde_no_runs_returns_none():
    import json
    from lectern.recon_autograde import scrape_autograde
    def fake_gh(args):
        return json.dumps({"workflow_runs": []})
    assert scrape_autograde("O", "r", "autograde.yml", [{"name":"Ward I","key":"w1","points":10}], gh=fake_gh) is None
