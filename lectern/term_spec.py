"""Term-spec loader + validator.

A term-spec (``classes/<term>.spec.yaml``) is the human-authored input to
``reg-term-create``: it declares the term boundaries and the sections being
taught. ``load_term_spec`` validates it (jsonschema + uniqueness) and derives
the per-section ``course-dir``.
"""

from __future__ import annotations

from pathlib import Path

import jsonschema
import yaml

from lectern.vault_notes import course_dir


class TermSpecError(Exception):
    """Raised when a term-spec is missing keys, malformed, or has dup sections."""


SCHEMA = {
    "type": "object",
    "required": [
        "term",
        "term-name",
        "year",
        "semester-code",
        "instructor",
        "start",
        "end",
        "finals-week-start",
        "finals-week-end",
        "grade-submission-deadline",
        "sections",
    ],
    "properties": {
        "sections": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": [
                    "course",
                    "section",
                    "class-number",
                    "room",
                    "meets",
                    "enrolled",
                    "final-exam-date",
                ],
            },
        },
    },
}


def load_term_spec(path: Path) -> dict:
    """Load, validate, and enrich a term-spec at ``path``.

    - Validates against :data:`SCHEMA`.
    - Enforces ``(course, section)`` uniqueness.
    - Derives ``course-dir`` on each section.
    """
    path = Path(path)
    spec = yaml.safe_load(path.read_text()) or {}
    try:
        jsonschema.validate(spec, SCHEMA)
    except jsonschema.ValidationError as e:
        loc = "/".join(str(p) for p in e.absolute_path) or "<root>"
        raise TermSpecError(f"invalid term-spec at {loc}: {e.message}") from e

    seen: set[tuple] = set()
    for sec in spec["sections"]:
        key = (sec["course"], str(sec["section"]))
        if key in seen:
            raise TermSpecError(
                f"duplicate section: {sec['course']} §{sec['section']}"
            )
        seen.add(key)
        sec["course-dir"] = course_dir(sec["course"])
    return spec


def stub_spec_text(term: str) -> str:
    """Return a commented YAML stub term-spec with ``term`` filled.

    Validates against :func:`load_term_spec` (one example section).
    """
    return f"""\
# Term-spec for {term} — edit then run `reg-term-create --term {term}`.
# Top-level fields describe the term; `sections` lists what you teach.
term: {term}
term-name: CHANGE ME
year: 2026
semester-code: {term[:2]}
instructor: CHANGE ME
start: 2026-01-01            # first day of instruction (ISO date)
end: 2026-05-01             # last day of instruction
finals-week-start: 2026-05-04
finals-week-end: 2026-05-08
grade-submission-deadline: 2026-05-15
sections:
  - course: CECS 326        # "CECS <num>"
    section: "01"           # 2-digit, quoted
    class-number: 1116      # MyCSULB class number
    room: HC-120
    meets: "TuTh 12:30-13:45"
    enrolled: 0
    final-exam-date: 2026-05-05
"""
