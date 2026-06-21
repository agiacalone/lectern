from lectern.digest_rubric import load_rubric
from lectern.digest_schema import result_schema, validate_result
from tests.test_digest_rubric import GOOD, _write

def _rubric(tmp_path): return load_rubric(_write(tmp_path, GOOD))

def test_valid_result_passes(tmp_path):
    r = _rubric(tmp_path)
    obj = {"github_id":"harleyq","sections":{"ward1":5,"ward2":10,"ward3":9,"craft":6},
           "bonus":{"omega":4},"total":30,"comment":"strong","confidence":"high","abstain":False}
    assert validate_result(obj, r) == []

def test_missing_field_flagged(tmp_path):
    r = _rubric(tmp_path)
    obj = {"github_id":"x","sections":{"ward1":5,"ward2":10,"ward3":9,"craft":6}}  # no comment/confidence
    assert validate_result(obj, r)  # non-empty error list

def test_bad_confidence_enum_flagged(tmp_path):
    r = _rubric(tmp_path)
    obj = {"github_id":"x","sections":{"ward1":5,"ward2":10,"ward3":9,"craft":6},
           "bonus":{"omega":0},"total":24,"comment":"ok","confidence":"medium-ish","abstain":False}
    assert validate_result(obj, r)
