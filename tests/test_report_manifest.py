from lectern.report_manifest import load_report_manifest
import pytest


def test_loads_spellbreaker(tmp_path):
    p = tmp_path / "m.yaml"
    p.write_text(
        "course: CECS 378\nsection: '01'\nterm: su26\n"
        "lab: 'Lab 1 — Symmetric Cryptography'\n"
        "org: Giacalone-CECS\nrepo_prefix: cecs-378-su26-01-lab-01-symmetric-crypto\n"
        "auto_max: 70\nwriteup_max: 30\nbump_band: 1.0\n"
        "feedback_branch: feedback\nfeedback_pr: 1\n"
        "wards:\n  - {key: ward1, label: 'Ward I'}\n  - {key: ward2, label: 'Ward II'}\n"
        "letter_cuts: {A: 90, B: 80, C: 70, D: 60, F: 0}\n"
    )
    m = load_report_manifest(str(p))
    assert m.auto_max == 70 and m.writeup_max == 30
    assert [w.key for w in m.wards] == ["ward1", "ward2"]
    assert m.letter_cuts["A"] == 90 and m.feedback_pr == 1


def test_rejects_bad_point_split(tmp_path):
    p = tmp_path / "m.yaml"
    p.write_text("course: X\nsection: '01'\nterm: su26\nlab: L\norg: O\n"
                 "repo_prefix: p\nauto_max: -1\nwriteup_max: 30\n"
                 "feedback_branch: feedback\nfeedback_pr: 1\nwards: []\n"
                 "letter_cuts: {A: 90}\n")
    with pytest.raises(ValueError):
        load_report_manifest(str(p))
