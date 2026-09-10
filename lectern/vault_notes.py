"""Vault note helpers — frontmatter round-trip + course-dir derivation.

Shared utilities for the term lifecycle tools (``term_create`` /
``term_finalize``). Frontmatter is kebab-case YAML between ``---`` fences;
manifests (snake_case) are handled elsewhere.
"""

from __future__ import annotations

import re

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


def _needs_quotes(s: str) -> bool:
    """True when a bare scalar would be misread by a YAML parser.

    Deliberately permissive about colons: YAML only treats ``": "`` (or a
    trailing colon) as a key separator, so ``2026-07-08T11:31:22-07:00`` and
    ``17:00-19:00`` are safe bare. That matters — quoting them is exactly the
    drift this module used to cause.
    """
    if s == "" or s.strip() != s:
        return True
    if s.lower() in ("true", "false", "yes", "no", "on", "off", "null", "~"):
        return True
    if re.fullmatch(r"[-+]?(\d+\.?\d*|\.\d+)([eE][-+]?\d+)?", s):
        return True
    if s[0] in "-?:,[]{}#&*!|>'\"%@`":
        return True
    return ": " in s or s.endswith(":")


def _fmt(value) -> str:
    """Render a scalar the way the vault writes it by hand."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, (list, tuple)):
        # Flow style: the vault writes `tags: [a, b, c]` by hand, and block
        # style here is exactly the reformatting this function exists to avoid.
        return "[" + ", ".join(_fmt(v) for v in value) + "]"
    if isinstance(value, dict):
        return "{" + ", ".join(f"{k}: {_fmt(v)}" for k, v in value.items()) + "}"
    s = str(value)
    if not _needs_quotes(s):
        return s
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"' 


def _split_fm(text: str) -> tuple[list[str], str]:
    """Return (frontmatter lines, everything from the closing fence onward)."""
    if not text.startswith("---\n"):
        raise ValueError("note does not begin with a frontmatter fence")
    rest = text[4:]
    end = rest.find("\n---")
    if end == -1:
        raise ValueError("unterminated frontmatter fence")
    return rest[:end].split("\n"), rest[end:]


def _block_bounds(lines: list[str], key: str) -> tuple[int, int] | None:
    """Locate ``key:`` at indent 0 and the extent of its indented block."""
    for i, ln in enumerate(lines):
        if re.match(rf"^{re.escape(key)}\s*:", ln):
            j = i + 1
            while j < len(lines) and (lines[j].startswith((" ", "\t")) or not lines[j].strip()):
                j += 1
            return i, j
    return None


def set_frontmatter_fields(text: str, updates: dict) -> str:
    """Apply ``updates`` to a note's frontmatter, changing nothing else.

    Dotted keys (``"headcount.enrolled"``) address a nested block.

    ==This edits the frontmatter as TEXT and never round-trips it through
    PyYAML.== A round-trip rewrites the whole block: flow sequences collapse to
    block style, quoting comes and goes, comments are destroyed, and a parsed
    timestamp is re-emitted as ``2026-07-08 11:31:22-07:00`` — dropping the
    ``T`` that the vault's ``created:`` fields and Dataview's date parsing both
    rely on. That happened to three live class notes on 2026-09-10, which is
    why this function looks the way it does.
    """
    lines, tail = _split_fm(text)

    for key, value in updates.items():
        rendered = _fmt(value)
        if "." not in key:
            pat = re.compile(rf"^{re.escape(key)}\s*:")
            for i, ln in enumerate(lines):
                if pat.match(ln):
                    lines[i] = f"{key}: {rendered}"
                    break
            else:
                lines.append(f"{key}: {rendered}")
            continue

        parent, child = key.split(".", 1)
        bounds = _block_bounds(lines, parent)
        if bounds is None:
            lines.append(f"{parent}:")
            lines.append(f"  {child}: {rendered}")
            continue

        start, stop = bounds
        cpat = re.compile(rf"^(\s+){re.escape(child)}\s*:")
        for i in range(start + 1, stop):
            m = cpat.match(lines[i])
            if m:
                lines[i] = f"{m.group(1)}{child}: {rendered}"
                break
        else:
            indent = "  "
            for i in range(start + 1, stop):
                m = re.match(r"^(\s+)\S", lines[i])
                if m:
                    indent = m.group(1)
                    break
            lines.insert(stop, f"{indent}{child}: {rendered}")

    return "---\n" + "\n".join(lines) + tail
