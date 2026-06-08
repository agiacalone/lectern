"""Tests for pa/isa_publish_schema.py — per-bundle isa-publish.yaml validator."""
from pathlib import Path

import pytest
import yaml

from lectern.isa_publish_schema import (
    SCHEMA,
    ISAPublishValidationError,
    default_manifest,
    validate,
    validate_yaml,
)


def test_default_manifest_validates():
    m = default_manifest()
    validate(m)
    assert m == {"publish": []}


def test_minimal_valid_manifest():
    m = {
        "publish": [
            {
                "source": "exams/478-final-sp26-b_key.pdf",
                "drive_path": "ExampleDept-ISA/SP26/Finals/CECS 478 Final Key.pdf",
                "source_hash": "sha256:abc123",
            }
        ]
    }
    validate(m)  # no raise


def test_full_entry_with_optional_fields():
    m = {
        "publish": [
            {
                "source": "exams/x_key.pdf",
                "drive_path": "ExampleDept-ISA/SP26/Finals/x.pdf",
                "source_hash": "sha256:deadbeef",
                "last_pushed": "2026-05-14T08:00:00-07:00",
                "drive_file_id": "1ABCxyz",
            }
        ]
    }
    validate(m)


def test_missing_required_field():
    m = {
        "publish": [
            {
                "source": "exams/x.pdf",
                "drive_path": "ExampleDept-ISA/SP26/x.pdf",
                # missing source_hash
            }
        ]
    }
    with pytest.raises(ISAPublishValidationError, match="source_hash"):
        validate(m)


def test_invalid_drive_path_type():
    m = {
        "publish": [
            {
                "source": "exams/x.pdf",
                "drive_path": 123,  # not a string
                "source_hash": "sha256:abc",
            }
        ]
    }
    with pytest.raises(ISAPublishValidationError):
        validate(m)


def test_yaml_roundtrip(tmp_path: Path):
    p = tmp_path / "isa-publish.yaml"
    m = {
        "publish": [
            {
                "source": "exams/x_key.pdf",
                "drive_path": "ExampleDept-ISA/SP26/Finals/x.pdf",
                "source_hash": "sha256:abc",
            }
        ]
    }
    p.write_text(yaml.safe_dump(m))
    loaded = validate_yaml(p)
    assert loaded == m


def test_publish_must_be_array():
    m = {"publish": "not a list"}
    with pytest.raises(ISAPublishValidationError):
        validate(m)
