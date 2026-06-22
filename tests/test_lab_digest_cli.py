import csv, json
from pathlib import Path
from lectern.lab_digest import main
from tests.test_digest_rubric import GOOD, _write
from tests.test_digest_merge import _bundle2, _cohort

def test_cli_emit_then_merge(tmp_path):
    rub = _write(tmp_path, GOOD); b = _bundle2(tmp_path); _cohort(b)
    tasks = tmp_path / "tasks.jsonl"
    assert main(["emit","--bundle",str(b),"--rubric",str(rub),"--out",str(tasks)]) == 0
    assert tasks.exists() and (tasks.parent / "digest.schema.json").exists()
    res = b / "results.jsonl"
    res.write_text(json.dumps({"github_id":"harleyq","sections":{"ward1":5,"ward2":10,"ward3":9,"craft":6},
                  "bonus":{"omega":4},"total":34,"comment":"strong","student_comment":"Great clear.",
                  "confidence":"high","abstain":False}))
    assert main(["merge","--bundle",str(b),"--rubric",str(rub),"--results",str(res)]) == 0
    rows = {r["github_id"]: r for r in csv.DictReader((b / "cohort.csv").open())}
    assert rows["harleyq"]["writeup_score"] == "30"
