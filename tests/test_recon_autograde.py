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
