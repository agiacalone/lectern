from lectern.digest_schema import validate_result
from lectern.digest_rubric import load_rubric


def _rubric(tmp_path):
    p = tmp_path / "r.yaml"
    p.write_text("lab: L\ntotal: 30\ncomment_max_chars: 140\nstudent_comment_max_chars: 600\ncap: 30\n"
                 "sections:\n  - {key: ward1, label: W1, max: 30, requires_cleared: ward1, "
                 "anchors: {strong: s, adequate: a, weak: w, missing: m}}\n")
    return load_rubric(str(p))


def test_student_comment_required(tmp_path):
    r = _rubric(tmp_path)
    obj = {"github_id": "x", "sections": {"ward1": 30}, "total": 30,
           "comment": "ok", "confidence": "high", "abstain": False}
    errs = validate_result(obj, r)
    assert any("student_comment" in e for e in errs)


def test_student_comment_present_validates(tmp_path):
    r = _rubric(tmp_path)
    obj = {"github_id": "x", "sections": {"ward1": 30}, "total": 30,
           "comment": "ok", "student_comment": "Nice full clear.",
           "confidence": "high", "abstain": False}
    assert validate_result(obj, r) == []


def test_student_comment_length_capped(tmp_path):
    r = _rubric(tmp_path)
    obj = {"github_id": "x", "sections": {"ward1": 30}, "total": 30,
           "comment": "ok", "student_comment": "z" * 601,
           "confidence": "high", "abstain": False}
    assert validate_result(obj, r)  # exceeds maxLength → error
