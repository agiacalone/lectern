import csv
from lectern.report_render import render_report
from lectern.report_manifest import ReportManifest

W = lambda k, l: type("W", (), {"key": k, "label": l})()
M = ReportManifest("CECS 378", "01", "su26", "Lab 1 — Symmetric Cryptography",
                   "Giacalone-CECS", "cecs-378-su26-01-lab-01-symmetric-crypto",
                   70, 30, [W("ward1", "Ward I"), W("ward2", "Ward II")],
                   {"A": 90, "B": 80, "C": 70, "D": 60, "F": 0}, 1.0, "feedback", 1)


def _cohort(tmp_path):
    p = tmp_path / "cohort.csv"
    with open(p, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["github_id", "student", "points", "honor_ok", "triage_bucket",
                    "cleared", "writeup_score", "writeup_comment", "student_comment", "writeup_flags"])
        w.writerow(["bwayne", "Selina Kyle", "70", "True", "PASS", "ward1 ward2", "30", "precise", "Full clear.", ""])
        w.writerow(["flawton", "James Gordon", "0", "False", "REVIEW", "", "0", "", "", ""])
    return str(p)


def test_render_has_sections(tmp_path):
    out = render_report(str(tmp_path), _cohort(tmp_path), M)
    for h in ["# ", "GRADE DISTRIBUTION", "Grade table", "recommendations",
              "Canvas entry sheet", "Provenance"]:
        assert h in out


def test_proposed_is_auto_plus_writeup(tmp_path):
    out = render_report(str(tmp_path), _cohort(tmp_path), M)
    assert "100" in out          # Arya 70+30
    assert "James Gordon" in out    # non-submission still listed


def test_feedback_section_scaffolds_placeholders(tmp_path):
    # graded → verbatim comment; ungraded submission → `_Comments:_` placeholder +
    # `__` grade; non-submission → `_no submission_`, nothing to grade.
    p = tmp_path / "cohort.csv"
    with open(p, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["github_id", "student", "points", "honor_ok", "triage_bucket",
                    "cleared", "doc_present", "writeup_score", "writeup_comment",
                    "student_comment", "writeup_flags"])
        # graded
        w.writerow(["bwayne", "Selina Kyle", "70", "True", "PASS", "ward1 ward2",
                    "True", "30", "internal", "Full clear, mechanism throughout.", ""])
        # submitted but not yet graded (doc present, no student_comment)
        w.writerow(["rsloan", "Renee Montoya", "60", "True", "PASS", "ward1",
                    "True", "0", "", "", ""])
        # non-submission
        w.writerow(["flawton", "James Gordon", "0", "False", "REVIEW", "",
                    "False", "0", "", "", ""])
    out = render_report(str(tmp_path), str(p), M)
    fb = out.split("## Per-student feedback & grades")[1].split("## Canvas")[0]
    assert "Selina Kyle — **100 / 100**" in fb
    assert "Full clear, mechanism throughout." in fb
    assert "Renee Montoya — **__ / 100**" in fb     # ungraded placeholder grade
    assert "> _Comments:_" in fb                      # placeholder to fill via LLM
    assert "Writeup __/30" in fb                      # ungraded writeup cell
    assert "James Gordon — **0 / 100**" in fb
    assert "> _no submission_" in fb


def test_ward_clear_funnel_counts_from_cleared_column(tmp_path):
    # Regression: the funnel used to read a non-existent `cleared` key and always
    # rendered 0. Only bwayne cleared ward1;ward2 → each ward counts 1, not 0.
    out = render_report(str(tmp_path), _cohort(tmp_path), M)
    funnel = out.split("WARD-CLEAR FUNNEL")[1].split("```")[0]
    assert "Ward I" in funnel and "Ward II" in funnel
    for line in funnel.splitlines():
        if line.strip().startswith(("Ward I", "Ward II")):
            assert line.rstrip().endswith(" 1"), f"funnel miscounted: {line!r}"
