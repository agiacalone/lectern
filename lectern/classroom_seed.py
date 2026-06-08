"""Pre-seed a GitHub Classroom roster from a MyCSULB enrollment export.

For Su26+ the Google-Form student→github binding retires. Instead, Anthony
pre-creates the Classroom roster with the 9-digit MyCSULB student ID as the
identifier. Students authenticate via GitHub on first assignment-join, picking
their identifier from the list. Result: authoritative (student_id, github_username)
binding via OAuth, no form needed.

Withdrawn rows in the roster are excluded from the seed.

CLI: pa-classroom-roster-seed --csv-roster <csv> --classroom <id>
                              [--dry-run] [--label-format <fmt>]
"""
from __future__ import annotations

import argparse
import csv
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from lectern.student_id import pad_student_id


@dataclass
class ClassroomSeedConfig:
    roster: Path
    classroom_id: str
    dry_run: bool = False
    label_format: str = "{student_id} — {display_name}"


# ── payload ──────────────────────────────────────────────────────────────────


def build_payload(cfg: ClassroomSeedConfig) -> dict:
    """Build the Classroom roster payload from the normalized roster CSV.

    Withdrawn students are dropped. Each remaining row formats into an
    identifier via cfg.label_format.
    """
    identifiers: list[str] = []
    with Path(cfg.roster).open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            status = (row.get("enrollment_status") or "").strip().lower()
            if status == "withdrawn":
                continue
            identifiers.append(
                cfg.label_format.format(
                    # Defensive zero-pad — Classroom roster identifiers are
                    # the binding key OAuth-attests against, so a truncated
                    # leading zero from Excel would create a phantom student.
                    student_id=pad_student_id(row.get("student_id") or ""),
                    display_name=(row.get("display_name") or "").strip(),
                    canonical_name=(row.get("canonical_name") or "").strip(),
                    section=(row.get("section") or "").strip(),
                )
            )
    return {"classroom_id": cfg.classroom_id, "identifiers": identifiers}


# ── seed (shell out to gh) ───────────────────────────────────────────────────


def seed_classroom(cfg: ClassroomSeedConfig) -> int:
    """Execute the seed. POSTs each identifier via `gh api`.

    --dry-run: prints the payload, returns count of identifiers (no gh call).
    Otherwise: for each identifier, POST /classrooms/<id>/roster.
      - 422 / already-exists → treat as already-seeded (log, continue).
      - Other non-zero exit → log, count as error, continue.
      - gh not installed → print clear message, exit 2.

    Returns count of identifiers seeded (or planned for, if dry-run).
    """
    payload = build_payload(cfg)
    idents = payload["identifiers"]

    if cfg.dry_run:
        print(f"── Classroom {cfg.classroom_id} — dry-run ({len(idents)} identifiers) ──")
        for ident in idents:
            print(ident)
        return len(idents)

    seeded = 0
    already = 0
    errors = 0
    for ident in idents:
        try:
            res = subprocess.run(
                ["gh", "api", "-X", "POST",
                 f"/classrooms/{cfg.classroom_id}/roster",
                 "-f", f"identifier={ident}"],
                capture_output=True, text=True, check=False,
            )
        except FileNotFoundError:
            print("error: `gh` not found on PATH — install GitHub CLI to seed",
                  file=sys.stderr)
            return -1
        out = (res.stdout or "") + (res.stderr or "")
        if res.returncode == 0:
            seeded += 1
        elif "422" in out or "already exists" in out.lower() or "already_exists" in out.lower():
            already += 1
            print(f"  · already-seeded: {ident}", file=sys.stderr)
        else:
            errors += 1
            print(f"  ! error seeding {ident!r}: {out.strip()[:200]}", file=sys.stderr)

    total = seeded + already
    print(f"→ Seeded {total} / {len(idents)} identifiers to Classroom "
          f"{cfg.classroom_id} ({already} skipped: already-seeded; {errors} errors).")
    return total


# ── CLI ──────────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="pa-classroom-roster-seed",
        description="Pre-seed a GitHub Classroom roster from a MyCSULB roster CSV.",
    )
    p.add_argument("--csv-roster", type=Path, required=True,
                   help="Normalized roster CSV (from pa-lms-roster-import)")
    p.add_argument("--classroom", required=True,
                   help="GitHub Classroom numeric ID")
    p.add_argument("--dry-run", action="store_true",
                   help="Print payload without calling gh")
    p.add_argument("--label-format", default="{student_id} — {display_name}",
                   help="Python str.format template (default: "
                        "'{student_id} — {display_name}')")
    args = p.parse_args(argv)

    cfg = ClassroomSeedConfig(
        roster=args.csv_roster,
        classroom_id=args.classroom,
        dry_run=args.dry_run,
        label_format=args.label_format,
    )
    rc = seed_classroom(cfg)
    if rc < 0:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
