"""Importer for Canvas gradebook CSV exports.

Canvas's gradebook export is a real RFC 4180 CSV with three header-area rows
before the first data row:

  Row 0: column headers (per-assignment columns look like "<title> (<canvas_id>)")
  Row 1: per-column "Manual Posting" flags or blanks
  Row 2: "    Points Possible" + per-col max values like "20.00", "100.00"
  Row 3+: actual student rows

This module:

  - parses the raw CSV, skipping metadata rows 1 + 2
  - filters ISA accounts (SIS User ID ending in 'SA') to a side file
  - normalizes into GradeRow dataclasses with per-assignment scores
    collapsed into a JSON object string
  - writes grades.csv, grades.filtered.csv, grades.points-possible.json,
    and preserves the raw input alongside the output

CLI: pa-lms-grades-import <canvas.csv> --out <grades.csv>
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from dataclasses import dataclass, field, fields, asdict
from pathlib import Path

from lectern.student_id import pad_student_id


@dataclass
class GradeRow:
    student_id: str
    display_name: str           # Canvas form "Last, First"
    section_label: str
    final_grade: str
    current_grade: str
    final_score: str
    current_score: str
    override_score: str
    override_grade: str
    assignment_scores: str      # JSON object as string, keyed by stripped title


@dataclass
class FilteredRow:
    student_id: str
    display_name: str
    reason: str


@dataclass
class NormalizedGrades:
    grades: list[GradeRow] = field(default_factory=list)
    filtered: list[FilteredRow] = field(default_factory=list)
    points_possible: dict[str, str] = field(default_factory=dict)


# ── parsing ──────────────────────────────────────────────────────────────────


def parse_canvas_csv(path: Path) -> dict:
    """Parse a Canvas gradebook CSV.

    Returns {'headers': [...], 'points_possible': {col: max},
             'students': [{col: val}, ...]}. Rows 1 (manual-posting) and 2
    (points-possible) are skipped from the student list.
    """
    with path.open("r", newline="", encoding="utf-8") as fh:
        rows = list(csv.reader(fh))

    if len(rows) < 4:
        sys.exit(f"{path}: not enough rows (need >=4, got {len(rows)})")

    headers = rows[0]
    points_possible = {h: v for h, v in zip(headers, rows[2])}
    students = [dict(zip(headers, r)) for r in rows[3:] if any(c.strip() for c in r)]

    return {
        "headers": headers,
        "points_possible": points_possible,
        "students": students,
    }


# ── normalization ────────────────────────────────────────────────────────────

# "<title> (<digits>)" — group 1 = clean title, group 2 = canvas id
_ASSIGNMENT_RE = re.compile(r"^(.*?)\s*\((\d+)\)\s*$")


def _strip_title(col: str) -> str | None:
    """Return the cleaned assignment title if col matches '<title> (<id>)', else None."""
    m = _ASSIGNMENT_RE.match(col)
    if not m:
        return None
    return m.group(1).strip()


# Identity / aggregate columns we never treat as assignments, even if some other
# column happens to match the (digits) pattern.
_RESERVED_COLS = {
    "Student", "ID", "SIS User ID", "SIS Login ID", "Section", "Root Account",
    "Integration ID",
    "Current Score", "Unposted Current Score",
    "Final Score", "Unposted Final Score",
    "Current Grade", "Unposted Current Grade",
    "Final Grade", "Unposted Final Grade",
    "Override Score", "Override Grade", "Override Status",
}


def normalize_grades(parsed: dict) -> NormalizedGrades:
    """Apply schema + ISA filter to a parse_canvas_csv() result."""
    norm = NormalizedGrades(points_possible=dict(parsed["points_possible"]))

    for raw in parsed["students"]:
        sid_raw = (raw.get("SIS User ID") or "").strip()
        display = (raw.get("Student") or "").strip()

        # Test Student filter — Canvas's built-in test/preview account has no
        # SIS User ID (display name is typically "Student, Test"). This is a
        # known Canvas artifact present in every exported gradebook; not a real
        # enrollment, so drop before the roster-join sanity check.
        if not sid_raw:
            norm.filtered.append(FilteredRow(
                student_id=sid_raw,
                display_name=display,
                reason="test_student",
            ))
            continue

        # ISA filter — check SA suffix on raw value, before zero-padding,
        # so the audit CSV preserves the exact form Canvas emitted.
        if sid_raw.endswith("SA"):
            norm.filtered.append(FilteredRow(
                student_id=sid_raw,
                display_name=display,
                reason="isa",
            ))
            continue

        # Defensive zero-pad: Excel/Sheets silently drop the CSULB leading-0
        # on CSV round-trip; we re-pad to 9 digits at every read boundary.
        sid = pad_student_id(sid_raw)

        # Build assignment_scores from columns matching "<title> (<digits>)"
        scores: dict[str, str] = {}
        for col, val in raw.items():
            if col in _RESERVED_COLS:
                continue
            title = _strip_title(col)
            if title is None:
                continue
            # Skip any aggregate-style columns that sneak past the reserved set
            # (Canvas sometimes emits "<bucket> Current Score" etc. without a
            # parenthesized id — those won't match _ASSIGNMENT_RE anyway).
            scores[title] = (val or "").strip()

        norm.grades.append(GradeRow(
            student_id=sid,
            display_name=display,
            section_label=(raw.get("Section") or "").strip(),
            final_grade=(raw.get("Final Grade") or "").strip(),
            current_grade=(raw.get("Current Grade") or "").strip(),
            final_score=(raw.get("Final Score") or "").strip(),
            current_score=(raw.get("Current Score") or "").strip(),
            override_score=(raw.get("Override Score") or "").strip(),
            override_grade=(raw.get("Override Grade") or "").strip(),
            assignment_scores=json.dumps(scores, ensure_ascii=False, sort_keys=True),
        ))

    return norm


# ── writers ──────────────────────────────────────────────────────────────────


def write_grades_csv(norm: NormalizedGrades, out: Path) -> None:
    field_names = [f.name for f in fields(GradeRow)]
    with out.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=field_names)
        writer.writeheader()
        for row in norm.grades:
            writer.writerow(asdict(row))


def write_filtered_csv(norm: NormalizedGrades, out: Path) -> None:
    field_names = [f.name for f in fields(FilteredRow)]
    with out.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=field_names)
        writer.writeheader()
        for row in norm.filtered:
            writer.writerow(asdict(row))


def write_points_possible_json(norm: NormalizedGrades, out: Path) -> None:
    out.write_text(json.dumps(norm.points_possible, ensure_ascii=False,
                              sort_keys=True, indent=2) + "\n", encoding="utf-8")


# ── CLI ──────────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="pa-lms-grades-import",
        description="Parse a Canvas gradebook CSV export into a normalized "
                    "grades CSV + ISA-filtered side file + points-possible JSON.",
    )
    parser.add_argument("csv", type=Path, help="path to Canvas gradebook .csv")
    parser.add_argument("--out", type=Path, required=True, help="output grades.csv path")
    args = parser.parse_args(argv)

    parsed = parse_canvas_csv(args.csv)
    norm = normalize_grades(parsed)

    write_grades_csv(norm, args.out)
    filtered_out = args.out.with_name("grades.filtered.csv")
    pp_out = args.out.with_name("grades.points-possible.json")
    write_filtered_csv(norm, filtered_out)
    write_points_possible_json(norm, pp_out)

    # Preserve original CSV alongside the normalized output for provenance.
    args.out.with_suffix(".raw.csv").write_bytes(args.csv.read_bytes())

    n_filtered = len(norm.filtered)
    suffix = "" if n_filtered == 0 else f", {n_filtered} filtered (ISA accounts)"
    print(f"→ {args.out} ({len(norm.grades)} students normalized{suffix})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
