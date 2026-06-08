"""JSONSchema validator for the per-section archive bundle manifest.yaml.

Every archive bundle at <vault-root>/classes/<course>/archives/<term>-<section>/
ships with a manifest.yaml that records what was archived, when, with what
serials/headcounts/grade distribution. This module:

  1. Defines the canonical schema (JSONSchema draft 2020-12).
  2. Validates an in-memory dict OR a YAML file against the schema.
  3. Provides default_manifest(course, term, section, instructor) — a minimal
     valid skeleton suitable for in-progress bundles during Sp26 backfill.

Optional fields are permissive (allow null/missing) so partial-bundle states
still validate while the term archive accumulates artifacts over the semester.

See docs/design/per-student-exam-id-design Part 2 for the
full doctrine.
"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

import jsonschema
import yaml


# ---------------------------------------------------------------------------
# Pattern constants — exposed for callers that want to validate inputs
# before constructing a manifest.
# ---------------------------------------------------------------------------

COURSE_RE = r"^CECS \d+$"
TERM_RE = r"^(sp|su|fa|wi)\d{2}$"
SECTION_RE = r"^\d{2}$"


# ---------------------------------------------------------------------------
# Schema — embedded as a Python dict for zero-IO loading.
# ---------------------------------------------------------------------------

SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["course", "term", "section", "instructor", "headcount", "audit"],
    "additionalProperties": True,
    "properties": {
        "course": {"type": "string", "pattern": COURSE_RE},
        "term": {"type": "string", "pattern": TERM_RE},
        "section": {"type": "string", "pattern": SECTION_RE},
        "class_number": {"type": ["string", "null"]},
        "instructor": {"type": "string"},
        "isa": {"type": "array", "items": {"type": "string"}},
        "headcount": {
            "type": "object",
            "required": ["enrolled", "completed", "withdrew"],
            "properties": {
                "enrolled": {"type": "integer", "minimum": 0},
                "completed": {"type": "integer", "minimum": 0},
                "withdrew": {"type": "integer", "minimum": 0},
            },
        },
        "schedule": {
            "type": "object",
            "properties": {
                "meets": {"type": ["string", "null"]},
                "room": {"type": ["string", "null"]},
                "first_day": {"type": ["string", "null"]},
                "last_day": {"type": ["string", "null"]},
                "final_exam": {"type": ["string", "null"]},
            },
        },
        "syllabus": {
            "type": "object",
            "properties": {
                "pdf": {"type": ["string", "null"]},
                "serial": {"type": ["string", "null"]},
                "repo": {"type": ["string", "null"]},
                "repo_commit": {"type": ["string", "null"]},
            },
        },
        "lectures": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["file"],
                "properties": {
                    "file": {"type": "string"},
                    "delivered": {"type": ["string", "null"]},
                },
            },
        },
        "labs": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["name"],
                "properties": {
                    "name": {"type": "string"},
                    "template_repo": {"type": ["string", "null"]},
                    "template_commit": {"type": ["string", "null"]},
                    "serial": {"type": ["string", "null"]},
                    "due": {"type": ["string", "null"]},
                },
            },
        },
        "exams": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["name"],
                "properties": {
                    "name": {"type": "string"},
                    "tex": {"type": ["string", "null"]},
                    "pdf": {"type": ["string", "null"]},
                    "key_pdf": {"type": ["string", "null"]},
                    "spec_json": {"type": ["string", "null"]},
                    "serials_csv": {"type": ["string", "null"]},
                    "administered": {"type": ["string", "null"]},
                    "source_serial": {"type": ["string", "null"]},
                    "per_student_ids": {"type": "boolean"},
                    "headcount_present": {"type": ["integer", "null"], "minimum": 0},
                },
            },
        },
        "roster": {
            "type": "object",
            "properties": {
                "source": {"type": ["string", "null"]},
                "exported": {"type": ["string", "null"]},
                "csv": {"type": ["string", "null"]},
                "rows": {"type": ["integer", "null"], "minimum": 0},
            },
        },
        "grades": {
            "type": "object",
            "properties": {
                "source": {"type": ["string", "null"]},
                "exported": {"type": ["string", "null"]},
                "csv": {"type": ["string", "null"]},
                "rows": {"type": ["integer", "null"], "minimum": 0},
                "distribution": {
                    "type": "object",
                    "additionalProperties": {"type": "integer", "minimum": 0},
                },
                "dfw_rate": {"type": ["number", "null"], "minimum": 0, "maximum": 1},
            },
        },
        "github": {
            "type": "object",
            "properties": {
                "source": {"type": ["string", "null"]},
                "csv": {"type": ["string", "null"]},
                "raw": {"type": ["string", "null"]},
                "audit": {"type": ["string", "null"]},
                "rows": {"type": ["integer", "null"], "minimum": 0},
                "verified": {"type": ["integer", "null"], "minimum": 0},
                "unverified": {"type": ["integer", "null"], "minimum": 0},
                "missing": {"type": ["integer", "null"], "minimum": 0},
                "flagged": {"type": ["integer", "null"], "minimum": 0},
                "verified_at": {"type": ["string", "null"]},
            },
        },
        "audit": {
            "type": "object",
            "required": ["archived", "archived_by"],
            "properties": {
                "archived": {"type": "string"},
                "archived_by": {"type": "string"},
                "notes": {"type": ["string", "null"]},
            },
        },
    },
}


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class ManifestValidationError(Exception):
    """Raised when a manifest fails JSONSchema validation.

    Wraps jsonschema.ValidationError with the validation path in the message
    so callers (and pa-term-archive) get a single readable line.
    """


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def validate_manifest(data: dict) -> None:
    """Validate ``data`` against SCHEMA.

    Raises ManifestValidationError on failure. Returns None on success.
    """
    try:
        jsonschema.validate(instance=data, schema=SCHEMA)
    except jsonschema.ValidationError as e:
        # Build a path like "headcount.enrolled" or "exams[0].name" for context.
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

        # Include the failing property name in the message when validation
        # tripped on a "required" rule, so tests/users can grep for e.g. "section".
        validator = e.validator
        if validator == "required":
            missing = re.search(r"'([^']+)'", e.message)
            missing_name = missing.group(1) if missing else ""
            raise ManifestValidationError(
                f"manifest invalid at {path}: missing required field '{missing_name}' ({e.message})"
            ) from e

        raise ManifestValidationError(
            f"manifest invalid at {path}: {e.message}"
        ) from e


def validate_manifest_yaml(path: Path) -> dict:
    """Load YAML from ``path`` and validate it. Returns the loaded dict on success."""
    path = Path(path)
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ManifestValidationError(
            f"manifest invalid at <root>: expected mapping at top level, got {type(data).__name__}"
        )
    validate_manifest(data)
    return data


def default_manifest(course: str, term: str, section: str, instructor: str) -> dict:
    """Return a minimal valid manifest skeleton for in-progress bundles.

    Pre-populates required fields and seeds empty containers for the optional
    sections that pa-term-archive will fill in over the semester.

    Validates the inputs match the expected patterns up-front so a malformed
    skeleton can't escape into the rest of the pipeline.
    """
    if not re.match(COURSE_RE, course):
        raise ManifestValidationError(
            f"default_manifest: course '{course}' does not match {COURSE_RE!r}"
        )
    if not re.match(TERM_RE, term):
        raise ManifestValidationError(
            f"default_manifest: term '{term}' does not match {TERM_RE!r}"
        )
    if not re.match(SECTION_RE, section):
        raise ManifestValidationError(
            f"default_manifest: section '{section}' does not match {SECTION_RE!r}"
        )
    if not instructor or not isinstance(instructor, str):
        raise ManifestValidationError(
            "default_manifest: instructor must be a non-empty string"
        )

    now_iso = datetime.now().astimezone().isoformat()

    manifest: dict[str, Any] = {
        "course": course,
        "term": term,
        "section": section,
        "class_number": None,
        "instructor": instructor,
        "isa": [],
        "headcount": {
            "enrolled": 0,
            "completed": 0,
            "withdrew": 0,
        },
        "schedule": {
            "meets": None,
            "room": None,
            "first_day": None,
            "last_day": None,
            "final_exam": None,
        },
        "syllabus": {
            "pdf": None,
            "serial": None,
            "repo": None,
            "repo_commit": None,
        },
        "lectures": [],
        "labs": [],
        "exams": [],
        "roster": {
            "source": None,
            "exported": None,
            "csv": None,
            "rows": None,
        },
        "grades": {
            "source": None,
            "exported": None,
            "csv": None,
            "rows": None,
            "distribution": {},
            "dfw_rate": None,
        },
        "github": {
            "source": None,
            "csv": None,
            "raw": None,
            "audit": None,
            "rows": None,
            "verified": None,
            "unverified": None,
            "missing": None,
            "flagged": None,
            "verified_at": None,
        },
        "audit": {
            "archived": now_iso,
            "archived_by": "pa-term-archive",
            "notes": None,
        },
    }

    # Sanity check: the skeleton we just built must itself validate.
    # If this fails we have a bug, not a user-input problem.
    validate_manifest(manifest)
    return manifest
