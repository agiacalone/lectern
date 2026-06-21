import pytest
from pathlib import Path
from lectern.digest_rubric import load_rubric

GOOD = """
lab: "Spellbreaker"
total: 30
comment_max_chars: 140
sections:
  - {key: ward1, label: "Ward I", max: 5,  requires_cleared: ward1, anchors: {strong: a, adequate: b, weak: c, missing: d}}
  - {key: ward2, label: "Ward II", max: 10, requires_cleared: ward2, anchors: {strong: a, adequate: b, weak: c, missing: d}}
  - {key: ward3, label: "Ward III", max: 9, requires_cleared: ward3, anchors: {strong: a, adequate: b, weak: c, missing: d}}
  - {key: craft, label: "Craft", max: 6, anchors: {strong: a, adequate: b, weak: c, missing: d}}
bonus:
  - {key: omega, label: "OMEGA", max: 4, requires_cleared: ward4, anchors: {strong: a, adequate: b, weak: c, missing: d}}
cap: 30
"""

def _write(tmp_path, text):
    p = tmp_path / "r.yaml"; p.write_text(text); return p

def test_loads_valid_rubric(tmp_path):
    r = load_rubric(_write(tmp_path, GOOD))
    assert r.total == 30 and r.cap == 30 and r.comment_max_chars == 140
    assert [s.key for s in r.sections] == ["ward1","ward2","ward3","craft"]
    assert r.sections[0].requires_cleared == "ward1" and r.sections[3].requires_cleared is None
    assert [s.key for s in r.bonus] == ["omega"]

def test_rejects_core_sum_ne_total(tmp_path):
    bad = GOOD.replace("total: 30", "total: 29")
    with pytest.raises(SystemExit):
        load_rubric(_write(tmp_path, bad))

def test_rejects_duplicate_keys(tmp_path):
    bad = GOOD.replace("key: craft", "key: ward1")
    with pytest.raises(SystemExit):
        load_rubric(_write(tmp_path, bad))

def test_rejects_negative_max(tmp_path):
    bad = GOOD.replace("max: 6", "max: -1")
    with pytest.raises(SystemExit):
        load_rubric(_write(tmp_path, bad))
