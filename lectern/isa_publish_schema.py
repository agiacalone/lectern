"""JSONSchema validator for the per-bundle isa-publish.yaml manifest.

Each archive bundle that publishes artifacts to Google Drive ships with an
``isa-publish.yaml`` next to its ``manifest.yaml``. The publish manifest tracks
(source_path, drive_path, source_hash, drive_file_id, last_pushed) for every
artifact mirrored to ``Giacalone-ISA/`` so pa-isa-publish can:

  - Skip uploads when the source hash is unchanged (idempotency).
  - Update existing Drive files in place (preserve permissions, shareable links).
  - Detect drift between vault and Drive (``--check`` mode).

This module is the schema layer only. The orchestration lives in
``pa.isa_publish`` and the I/O backends live in ``pa.drive_auth``.

See <vault>/plans/specs/2026-05-13-per-student-exam-id-design Part 6.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import jsonschema
import yaml


SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["publish"],
    "additionalProperties": True,
    "properties": {
        "publish": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["source", "drive_path", "source_hash"],
                "additionalProperties": True,
                "properties": {
                    "source": {"type": "string"},
                    "drive_path": {"type": "string"},
                    "source_hash": {"type": "string"},
                    "last_pushed": {"type": ["string", "null"]},
                    "drive_file_id": {"type": ["string", "null"]},
                },
            },
        },
    },
}


class ISAPublishValidationError(Exception):
    """Raised when an isa-publish manifest fails JSONSchema validation."""


def validate(data: dict) -> None:
    """Validate ``data`` against SCHEMA. Raises ISAPublishValidationError on failure."""
    try:
        jsonschema.validate(instance=data, schema=SCHEMA)
    except jsonschema.ValidationError as e:
        parts: list[str] = []
        for p in e.absolute_path:
            if isinstance(p, int):
                if parts:
                    parts[-1] = f"{parts[-1]}[{p}]"
                else:
                    parts.append(f"[{p}]")
            else:
                parts.append(str(p))
        path = ".".join(parts) if parts else "<root>"

        if e.validator == "required":
            missing = re.search(r"'([^']+)'", e.message)
            missing_name = missing.group(1) if missing else ""
            raise ISAPublishValidationError(
                f"isa-publish invalid at {path}: missing required field '{missing_name}' ({e.message})"
            ) from e

        raise ISAPublishValidationError(
            f"isa-publish invalid at {path}: {e.message}"
        ) from e


def validate_yaml(path: Path) -> dict:
    """Load YAML from ``path``, validate it, and return the loaded dict."""
    path = Path(path)
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ISAPublishValidationError(
            f"isa-publish invalid at <root>: expected mapping at top level, got {type(data).__name__}"
        )
    validate(data)
    return data


def default_manifest() -> dict:
    """Return a minimal valid skeleton: empty publish list."""
    return {"publish": []}
