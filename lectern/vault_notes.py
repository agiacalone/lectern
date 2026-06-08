"""Vault note helpers — frontmatter round-trip + course-dir derivation.

Shared utilities for the term lifecycle tools (``term_create`` /
``term_finalize``). Frontmatter is kebab-case YAML between ``---`` fences;
manifests (snake_case) are handled elsewhere.
"""

from __future__ import annotations

import yaml


def course_dir(course: str) -> str:
    """Map a course code to its vault folder.

    ``378`` and ``478`` share the ``378-478`` folder; every other course
    number is its own folder. Takes the trailing token of ``course``.
    """
    num = course.split()[-1]
    if num in ("378", "478"):
        return "378-478"
    return num


def split_frontmatter(text: str) -> tuple[dict, str]:
    """Split a note into (frontmatter dict, body).

    Requires the text to open with a ``---`` fence; raises ``ValueError``
    otherwise. The body is everything after the closing fence line, with its
    leading newline preserved.
    """
    if not text.startswith("---\n"):
        raise ValueError("note does not begin with a frontmatter fence")
    # Find the closing fence: a line that is exactly '---'.
    rest = text[len("---\n"):]
    end = rest.find("\n---")
    if end == -1:
        raise ValueError("unterminated frontmatter fence")
    block = rest[:end]
    # body starts after the closing '---' line (consume the '\n---' and the
    # rest of that fence line up to and including its trailing newline if any).
    after = rest[end + len("\n---"):]
    # `after` begins right after the three dashes; drop to end of that line.
    nl = after.find("\n")
    body = after[nl + 1:] if nl != -1 else ""
    # Preserve a leading newline to match round-trip expectations.
    body = "\n" + body if not body.startswith("\n") else body
    fm = yaml.safe_load(block) or {}
    return fm, body


def _set_dotted(fm: dict, dotted: str, value) -> None:
    parts = dotted.split(".")
    cur = fm
    for p in parts[:-1]:
        nxt = cur.get(p)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[p] = nxt
        cur = nxt
    cur[parts[-1]] = value


def set_frontmatter_fields(text: str, updates: dict) -> str:
    """Apply ``updates`` to a note's frontmatter and reassemble.

    Dotted keys (``"headcount.enrolled"``) traverse/create nested dicts.
    Key order is preserved (PyYAML with ``sort_keys=False``).
    """
    fm, body = split_frontmatter(text)
    for k, v in updates.items():
        if "." in k:
            _set_dotted(fm, k, v)
        else:
            fm[k] = v
    dumped = yaml.dump(
        fm, sort_keys=False, default_flow_style=False, allow_unicode=True
    )
    return "---\n" + dumped + "---" + body
