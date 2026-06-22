import os
from lectern.report_render import render_report
from lectern.report_manifest import load_report_manifest

FX = os.path.join(os.path.dirname(__file__), "fixtures", "spellbreaker_su26")


def test_golden_render_matches():
    m = load_report_manifest(os.path.join(FX, "spellbreaker.report.yaml"))
    out = render_report(FX, os.path.join(FX, "cohort.csv"), m)
    expected = open(os.path.join(FX, "expected_report.md")).read()
    assert out.strip() == expected.strip()


def test_golden_stats_match_known_cohort():
    m = load_report_manifest(os.path.join(FX, "spellbreaker.report.yaml"))
    out = render_report(FX, os.path.join(FX, "cohort.csv"), m)
    # values verified against classes/378-478/archives/su26-01/recon-lab1/REPORT.md
    assert "n=25" in out and "mean 82.6" in out and "median 90" in out
    # distribution A:13 B:6 C:3 D:0 F:3
    assert "A ▏████████████████████████ 13" in out
    assert "F ▏██████ 3" in out
