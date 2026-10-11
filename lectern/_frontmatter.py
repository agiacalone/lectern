"""Obsidian frontmatter for the Markdown summaries lectern writes into the vault.

Grading runs land under ``classes/<course-dir>/archives/<term>-<section>/<run>/``.
The course and term are read from that path so FACTS, REPORT, DRAFTS and TRIAGE
can be found by tag. Outside that layout the course and term tags are omitted.
Per-student writeups get no frontmatter: they are verbatim student text and the
grading input, so they stay byte-identical to the source.
"""
from __future__ import annotations

import re
from pathlib import Path

_TERM_SECTION = re.compile(r"^([a-z]{2}\d{2})-(\d{2})$")


def _course_and_term(path: Path) -> tuple[str | None, str | None]:
    parts = Path(path).resolve().parts
    if "classes" not in parts or "archives" not in parts:
        return None, None
    i = parts.index("classes")
    j = parts.index("archives")
    if j != i + 2 or j + 1 >= len(parts):
        return None, None
    course_dir = parts[i + 1]
    m = _TERM_SECTION.match(parts[j + 1])
    if not m:
        return None, None
    term, section = m.groups()
    nums = course_dir.split("-")
    if len(nums) == 1:
        return f"cecs-{nums[0]}", term
    # A shared folder such as 378-478: the class note names the course.
    classes_dir = Path(*parts[: i + 2])
    for num in nums:
        if (classes_dir / f"{num}-{section}-{term}.md").exists():
            return f"cecs-{num}", term
    return None, term


def frontmatter(path: Path, *, note_type: str, extra_tags: tuple[str, ...] = ()) -> str:
    """Return a frontmatter block (with trailing blank line) for a file at ``path``."""
    course, term = _course_and_term(path)
    tags = ["teaching"]
    if course:
        tags.append(course)
    if term:
        tags.append(f"term-{term}")
    tags += ["grading", *extra_tags, "internal", "private"]
    lines = ["---",
             f"type: {note_type}",
             f"tags: [{', '.join(dict.fromkeys(tags))}]",
             "visibility: private",
             "icon: LiClipboardCheck",
             "iconColor: var(--text-normal)",
             "---", ""]
    return "\n".join(lines) + "\n"
