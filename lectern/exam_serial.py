"""Pure functions for the exam serial-ID system.

Two layers:
  - source_serial: 8-hex hash of canonicalized .tex content (variant level)
  - student_serial: 8-hex hash of source_serial + ":" + canonical(name)

Both internal-only — never student-facing.
See <vault>/plans/specs/2026-05-13-per-student-exam-id-design for the full system.
"""
from __future__ import annotations
import hashlib
import re
import unicodedata


def canonical_name(name: str) -> str:
    """Deterministic name → key string for the per-student hash.

    Pipeline: NFKC → strip combining marks → lowercase → collapse whitespace → strip.
    Apostrophes, hyphens, and periods are preserved.
    """
    s = unicodedata.normalize("NFKC", name)
    s = "".join(c for c in unicodedata.normalize("NFD", s)
                if not unicodedata.combining(c))
    s = s.lower()
    s = " ".join(s.split())
    return s


def student_serial(source_serial: str, name: str) -> str:
    """8-hex uppercase derived from variant source_serial + canonical(name)."""
    key = f"{source_serial}:{canonical_name(name)}".encode("utf-8")
    return hashlib.sha256(key).hexdigest()[:8].upper()


_SERIAL_LINE_RE = re.compile(r"\\def\\examserial\{[^}]*\}")
_ANSWERS_FALSE_RE = re.compile(r"\\answersfalse")
_ANSWERS_TRUE_RE = re.compile(r"\\answerstrue")
_KEY_SUFFIX_RE = re.compile(r" --- KEY")


def source_serial_from_tex(tex_content: str) -> str:
    """Compute the variant source serial from canonicalized .tex content.

    Canonicalization (matches exam-tex-doctrine):
      1. strip the existing \\def\\examserial{...} line itself
      2. strip \\answersfalse / \\answerstrue toggles
      3. strip ' --- KEY' cosmetic suffix
      4. SHA-256, first 8 hex, uppercase
    """
    s = _SERIAL_LINE_RE.sub("", tex_content)
    s = _ANSWERS_FALSE_RE.sub("", s)
    s = _ANSWERS_TRUE_RE.sub("", s)
    s = _KEY_SUFFIX_RE.sub("", s)
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:8].upper()
