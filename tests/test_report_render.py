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
                    "writeup_score", "writeup_comment", "student_comment", "writeup_flags"])
        w.writerow(["bwayne", "Selina Kyle", "70", "True", "PASS", "30", "precise", "Full clear.", ""])
        w.writerow(["flawton", "James Gordon", "0", "False", "REVIEW", "0", "", "", ""])
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
