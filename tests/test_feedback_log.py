from lectern.feedback_log import render_feedback_log
from lectern.report_manifest import ReportManifest

M = ReportManifest("CECS 378", "01", "su26", "Lab 1", "Giacalone-CECS",
                   "cecs-378-su26-01-lab-01-symmetric-crypto", 70, 30, [], {}, 1.0, "feedback", 1)


def test_log_has_frontmatter_and_entries():
    out = render_feedback_log([
        {"github_id": "gh-user-06", "student": "Selina Kyle", "auto": 70, "writeup": 30,
         "total": 100, "student_comment": "Full clear.", "posted": True, "signed": True,
         "pr_state": "CLOSED"}], M)
    assert out.startswith("---") and "type: feedback-log" in out
    assert "visibility: private" in out
    assert "Selina Kyle" in out and "100" in out and "Full clear." in out


def test_log_sorted_by_total_desc():
    out = render_feedback_log([
        {"github_id": "a", "student": "Low Student", "auto": 0, "writeup": 0, "total": 14,
         "student_comment": "x", "posted": True, "signed": True, "pr_state": "CLOSED"},
        {"github_id": "b", "student": "High Student", "auto": 70, "writeup": 30, "total": 100,
         "student_comment": "y", "posted": True, "signed": True, "pr_state": "CLOSED"},
    ], M)
    assert out.index("High Student") < out.index("Low Student")
