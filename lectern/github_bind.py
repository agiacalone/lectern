"""Resolve student-id → authoritative GitHub username via 3 source modes.

Modes:
  form      — Google Form CSV (Sp26 path). Dirty data: dup submissions, wrong
              sections, leading whitespace, malformed IDs, swapped name fields.
              Dedups by student_id, flags alternates, leaves roster as section
              source of truth.
  classroom — gh classroom roster CSV (Su26+ path). github_username verified
              by OAuth at link time — no typos possible.
  scrape    — gh api orgs/<org>/repos + prefix filter. v1: surfaces what's in
              the org for human cross-reference. Not auto-bindable to SIDs.

Optional --verify shells out to `gh api users/<u>` for each non-empty username
to confirm GitHub-side existence.

CLI: pa-github-bind --form CSV | --classroom CSV | --scrape
                    --roster CSV [--section NN] [--org ExampleDept-CECS]
                    [--prefix cecs-478-sp26-04] --out github.csv [--verify]
"""
from __future__ import annotations

import argparse
import csv
import re
import subprocess
import sys
from dataclasses import dataclass, asdict, fields
from datetime import datetime
from pathlib import Path


@dataclass
class BindingRow:
    student_id: str
    display_name: str
    github_username: str
    source: str               # 'form' | 'classroom' | 'scrape'
    submitted_at: str         # ISO from form / classroom joined_at
    verified: str             # see header
    notes: str                # comma-separated flags


# ── normalizers ──────────────────────────────────────────────────────────────
# normalize_student_id moved to pa.student_id (2026-05-13) — shared by every
# CSV-read boundary in the pipeline because Excel/Sheets silently truncates
# the leading-zero CSULB IDs on round-trip.

from lectern.student_id import normalize_student_id  # noqa: E402 — kept here for callers


def normalize_username(raw: str) -> str:
    """Strip whitespace, leading @, leading https://github.com/ prefix. Lowercase."""
    u = (raw or "").strip()
    # strip URL prefix (case-insensitive)
    m = re.match(r"^https?://(?:www\.)?github\.com/", u, re.IGNORECASE)
    if m:
        u = u[m.end():]
    u = u.lstrip("@").strip()
    # strip trailing slash
    u = u.rstrip("/").strip()
    return u.lower()


# ── timestamp helpers ────────────────────────────────────────────────────────

def _parse_form_ts(s: str) -> str:
    """Form 'M/D/YYYY H:MM:SS' → ISO 'YYYY-MM-DDTHH:MM:SS'. Best-effort."""
    s = (s or "").strip()
    if not s:
        return ""
    for fmt in ("%m/%d/%Y %H:%M:%S", "%m/%d/%Y %I:%M:%S %p", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(s, fmt).isoformat(timespec="seconds")
        except ValueError:
            continue
    return s  # leave unparsed string in place


# ── roster loader ────────────────────────────────────────────────────────────

def _load_roster(roster_csv: Path) -> list[dict]:
    with Path(roster_csv).open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


# ── form mode ────────────────────────────────────────────────────────────────

# Google Form column names — handle common header variations
_FORM_TS = "Timestamp"
_FORM_LAST = "Last Name"
_FORM_FIRST = "First and Middle Names"
_FORM_SID = "Student ID#"
_FORM_USER = "GitHub Username"


def _form_row_get(row: dict, key: str) -> str:
    # Accept either exact match or startswith (form columns can have parenthetical suffixes)
    if key in row:
        return row[key] or ""
    for k, v in row.items():
        if k and k.startswith(key):
            return v or ""
    return ""


def bind_from_form(
    form_csv: Path,
    roster_csv: Path,
    section: str,
) -> list[BindingRow]:
    """Parse form, dedup by SID, left-join with roster. One BindingRow per roster student."""
    # Parse form into list of dicts keyed by normalized SID
    by_sid: dict[str, list[dict]] = {}
    with Path(form_csv).open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            raw_sid = _form_row_get(row, _FORM_SID)
            sid, sid_flags = normalize_student_id(raw_sid)
            raw_user = _form_row_get(row, _FORM_USER)
            uname = normalize_username(raw_user)
            ts = _parse_form_ts(_form_row_get(row, _FORM_TS))
            by_sid.setdefault(sid, []).append({
                "sid": sid,
                "sid_flags": sid_flags,
                "username": uname,
                "submitted_at": ts,
                "raw_sid": raw_sid,
            })

    # Dedup per SID — collapse to a single canonical entry
    canonical: dict[str, dict] = {}
    for sid, entries in by_sid.items():
        # Sort by submitted_at ascending; latest wins
        entries_sorted = sorted(entries, key=lambda e: e["submitted_at"])
        latest = entries_sorted[-1]
        unames = [e["username"] for e in entries_sorted if e["username"]]
        unique_unames = []
        for u in unames:
            if u not in unique_unames:
                unique_unames.append(u)
        notes_parts: list[str] = []
        flags = list(latest["sid_flags"])
        if flags:
            notes_parts.extend(flags)
        if len(entries) > 1:
            if len(unique_unames) <= 1:
                verified = "consistent_dedup"
            else:
                verified = "unverified"
                # latest is last in list — alternates = others
                latest_u = latest["username"]
                alternates = [u for u in unique_unames if u != latest_u]
                if alternates:
                    notes_parts.append("alternate_usernames:" + ",".join(alternates))
        else:
            verified = "unverified"
        canonical[sid] = {
            "username": latest["username"],
            "submitted_at": latest["submitted_at"],
            "verified": verified,
            "notes_parts": notes_parts,
        }

    # Left-join with roster
    roster = _load_roster(roster_csv)
    out: list[BindingRow] = []
    for r in roster:
        sid = (r.get("student_id") or "").strip()
        display = (r.get("display_name") or "").strip()
        c = canonical.get(sid)
        if c is None:
            out.append(BindingRow(
                student_id=sid,
                display_name=display,
                github_username="",
                source="form",
                submitted_at="",
                verified="missing",
                notes="missing",
            ))
        else:
            out.append(BindingRow(
                student_id=sid,
                display_name=display,
                github_username=c["username"],
                source="form",
                submitted_at=c["submitted_at"],
                verified=c["verified"],
                notes=",".join(c["notes_parts"]),
            ))
    return out


# ── classroom mode ───────────────────────────────────────────────────────────

def bind_from_classroom(classroom_csv: Path, roster_csv: Path) -> list[BindingRow]:
    """Parse Classroom CSV, left-join with roster."""
    by_sid: dict[str, dict] = {}
    with Path(classroom_csv).open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            raw_sid = (row.get("roster_identifier") or "").strip()
            sid, _ = normalize_student_id(raw_sid)
            uname = normalize_username(row.get("github_username") or "")
            joined = (row.get("joined_at") or "").strip()
            by_sid[sid] = {
                "username": uname,
                "joined_at": joined,
            }

    roster = _load_roster(roster_csv)
    out: list[BindingRow] = []
    for r in roster:
        sid = (r.get("student_id") or "").strip()
        display = (r.get("display_name") or "").strip()
        c = by_sid.get(sid)
        if c is None or not c.get("username"):
            out.append(BindingRow(
                student_id=sid,
                display_name=display,
                github_username="",
                source="classroom",
                submitted_at="",
                verified="missing",
                notes="not joined to classroom yet",
            ))
        else:
            out.append(BindingRow(
                student_id=sid,
                display_name=display,
                github_username=c["username"],
                source="classroom",
                submitted_at=c["joined_at"],
                verified="classroom_oauth",
                notes="",
            ))
    return out


# ── scrape mode ──────────────────────────────────────────────────────────────

def bind_from_scrape(org: str, prefix: str, roster_csv: Path) -> tuple[list[BindingRow], list[str]]:
    """List org repos with given prefix; trailing token = github username.

    v1: returns placeholder BindingRows for each roster student plus the raw
    scraped usernames for the caller to surface in an audit report.
    """
    scraped: list[str] = []
    try:
        res = subprocess.run(
            ["gh", "api", f"orgs/{org}/repos", "--paginate", "--jq", ".[].name"],
            capture_output=True, text=True, check=False,
        )
        names = [n.strip() for n in res.stdout.splitlines() if n.strip()]
        for n in names:
            if n.startswith(prefix + "-") or n == prefix:
                # trailing token after last dash
                if "-" in n[len(prefix):]:
                    user = n.rsplit("-", 1)[-1]
                    if user:
                        scraped.append(normalize_username(user))
    except FileNotFoundError:
        # gh not installed
        pass

    roster = _load_roster(roster_csv)
    out: list[BindingRow] = []
    for r in roster:
        sid = (r.get("student_id") or "").strip()
        display = (r.get("display_name") or "").strip()
        out.append(BindingRow(
            student_id=sid,
            display_name=display,
            github_username="",
            source="scrape",
            submitted_at="",
            verified="missing",
            notes="scrape-only: cross-reference manually",
        ))
    return out, scraped


# ── verify ───────────────────────────────────────────────────────────────────

def verify_via_gh(rows: list[BindingRow]) -> list[BindingRow]:
    """Call `gh api users/<u>` for each non-empty username. Mutates rows."""
    for row in rows:
        if not row.github_username:
            continue
        try:
            res = subprocess.run(
                ["gh", "api", f"users/{row.github_username}"],
                capture_output=True, text=True, check=False,
            )
        except FileNotFoundError:
            row.verified = "rate_limited"  # treat missing gh as inability to verify
            return rows
        out = (res.stdout or "") + (res.stderr or "")
        if res.returncode == 0:
            row.verified = "github_exists"
        elif "404" in out or "Not Found" in out:
            row.verified = "github_404"
            row.notes = (row.notes + "," if row.notes else "") + "github_404"
        elif "rate limit" in out.lower() or "API rate limit" in out:
            row.verified = "rate_limited"
        else:
            # Unknown failure; keep existing verified, add a note
            row.notes = (row.notes + "," if row.notes else "") + "verify_failed"
    return rows


# ── writers ──────────────────────────────────────────────────────────────────

_GITHUB_HEADER = [
    "student_id", "display_name", "github_username",
    "source", "submitted_at", "verified", "notes",
]


def write_github_csv(rows: list[BindingRow], path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(_GITHUB_HEADER)
        for r in rows:
            w.writerow([r.student_id, r.display_name, r.github_username,
                        r.source, r.submitted_at, r.verified, r.notes])


def _is_flagged(r: BindingRow) -> bool:
    if r.notes:
        return True
    if r.verified in ("missing", "github_404", "rate_limited"):
        return True
    return False


def write_audit_csv(rows: list[BindingRow], path: Path) -> None:
    flagged = [r for r in rows if _is_flagged(r)]
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(_GITHUB_HEADER)
        for r in flagged:
            w.writerow([r.student_id, r.display_name, r.github_username,
                        r.source, r.submitted_at, r.verified, r.notes])


# ── CLI ──────────────────────────────────────────────────────────────────────

def _audit_path(out: Path) -> Path:
    return out.with_name("github.audit.csv")


def _summarize(rows: list[BindingRow]) -> tuple[int, int, int, int]:
    total = len(rows)
    verified = sum(1 for r in rows if r.verified in (
        "consistent_dedup", "classroom_oauth", "github_exists"))
    missing = sum(1 for r in rows if r.verified == "missing")
    flagged = sum(1 for r in rows if _is_flagged(r))
    return total, verified, missing, flagged


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="pa-github-bind",
        description="Resolve student-id → GitHub username (form/classroom/scrape).")
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--form", type=Path, help="Google Form CSV export")
    src.add_argument("--classroom", type=Path, help="gh classroom roster CSV")
    src.add_argument("--scrape", action="store_true",
                     help="List org repos for cross-reference (v1: audit only)")
    p.add_argument("--roster", type=Path, required=True,
                   help="Normalized roster CSV (from pa-lms-roster-import)")
    p.add_argument("--section", default="",
                   help="Section number (form mode; recorded, doesn't filter)")
    p.add_argument("--org", default="ExampleDept-CECS", help="GitHub org for scrape mode")
    p.add_argument("--prefix", default="", help="Repo-name prefix for scrape mode")
    p.add_argument("--out", type=Path, required=True, help="Output github.csv path")
    p.add_argument("--verify", action="store_true",
                   help="Call `gh api users/<u>` for each username")
    args = p.parse_args(argv)

    scraped: list[str] = []
    if args.form:
        rows = bind_from_form(args.form, args.roster, section=args.section)
    elif args.classroom:
        rows = bind_from_classroom(args.classroom, args.roster)
    elif args.scrape:
        if not args.prefix:
            print("error: --prefix required for --scrape mode", file=sys.stderr)
            return 2
        rows, scraped = bind_from_scrape(args.org, args.prefix, args.roster)
    else:
        return 2  # unreachable

    if args.verify:
        verify_via_gh(rows)

    write_github_csv(rows, args.out)
    audit_path = _audit_path(args.out)
    write_audit_csv(rows, audit_path)

    total, verified, missing, flagged = _summarize(rows)
    print(f"→ {args.out}  ({total} total, {verified} verified, "
          f"{missing} missing, {flagged} flagged)")
    if scraped:
        print(f"  scraped {len(scraped)} repo-usernames in org {args.org} matching {args.prefix!r}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
