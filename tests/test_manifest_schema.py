"""Tests for pa/manifest_schema.py — JSONSchema validator for per-section manifest.yaml."""
import pytest
import yaml

from lectern.manifest_schema import (
    SCHEMA,
    ManifestValidationError,
    default_manifest,
    validate_manifest,
    validate_manifest_yaml,
)


def test_default_manifest_skeleton_validates():
    m = default_manifest("CECS 478", "sp26", "04", "Anthony Giacalone")
    validate_manifest(m)  # no raise


def test_default_manifest_required_fields():
    m = default_manifest("CECS 478", "sp26", "04", "Anthony Giacalone")
    assert m["course"] == "CECS 478"
    assert m["term"] == "sp26"
    assert m["section"] == "04"
    assert m["instructor"] == "Anthony Giacalone"
    assert "headcount" in m
    assert "audit" in m


def test_minimal_valid_manifest():
    m = {
        "course": "CECS 478",
        "term": "sp26",
        "section": "04",
        "instructor": "Anthony Giacalone",
        "headcount": {"enrolled": 15, "completed": 13, "withdrew": 2},
        "audit": {"archived": "2026-05-22T10:00:00-07:00", "archived_by": "pa-term-archive"},
    }
    validate_manifest(m)  # no raise


def test_missing_section_invalid():
    m = {
        "course": "CECS 478",
        "term": "sp26",
        "instructor": "Anthony Giacalone",
        "headcount": {"enrolled": 1, "completed": 1, "withdrew": 0},
        "audit": {"archived": "2026-05-22T10:00:00", "archived_by": "test"},
    }
    with pytest.raises(ManifestValidationError, match="section"):
        validate_manifest(m)


def test_course_pattern():
    m = default_manifest("CECS 478", "sp26", "04", "Anthony Giacalone")
    m["course"] = "bad-course"
    with pytest.raises(ManifestValidationError, match="course"):
        validate_manifest(m)


def test_term_pattern():
    m = default_manifest("CECS 478", "sp26", "04", "Anthony Giacalone")
    m["term"] = "spring2026"  # invalid format
    with pytest.raises(ManifestValidationError, match="term"):
        validate_manifest(m)


def test_section_must_be_two_digits():
    m = default_manifest("CECS 478", "sp26", "04", "Anthony Giacalone")
    m["section"] = "4"  # single digit
    with pytest.raises(ManifestValidationError, match="section"):
        validate_manifest(m)


def test_yaml_roundtrip(tmp_path):
    m = default_manifest("CECS 478", "sp26", "04", "Anthony Giacalone")
    m["isa"] = ["Alexa Lee", "Kristen Park"]
    m["exams"] = [{
        "name": "final",
        "tex": "exams/478-final-sp26-b.tex",
        "pdf": "exams/478-final-sp26-b.pdf",
        "source_serial": "DC8C3554",
        "per_student_ids": True,
    }]
    p = tmp_path / "manifest.yaml"
    p.write_text(yaml.safe_dump(m, sort_keys=False))
    loaded = validate_manifest_yaml(p)
    assert loaded["course"] == "CECS 478"
    assert loaded["isa"] == ["Alexa Lee", "Kristen Park"]
    assert loaded["exams"][0]["source_serial"] == "DC8C3554"


def test_negative_headcount_invalid():
    m = default_manifest("CECS 478", "sp26", "04", "Anthony Giacalone")
    m["headcount"]["enrolled"] = -1
    with pytest.raises(ManifestValidationError):
        validate_manifest(m)


def test_optional_fields_accept_null():
    m = default_manifest("CECS 478", "sp26", "04", "Anthony Giacalone")
    m["syllabus"] = {"pdf": None, "serial": None, "repo": None, "repo_commit": None}
    m["roster"] = {"source": None, "exported": None, "csv": None, "rows": None}
    validate_manifest(m)


def test_dfw_rate_bounds():
    m = default_manifest("CECS 478", "sp26", "04", "Anthony Giacalone")
    m["grades"] = {
        "source": "canvas",
        "csv": "grades.csv",
        "rows": 15,
        "distribution": {"A": 5, "B": 5, "C": 3, "D": 1, "F": 1},
        "dfw_rate": 1.5,  # > 1.0 — invalid
    }
    with pytest.raises(ManifestValidationError):
        validate_manifest(m)


def test_schema_is_a_dict():
    """SCHEMA constant is exposed for callers that need to introspect it."""
    assert isinstance(SCHEMA, dict)
    assert SCHEMA["type"] == "object"
    assert "course" in SCHEMA["properties"]
