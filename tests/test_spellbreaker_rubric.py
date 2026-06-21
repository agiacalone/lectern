# tests/test_spellbreaker_rubric.py
from pathlib import Path
from lectern.digest_rubric import load_rubric


def test_spellbreaker_rubric_valid():
    r = load_rubric(Path("templates/spellbreaker.rubric.yaml"))
    assert r.total == 30 and r.cap == 30
    assert {s.key for s in r.sections} == {"ward1", "ward2", "ward3", "craft"}
    assert r.sections[0].requires_cleared == "ward1"
    assert [s.key for s in r.bonus] == ["omega"] and r.bonus[0].requires_cleared == "ward4"
