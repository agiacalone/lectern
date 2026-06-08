"""CSULB student-ID normalization.

CSULB student IDs are 9 digits with a **leading zero** (e.g. `040100001`).
Spreadsheet tools (Excel, Google Sheets) frequently truncate leading zeros
when opening CSVs — `040100001` becomes the integer `40100001` and gets
re-exported as `40100001` (8 digits). Every CSV-read boundary in the pipeline
must defensively re-pad student IDs to 9 digits.

This module centralizes that normalization so every importer (MyCSULB,
Canvas, GitHub Classroom, Google Form, gradebook, classroom-seed) routes
through the same recipe.

Recipe:
  - Strip non-digit characters, but recognize the legitimate `<letter><8 digits>`
    CSULB form (e.g. `C40100020`) — the letter is a Campus Solutions prefix
    and the 8 digits are the student ID with leading zero already stripped.
  - Zero-pad to 9 digits.
  - Flag malformed input (zero-digit, non-9-digit final after pad-stripping,
    oversized).

The returned `flags` list is diagnostic — callers may surface it as a note
column or drop it.
"""
from __future__ import annotations

import re

_DIGIT_RE = re.compile(r"\d+")
_LETTER_PREFIX_RE = re.compile(r"^[A-Za-z]\d{8}\b")


def normalize_student_id(raw: str) -> tuple[str, list[str]]:
    """Strip non-digits, zero-pad to 9. Flag non-9-digit results.

    Examples
    --------
    >>> normalize_student_id("040100001")
    ('040100001', [])
    >>> normalize_student_id("40100001")            # Excel-truncated zero
    ('040100001', [])
    >>> normalize_student_id("C40100020")           # CSULB letter-prefix form
    ('040100020', [])
    >>> normalize_student_id("401002")[1]
    ['malformed_id_6d']
    >>> normalize_student_id("")
    ('000000000', ['malformed_id_0d'])
    """
    s = (raw or "").strip()
    digits = "".join(_DIGIT_RE.findall(s))
    flags: list[str] = []
    if not digits:
        return ("000000000", ["malformed_id_0d"])
    n = len(digits)
    letter_prefix_8d = bool(_LETTER_PREFIX_RE.match(s))
    if n < 9:
        # 8-digit input is the common Excel-truncation case (leading zero
        # dropped). Don't flag it as malformed — it's the expected shape
        # from a spreadsheet round-trip. Letter-prefix-8d is also legitimate.
        if n != 8 and not (letter_prefix_8d and n == 8):
            flags.append(f"malformed_id_{n}d")
        sid = digits.zfill(9)
    elif n > 9:
        flags.append(f"malformed_id_{n}d")
        sid = digits  # keep all digits — caller can see oversize
    else:
        sid = digits
    return (sid, flags)


def pad_student_id(raw: str) -> str:
    """Quick variant when the caller doesn't need flags — just the padded ID."""
    return normalize_student_id(raw)[0]
