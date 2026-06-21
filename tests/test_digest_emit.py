import json
from pathlib import Path
from lectern.digest_rubric import load_rubric
from lectern.digest_emit import emit
from tests.test_digest_rubric import GOOD, _write

def _bundle(tmp_path):
    b = tmp_path / "bundle"; (b / "repos").mkdir(parents=True); (b / "writeups").mkdir()
    # Harley: full clear, honor ok, has writeup
    (b / "repos" / "harleyq.json").write_text(json.dumps({
        "github_id":"harleyq","student":"Harley Quinn","repo":"r",
        "autograde":{"honor_ok":True,"points":70,"max":70,"all_failed":False,"challenges":{
            "ward1":{"key":"ward1","passed":True,"points":10,"max":10},
            "ward2":{"key":"ward2","passed":True,"points":35,"max":35},
            "ward3":{"key":"ward3","passed":True,"points":15,"max":15},
            "ward4":{"key":"ward4","passed":True,"points":10,"max":10}}},
        "docs":{},"git":None,"links":{}}))
    (b / "writeups" / "harleyq.md").write_text("# Grimoire\nWard I broke via ECB determinism.")
    # Joker: honor fail, no writeup -> skip
    (b / "repos" / "joker.json").write_text(json.dumps({
        "github_id":"joker","student":"The Joker","repo":"r",
        "autograde":{"honor_ok":False,"points":0,"max":70,"all_failed":True,"challenges":{}},
        "docs":{},"git":None,"links":{}}))
    return b

def test_emit_writes_tasks_and_schema(tmp_path):
    r = load_rubric(_write(tmp_path, GOOD))
    out = tmp_path / "tasks.jsonl"
    n = emit(_bundle(tmp_path), r, out)
    assert n == 1  # only Harley is gradeable
    assert (out.parent / "digest.schema.json").exists()
    tasks = {json.loads(l)["github_id"]: json.loads(l) for l in out.read_text().splitlines()}
    assert tasks["harleyq"]["skip"] is False
    assert tasks["harleyq"]["autograde"]["cleared"] == ["ward1","ward2","ward3","ward4"]
    assert "ECB determinism" in tasks["harleyq"]["writeup_text"]
    assert tasks["joker"]["skip"] is True
