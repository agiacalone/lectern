"""Triage manifest loader + validator.

A triage manifest (``*.triage.yaml``) defines the assignment metadata, grading
profile, and thresholds for automated triage. ``load_manifest`` validates it
(jsonschema) and applies sensible defaults.
"""

from __future__ import annotations

import datetime
from pathlib import Path

import jsonschema
import yaml

from lectern.triage_guardfile import DEFAULT_GUARD_FILES


class TriageManifestError(Exception):
    """Raised when a triage manifest is missing keys, malformed, or invalid."""


SCHEMA = {
    "type": "object",
    "required": ["assignment", "profile"],
    "properties": {
        "assignment": {
            "type": "object",
            "required": [
                "course",
                "section",
                "term",
                "name",
                "org",
                "repo_prefix",
                "assigned_date",
                "due_date",
                "total_points",
            ],
        },
        "profile": {"enum": ["single-sitting", "short-project", "term-project"]},
        "source": {"enum": ["classroom", "scrape"]},
        "guard_files": {
            "type": "array",
            "items": {
                "oneOf": [
                    {"type": "string"},
                    {
                        "type": "object",
                        "required": ["path"],
                        "properties": {
                            "path": {"type": "string"},
                            "sha256": {"type": "string"},
                        },
                    },
                ]
            },
        },
    },
}


def load_manifest(path: Path) -> dict:
    """Load, validate, and enrich a triage manifest at ``path``.

    - Validates against :data:`SCHEMA`.
    - Applies defaults for ``thresholds``, ``weights``, and ``deliverables``.
    """
    path = Path(path)
    cfg = yaml.safe_load(path.read_text()) or {}
    try:
        jsonschema.validate(cfg, SCHEMA)
    except jsonschema.ValidationError as e:
        loc = "/".join(str(p) for p in e.absolute_path) or "<root>"
        raise TriageManifestError(
            f"invalid triage manifest at {loc}: {e.message}"
        ) from e

    cfg.setdefault("thresholds", {})
    cfg.setdefault("weights", {})
    cfg.setdefault("deliverables", [])
    # Instructor-authored files the student is not asked to edit. Editing or
    # deleting one is a Part A fact, never a score — see triage_guardfile.
    cfg.setdefault("guard_files", list(DEFAULT_GUARD_FILES))

    # Normalize date fields: yaml.safe_load parses bare YAML dates (e.g.
    # ``due_date: 2026-05-16``) into datetime.date objects, but all downstream
    # consumers (scoring engine, report, sweep) expect ISO-format strings.
    asgn = cfg.get("assignment", {})
    for _k in ("assigned_date", "due_date"):
        v = asgn.get(_k)
        if isinstance(v, (datetime.date, datetime.datetime)):
            asgn[_k] = v.isoformat()

    return cfg
