from lectern.report_recommend import recommend
from lectern.report_manifest import ReportManifest

M = ReportManifest("CECS 378", "01", "su26", "L", "O", "p", 70, 30, [],
                   {"A": 90, "B": 80, "C": 70, "D": 60, "F": 0}, 1.0, "feedback", 1)


def row(**k):
    base = dict(github_id="x", student="X", points=70, honor_ok=True,
                triage_bucket="PASS", writeup_flags=[], proposed=100)
    base.update(k)
    return base


def test_routine_goes_to_confirm():
    rec = recommend([row()], {"x": 96.0}, M)
    assert rec.confirm and not rec.edge_cases


def test_honor_fail_is_edge_case():
    rec = recommend([row(github_id="j", honor_ok=False, points=0, proposed=0)], {"j": 0}, M)
    assert any(e["github_id"] == "j" for e in rec.edge_cases)


def test_flag_triage_is_edge_case():
    rec = recommend([row(github_id="f", triage_bucket="FLAG")], {"f": 80}, M)
    assert any(e["github_id"] == "f" for e in rec.edge_cases)


def test_needs_review_is_low_confidence():
    rec = recommend([row(github_id="r", writeup_flags=["student-comment:needs-review"])],
                    {"r": 85}, M)
    assert any(e["github_id"] == "r" for e in rec.low_confidence)


def test_near_letter_cut_is_upward():
    rec = recommend([row(github_id="u")], {"u": 89.4}, M)
    assert any(e["github_id"] == "u" for e in rec.upward)
