"""Parser for MyCSULB Faculty Center class-roster exports.

The exported file has a .xls extension but is actually HTML — a single <table>
with malformed <tr> tags (no closing tags). This module:

  - parses the malformed HTML into raw column→value dicts
  - normalizes into RosterRow dataclasses with ISO dates + derived names
  - writes a CSV with stable column order

CLI: pa-lms-roster-import <xls> --out <csv> --term <t>
     [--course CECS_NNN --section NN --class-number NNNNN]

If --course/--section/--class-number are omitted, they are inferred from the
filename pattern class-roster-cecs-NNN-NN-NNNNN.xls.
"""
from __future__ import annotations

import argparse
import csv
import html
import re
import sys
from dataclasses import dataclass, fields, asdict
from pathlib import Path

from lectern.exam_serial import canonical_name
from lectern.student_id import pad_student_id


@dataclass
class RosterRow:
    student_id: str
    lms_name: str
    display_name: str
    canonical_name: str
    section: str
    enrollment_status: str
    add_dt: str
    grade_dt: str
    program: str
    academic_level: str


# ── parsing ──────────────────────────────────────────────────────────────────

_TR_OPEN_RE = re.compile(r"<tr[^>]*>", re.IGNORECASE)
_CELL_RE = re.compile(r"<t[hd][^>]*>(.*?)</t[hd]>", re.DOTALL | re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _clean_cell(raw: str) -> str:
    """Strip tags, unescape entities, normalize whitespace + NBSP."""
    text = _TAG_RE.sub("", raw)
    text = html.unescape(text)
    text = text.replace("\xa0", " ")
    text = _WS_RE.sub(" ", text).strip()
    return text


def parse_mycsulb_xls(path: Path) -> list[dict]:
    """Parse malformed-HTML 'xls' → list of {column-header: cell-value} dicts.

    The first <tr> contains <th> header cells; subsequent <tr> blocks are data
    rows. Rows have no closing </tr> — each new <tr> opens the next row.
    """
    content = path.read_text(encoding="utf-8")
    # Split on <tr open. First chunk is everything before the first <tr>.
    chunks = _TR_OPEN_RE.split(content)[1:]
    if not chunks:
        return []

    # Header row drives column keys
    header_cells = [_clean_cell(m) for m in _CELL_RE.findall(chunks[0])]

    rows: list[dict] = []
    for chunk in chunks[1:]:
        cells = [_clean_cell(m) for m in _CELL_RE.findall(chunk)]
        if not cells:
            continue
        row = {}
        for i, header in enumerate(header_cells):
            row[header] = cells[i] if i < len(cells) else ""
        rows.append(row)
    return rows


# ── filename inference ───────────────────────────────────────────────────────

_FILENAME_RE = re.compile(
    r"^class-roster-cecs-(\d{3})-(\d{2})-(\d{5})\.xls$", re.IGNORECASE
)


def infer_from_filename(path: Path) -> dict:
    m = _FILENAME_RE.match(path.name)
    if not m:
        return {}
    course_num, section, class_number = m.groups()
    return {
        "course": f"CECS {course_num}",
        "section": section,
        "class_number": class_number,
    }


# ── normalization ────────────────────────────────────────────────────────────

_DATE_RE = re.compile(r"^(\d{2})/(\d{2})/(\d{4})$")


def _convert_date(s: str) -> str:
    """MM/DD/YYYY → YYYY-MM-DD; '' or invalid → ''."""
    if not s:
        return ""
    m = _DATE_RE.match(s.strip())
    if not m:
        return ""
    mo, da, yr = m.groups()
    return f"{yr}-{mo}-{da}"


def _split_lms_name(lms_name: str) -> tuple[str, str]:
    """'Last,First Middle' → (display='First Middle Last', canonical key).

    Comma is the split point. If no comma, treat the whole thing as display.
    """
    if "," in lms_name:
        last, rest = lms_name.split(",", 1)
        display = f"{rest.strip()} {last.strip()}".strip()
    else:
        display = lms_name.strip()
    return display, canonical_name(display)


def _flatten(s: str) -> str:
    """Collapse internal newlines/whitespace — for the 'Program and Plan' field."""
    return _WS_RE.sub(" ", s).strip()


def normalize_to_roster_csv(
    raw_rows: list[dict],
    course: str,
    section: str,
    class_number: str,
    term: str,
) -> list[RosterRow]:
    out: list[RosterRow] = []
    for raw in raw_rows:
        lms_name = raw.get("Name", "").strip()
        if not lms_name:
            sys.exit(f"empty name in roster row: {raw!r}")
        display, canon = _split_lms_name(lms_name)
        status_note = raw.get("Status Note", "").strip()
        enrollment = "withdrawn" if status_note.lower() == "withdrawn" else "enrolled"
        out.append(
            RosterRow(
                student_id=pad_student_id(raw.get("ID", "")),
                lms_name=lms_name,
                display_name=display,
                canonical_name=canon,
                section=section,
                enrollment_status=enrollment,
                add_dt=_convert_date(raw.get("Add Dt", "")),
                grade_dt=_convert_date(raw.get("Grade Dt", "")),
                program=_flatten(raw.get("Program and Plan", "")),
                academic_level=raw.get("Academic Level", "").strip(),
            )
        )
    return out


# ── CSV writer ───────────────────────────────────────────────────────────────


def write_roster_csv(rows: list[RosterRow], path: Path) -> None:
    field_names = [f.name for f in fields(RosterRow)]
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=field_names)
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))


# ── CLI ──────────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="pa-lms-roster-import",
        description="Parse a MyCSULB Faculty Center roster export (HTML-as-xls) "
                    "into a normalized roster CSV.",
    )
    parser.add_argument("xls", type=Path, help="path to class-roster-*.xls")
    parser.add_argument("--out", type=Path, required=True, help="output CSV path")
    parser.add_argument("--term", required=True, help="term code (e.g. sp26)")
    parser.add_argument("--course", help="e.g. 'CECS 478' (else inferred from filename)")
    parser.add_argument("--section", help="e.g. '04' (else inferred from filename)")
    parser.add_argument("--class-number", help="e.g. '12548' (else inferred from filename)")
    args = parser.parse_args(argv)

    inferred = infer_from_filename(args.xls)
    course = args.course or inferred.get("course")
    section = args.section or inferred.get("section")
    class_number = args.class_number or inferred.get("class_number")

    missing = [k for k, v in (("course", course), ("section", section),
                              ("class_number", class_number)) if not v]
    if missing:
        parser.error(
            f"filename {args.xls.name!r} doesn't match the "
            f"class-roster-cecs-NNN-NN-NNNNN.xls pattern; pass --{', --'.join(missing)} explicitly"
        )

    raw = parse_mycsulb_xls(args.xls)
    norm = normalize_to_roster_csv(raw, course=course, section=section,
                                   class_number=class_number, term=args.term)
    write_roster_csv(norm, args.out)

    # Preserve original .xls alongside the CSV for provenance.
    args.out.with_suffix(".raw.xls").write_bytes(args.xls.read_bytes())

    withdrawn = sum(1 for r in norm if r.enrollment_status == "withdrawn")
    print(f"→ {args.out} ({len(norm)} rows; {withdrawn} withdrawn)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
