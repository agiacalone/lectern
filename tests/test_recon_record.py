from lectern.recon_record import RepoRecord, record_to_dict, record_from_dict
from lectern.recon_autograde import AutogradeResult, Challenge
from lectern.recon_git import GitRecon
from lectern.recon_docs import DocRecon

def _rec():
    return RepoRecord(
        github_id="ChaoticNerd", student="C. Nerd",
        repo="cecs-378-...-ChaoticNerd", grading_commit="abc123",
        autograde=AutogradeResult(honor_ok=True, points=25, max=100,
            challenges={"ward1": Challenge("ward1", True, 10, 10)}, commit="abc123"),
        git=GitRecon(commits=14, spread_days=6.0),
        docs={"grimoire": DocRecon(label="grimoire", present=True, sources=3, word_count=400)},
        links={"repo": "https://github.com/o/r", "feedback_pr": "https://github.com/o/r/pull/1"})

def test_record_round_trips():
    r = _rec()
    d = record_to_dict(r)
    assert d["autograde"]["points"] == 25
    assert d["git"]["commits"] == 14
    assert d["links"]["feedback_pr"].endswith("/pull/1")
    back = record_from_dict(d)
    assert back.github_id == "ChaoticNerd"
    assert back.autograde.points == 25
    assert back.docs["grimoire"].sources == 3
    assert back.links["repo"] == "https://github.com/o/r"

def test_record_handles_no_autograde():
    r = _rec(); r.autograde = None
    d = record_to_dict(r)
    assert d["autograde"] is None
    assert record_from_dict(d).autograde is None
