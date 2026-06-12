import pytest
from lectern.triage_manifest import load_manifest, TriageManifestError


def test_load_valid_manifest(tmp_path):
    m = tmp_path / "a.triage.yaml"
    m.write_text("""
assignment:
  course: "CECS 326"
  section: "01"
  term: sp26
  name: "Lab 02"
  classroom_assignment_id: 123
  org: Giacalone-CECS
  repo_prefix: "cecs-326-sp26-01-lab-02-semaphores-"
  assigned_date: 2026-03-12
  due_date: 2026-05-16
  total_points: 100
profile: short-project
""")
    cfg = load_manifest(m)
    assert cfg["assignment"]["org"] == "Giacalone-CECS"
    assert cfg["profile"] == "short-project"


def test_missing_required_field_raises(tmp_path):
    m = tmp_path / "bad.triage.yaml"
    m.write_text("assignment:\n  name: x\nprofile: short-project\n")
    with pytest.raises(TriageManifestError):
        load_manifest(m)


def test_load_manifest_coerces_yaml_dates_to_iso_strings(tmp_path):
    from lectern.triage_manifest import load_manifest
    m = tmp_path / "d.triage.yaml"
    m.write_text(
        'assignment:\n'
        '  course: "CECS 326"\n  section: "01"\n  term: sp26\n  name: "Lab 02"\n'
        '  org: Giacalone-CECS\n  repo_prefix: "p-"\n'
        '  assigned_date: 2026-03-12\n  due_date: 2026-05-16\n  total_points: 100\n'
        'profile: short-project\n'
    )
    cfg = load_manifest(m)
    assert cfg["assignment"]["assigned_date"] == "2026-03-12"
    assert cfg["assignment"]["due_date"] == "2026-05-16"
    assert isinstance(cfg["assignment"]["due_date"], str)
