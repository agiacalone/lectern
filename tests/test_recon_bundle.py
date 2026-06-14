import csv, json
from pathlib import Path
from lectern.recon_bundle import write_bundle
from lectern.recon_record import RepoRecord
from lectern.recon_autograde import AutogradeResult, Challenge
from lectern.recon_git import GitRecon
from lectern.recon_docs import DocRecon

def _recs():
    return [
        RepoRecord("Alpha","A","r-Alpha","c1",
            AutogradeResult(True, 70, 100, {"ward1":Challenge("ward1",True,10,10)}, "c1"),
            GitRecon(commits=12, spread_days=5.0), {"grimoire":DocRecon("grimoire",True,sources=3,word_count=600)},
            links={"repo":"https://github.com/o/r-Alpha","feedback_pr":"https://github.com/o/r-Alpha/pull/1"}),
        RepoRecord("Beta","B","r-Beta","c2",
            AutogradeResult(False, 0, 100, {"ward1":Challenge("ward1",False,0,10)}, "c2"),
            GitRecon(commits=1, spread_days=0.0), {"grimoire":DocRecon("grimoire",False)},
            links={"repo":"https://github.com/o/r-Beta","feedback_pr":"https://github.com/o/r-Beta/pull/1"}),
    ]

def test_write_bundle_emits_all_artifacts(tmp_path):
    out = tmp_path / "bundle"
    write_bundle(_recs(), out, lab_name="Lab 1", total_points=100)
    assert (out / "repos" / "Alpha.json").exists()
    assert json.loads((out/"repos"/"Beta.json").read_text())["autograde"]["all_failed"] is True
    rows = list(csv.DictReader((out / "cohort.csv").open()))
    assert {r["github_id"] for r in rows} == {"Alpha","Beta"}
    assert any(r["points"] == "70" for r in rows)
    assert any(r["feedback_pr"].endswith("/pull/1") for r in rows)
    facts = (out / "FACTS.md").read_text()
    assert "Lab 1" in facts and "Alpha" in facts and "Beta" in facts
    assert "Feedback" in facts
    assert (out / "bundle.json").exists()
