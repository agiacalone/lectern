import pytest
from pathlib import Path
from lectern.classroom_seed import build_payload, ClassroomSeedConfig


def _write_roster(path: Path):
    path.write_text(
        "student_id,lms_name,display_name,canonical_name,section,enrollment_status,"
        "add_dt,grade_dt,program,academic_level\n"
        '111111111,"Smith,Jane",Jane Smith,jane smith,01,enrolled,2026-01-21,,,Senior\n'
        '222222222,"Doe,John",John Doe,john doe,01,enrolled,2026-01-21,,,Senior\n'
        '333333333,"López,María José",María José López,maria jose lopez,01,withdrawn,2026-01-20,2026-04-16,,Senior\n'
    )


def test_build_payload_drops_withdrawn(tmp_path):
    roster = tmp_path / "roster.csv"
    _write_roster(roster)
    cfg = ClassroomSeedConfig(roster=roster, classroom_id="12345", dry_run=True)
    payload = build_payload(cfg)
    assert payload["classroom_id"] == "12345"
    # 2 enrolled, 1 withdrawn → 2 identifiers
    assert len(payload["identifiers"]) == 2
    # Withdrawn name not present
    assert not any("López" in i for i in payload["identifiers"])


def test_build_payload_default_label_format(tmp_path):
    roster = tmp_path / "roster.csv"
    _write_roster(roster)
    cfg = ClassroomSeedConfig(roster=roster, classroom_id="12345", dry_run=True)
    payload = build_payload(cfg)
    assert payload["identifiers"][0] == "111111111 — Jane Smith"
    assert payload["identifiers"][1] == "222222222 — John Doe"


def test_build_payload_custom_label_format(tmp_path):
    roster = tmp_path / "roster.csv"
    _write_roster(roster)
    cfg = ClassroomSeedConfig(roster=roster, classroom_id="12345", dry_run=True,
                              label_format="{student_id}")
    payload = build_payload(cfg)
    assert payload["identifiers"][0] == "111111111"


def test_build_payload_preserves_unicode_in_display_name(tmp_path):
    """Withdrawn students excluded, but if María José were enrolled, her name
    should pass through unmolested into the label."""
    roster = tmp_path / "roster.csv"
    roster.write_text(
        "student_id,lms_name,display_name,canonical_name,section,enrollment_status,"
        "add_dt,grade_dt,program,academic_level\n"
        '111111111,"López,María José",María José López,maria jose lopez,01,enrolled,2026-01-21,,,Senior\n'
    )
    cfg = ClassroomSeedConfig(roster=roster, classroom_id="12345", dry_run=True)
    payload = build_payload(cfg)
    assert payload["identifiers"] == ["111111111 — María José López"]


def test_build_payload_empty_roster(tmp_path):
    """All-withdrawn roster → empty identifiers list (not an error)."""
    roster = tmp_path / "roster.csv"
    roster.write_text(
        "student_id,lms_name,display_name,canonical_name,section,enrollment_status,"
        "add_dt,grade_dt,program,academic_level\n"
        '111111111,"Smith,Jane",Jane Smith,jane smith,01,withdrawn,2026-01-21,2026-04-16,,Senior\n'
    )
    cfg = ClassroomSeedConfig(roster=roster, classroom_id="12345", dry_run=True)
    payload = build_payload(cfg)
    assert payload["identifiers"] == []
