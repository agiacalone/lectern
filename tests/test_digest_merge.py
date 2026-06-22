import csv, json
from pathlib import Path
from lectern.digest_rubric import load_rubric
from lectern.digest_merge import merge_results, apply_to_cohort
from tests.test_digest_rubric import GOOD, _write
from tests.test_digest_emit import _bundle

def _cohort(b):
    p = b / "cohort.csv"
    with p.open("w", newline="") as f:
        w = csv.writer(f); w.writerow(["github_id","student","points"])
        w.writerow(["harleyq","Harley Quinn","70"]); w.writerow(["riddler","The Riddler","55"])
    return p

def _bundle2(tmp_path):
    b = _bundle(tmp_path)
    # Riddler: cleared I+II+OMEGA, NOT ward3 -> ward3 must be forced to 0 on merge
    (b / "repos" / "riddler.json").write_text(json.dumps({
        "github_id":"riddler","student":"The Riddler","repo":"r",
        "autograde":{"honor_ok":True,"points":55,"max":70,"all_failed":False,"challenges":{
            "ward1":{"key":"ward1","passed":True,"points":10,"max":10},
            "ward2":{"key":"ward2","passed":True,"points":35,"max":35},
            "ward3":{"key":"ward3","passed":False,"points":0,"max":15},
            "ward4":{"key":"ward4","passed":True,"points":10,"max":10}}},
        "docs":{},"git":None,"links":{}}))
    (b / "writeups" / "riddler.md").write_text("# Grimoire\nplausible but ward3 not done")
    return b

def test_partial_ward_zeroing_and_total_recompute(tmp_path):
    r = load_rubric(_write(tmp_path, GOOD))
    b = _bundle2(tmp_path)
    res = b / "results.jsonl"
    res.write_text("\n".join([
      # Riddler: model WRONGLY credits ward3=9; merge must zero it (ward3 not cleared)
      json.dumps({"github_id":"riddler","sections":{"ward1":4,"ward2":8,"ward3":9,"craft":3},
                  "bonus":{"omega":4},"total":28,"comment":"ok","student_comment":"Solid start.",
                  "confidence":"high","abstain":False}),
      # Harley: clean full
      json.dumps({"github_id":"harleyq","sections":{"ward1":5,"ward2":10,"ward3":9,"craft":6},
                  "bonus":{"omega":4},"total":34,"comment":"strong","student_comment":"Excellent work.",
                  "confidence":"high","abstain":False}),
    ]))
    merged = {m.github_id: m for m in merge_results(b, r, res)}
    # Riddler: ward3 forced 0 -> 4+8+0+3 + omega 4 = 19 (capped at 30)
    assert merged["riddler"].score == 19
    assert "partial-ward-zeroed:ward3" in merged["riddler"].flags
    # Harley: 5+10+9+6 + 4 = 34 -> capped to 30
    assert merged["harleyq"].score == 30

def test_low_confidence_withholds_score(tmp_path):
    r = load_rubric(_write(tmp_path, GOOD)); b = _bundle2(tmp_path)
    res = b / "results.jsonl"
    res.write_text(json.dumps({"github_id":"harleyq","sections":{"ward1":5,"ward2":10,"ward3":9,"craft":6},
                  "bonus":{"omega":0},"total":30,"comment":"unsure","student_comment":"Maybe.",
                  "confidence":"low","abstain":False}))
    merged = {m.github_id: m for m in merge_results(b, r, res)}
    assert merged["harleyq"].score is None and "needs-human-read" in merged["harleyq"].flags
    assert merged["harleyq"].student_comment == ""  # withheld on low confidence

def test_apply_to_cohort_adds_columns(tmp_path):
    r = load_rubric(_write(tmp_path, GOOD)); b = _bundle2(tmp_path); _cohort(b)
    res = b / "results.jsonl"
    res.write_text(json.dumps({"github_id":"harleyq","sections":{"ward1":5,"ward2":10,"ward3":9,"craft":6},
                  "bonus":{"omega":4},"total":34,"comment":"strong","student_comment":"Great clear.",
                  "confidence":"high","abstain":False}))
    apply_to_cohort(b, merge_results(b, r, res))
    rows = {row["github_id"]: row for row in csv.DictReader((b / "cohort.csv").open())}
    assert rows["harleyq"]["writeup_score"] == "30"
    assert rows["harleyq"]["writeup_comment"] == "strong"
    assert rows["harleyq"]["student_comment"] == "Great clear."
    assert rows["riddler"]["writeup_score"] == ""  # no result -> blank, untouched
