"""``reg-canvas`` — the Canvas API half of lectern.

Every Canvas step lectern used to hand back as "now paste this into Canvas"
has a subcommand here. The vault stays the proprietary record and Canvas
stays student-facing; the API only removes the copy-and-paste between them.

Read-only:

- ``whoami``         check the token
- ``courses``        list your courses; ``--bind`` records each section's
                     Canvas course id in its class note
- ``grades-export``  the gradebook, as the same CSV Canvas's *Export* button
                     writes, so ``reg-lms-grades-import`` and
                     ``reg-gradebook export-canvas --template`` take it unchanged
- ``roster-check``   diff Canvas enrolments against the registrar roster
- ``audit``          find ungraded or unposted work and gradebook settings
                     that skew the weighted score
                     (:mod:`lectern.canvas_grading`)

Writes (**dry run unless ``--apply``**):

- ``grades-push``    apply a Canvas-format import CSV, changed cells only
- ``announce``       post an announcement (e.g. ``reg-c50 post``'s ANNOUNCE.md)
- ``discussion``     create a discussion topic, unpublished by default
- ``assignment``     create an assignment (``--lab N`` fills it from the vault)
- ``syllabus``       set the syllabus page, refusing a file without its serial
- ``discussions``    grade discussion assignments by post count: ``review``
                     writes the short list to judge, ``apply`` sets scores
                     and likes (:mod:`lectern.canvas_grading`)

Data scope is what the instructor already does by hand: roster and grades
for their own sections, and reading discussion posts to grade them. ``grades-export`` reads scores through the
submissions endpoint but keeps only score fields (:data:`SCORE_FIELDS`);
submission content is dropped as each page arrives and never written.

Targets resolve from the vault: ``--term`` + ``--course`` / ``--section`` →
the term-spec's sections → each class note's ``canvas.course-id`` (written by
``courses --bind``). ``--course-id`` bypasses the vault, for the sandbox.
"""
from __future__ import annotations

import argparse
import csv
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from lectern import canvas_grading
from lectern.canvas_api import CanvasClient, CanvasError
from lectern.c50 import C50Error, class_note_path, sections_for, spec_path
from lectern.student_id import pad_student_id
from lectern.term_spec import TermSpecError, load_term_spec
from lectern.vault_notes import course_dir, set_frontmatter_fields, split_frontmatter

# The only submission fields lectern keeps. Everything else the endpoint
# returns (body, url, attachments, preview links) is discarded on arrival.
SCORE_FIELDS = ("user_id", "assignment_id", "score", "grade", "excused",
                "missing", "late", "workflow_state")

IDENTITY_COLS = ["Student", "ID", "SIS User ID", "SIS Login ID", "Section"]
TOTAL_COLS = [
    ("Current Score", "current_score"),
    ("Unposted Current Score", "unposted_current_score"),
    ("Final Score", "final_score"),
    ("Unposted Final Score", "unposted_final_score"),
    ("Current Grade", "current_grade"),
    ("Unposted Current Grade", "unposted_current_grade"),
    ("Final Grade", "final_grade"),
    ("Unposted Final Grade", "unposted_final_grade"),
    ("Override Score", "override_score"),
    ("Override Grade", "override_grade"),
    ("Override Status", "override_status"),
]
# Canvas's points row marks the totals "(read only)" but leaves these blank.
_POINTS_BLANK = {"Override Score", "Override Status"}
_ASSIGNMENT_COL = re.compile(r"^(.*?)\s*\((\d+)\)\s*$")


class CanvasCmdError(Exception):
    """A user-facing failure of a ``reg-canvas`` command."""


@dataclass
class Target:
    """One Canvas course to act on, with the vault section it came from."""

    course_id: int
    label: str
    section: dict | None = None
    class_note: Path | None = None


# ── target resolution ────────────────────────────────────────────────────────


def resolve_targets(args) -> list[Target]:
    """Turn ``--course-id`` or ``--term``/``--course``/``--section`` into targets."""
    if getattr(args, "course_id", None):
        sec = {"section": args.section, "course": args.course} if args.section else None
        return [Target(int(args.course_id), "Canvas", sec)]
    if not (args.term and args.vault_root):
        raise CanvasCmdError("pass --term and --vault-root, or --course-id")
    vault = Path(args.vault_root)
    spec = load_term_spec(spec_path(vault, args.term))
    out = []
    for sec in sections_for(spec, args.course, args.section):
        note = class_note_path(vault, sec, args.term)
        cid = canvas_course_id(note)
        label = f"{sec['course']} §{sec['section']}"
        if cid is None:
            raise CanvasCmdError(
                f"{label}: no canvas.course-id in {note.name}; run "
                f"reg-canvas courses --bind --term {args.term} --vault-root {args.vault_root}")
        out.append(Target(cid, label, sec, note))
    return out


def canvas_course_id(note: Path) -> int | None:
    if not note.exists():
        return None
    fm, _ = split_frontmatter(note.read_text(encoding="utf-8"))
    cid = (fm.get("canvas") or {}).get("course-id")
    return int(cid) if cid else None


def expand_path(template: str, target: Target, term: str | None) -> Path:
    """Fill ``{section}``/``{term}``/``{course}`` in a per-section file argument."""
    sec = target.section or {}
    if "{" in template and not sec.get("section"):
        raise CanvasCmdError(f"{template}: placeholders need --section with --course-id")
    num = str(sec.get("course", "")).split()[-1] if sec.get("course") else ""
    return Path(template.format(section=sec.get("section", ""), term=term or "", course=num))


# ── courses / bind ───────────────────────────────────────────────────────────


def teacher_courses(client: CanvasClient) -> list[dict]:
    return list(client.get_all("courses", [
        ("enrollment_type", "teacher"), ("include[]", "term"),
        ("state[]", "available"), ("state[]", "unpublished"),
    ]))


def match_course(courses: list[dict], sec: dict, term_name: str | None) -> dict:
    """Find the one Canvas course for a term-spec section.

    CSULB names shells ``CECS 326 Sec01 1131 Operating Systems``. The class
    number is the strongest key, but class numbers recur across years, so a
    tie is broken by the Canvas term name (``Fall 2026``) when the spec has one.
    """
    num = str(sec["course"]).split()[-1]
    cls = str(sec.get("class-number", ""))
    pat = re.compile(rf"\b{re.escape(num)}\b.*\bSec\s*0*{int(sec['section'])}\b.*\b{re.escape(cls)}\b")
    hits = [c for c in courses if cls and pat.search(c.get("name", ""))]
    if len(hits) > 1 and term_name:
        words = term_name.lower().split()
        narrowed = [c for c in hits
                    if all(w in str((c.get("term") or {}).get("name", "")).lower() for w in words)]
        hits = narrowed or hits
    if len(hits) != 1:
        found = ", ".join(f"{c['id']} {c.get('name')}" for c in hits) or "none"
        raise CanvasCmdError(
            f"{sec['course']} §{sec['section']} (class {cls}): expected one Canvas course, "
            f"found {found}. Bind it by hand with canvas.course-id in the class note.")
    return hits[0]


def cmd_whoami(client: CanvasClient, args) -> int:
    me = client.get("users/self")
    print(f"Canvas OK: {me.get('name')} (user {me.get('id')}) at {client.base}")
    return 0


def cmd_courses(client: CanvasClient, args) -> int:
    courses = teacher_courses(client)
    if not args.bind:
        for c in sorted(courses, key=lambda c: c["id"], reverse=True):
            term = (c.get("term") or {}).get("name", "")
            print(f"{c['id']:>8}  {c.get('workflow_state', ''):<11}  {term:<14}  {c.get('name')}")
        return 0
    if not (args.term and args.vault_root):
        raise CanvasCmdError("--bind needs --term and --vault-root")
    vault = Path(args.vault_root)
    spec = load_term_spec(spec_path(vault, args.term))
    for sec in sections_for(spec, args.course, args.section):
        c = match_course(courses, sec, spec.get("term-name"))
        note = class_note_path(vault, sec, args.term)
        label = f"{sec['course']} §{sec['section']}"
        if canvas_course_id(note) == c["id"]:
            print(f"{label}: {c['id']} (already bound)")
            continue
        print(f"{label}: {c['id']} {c.get('name')}")
        if args.dry_run or not note.exists():
            if not note.exists():
                print(f"  no class note at {note}")
            continue
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        note.write_text(set_frontmatter_fields(note.read_text(encoding="utf-8"), {
            "canvas.course-id": c["id"],
            "canvas.url": f"{client.base}/courses/{c['id']}",
            "updated": now,
        }), encoding="utf-8")
        print(f"  bound in {note.relative_to(vault)}")
    return 0


# ── gradebook read ───────────────────────────────────────────────────────────


@dataclass
class Gradebook:
    assignments: list[dict]          # gradebook column order
    students: list[dict]             # one per user: user, sections, grades
    scores: dict[tuple[int, int], dict]  # (user_id, assignment_id) → SCORE_FIELDS


def read_gradebook(client: CanvasClient, course_id: int, include_inactive: bool = False) -> Gradebook:
    """Read assignments, student enrolments and scores for one course."""
    groups = {g["id"]: g.get("position", 0)
              for g in client.get_all(f"courses/{course_id}/assignment_groups")}
    assignments = [
        a for a in client.get_all(f"courses/{course_id}/assignments")
        if a.get("published", True) and not a.get("hide_in_gradebook")
    ]
    assignments.sort(key=lambda a: (groups.get(a.get("assignment_group_id"), 0),
                                    a.get("position") or 0, a["id"]))

    sections = {s["id"]: s.get("name", "")
                for s in client.get_all(f"courses/{course_id}/sections")}
    states = ["active", "invited"] + (["inactive", "completed"] if include_inactive else [])
    params = [("type[]", "StudentEnrollment")] + [("state[]", s) for s in states]
    by_user: dict[int, dict] = {}
    for e in client.get_all(f"courses/{course_id}/enrollments", params):
        uid = e["user_id"]
        rec = by_user.setdefault(uid, {"user": e.get("user") or {}, "sections": [],
                                       "grades": e.get("grades") or {}})
        name = sections.get(e.get("course_section_id"), "")
        if name and name not in rec["sections"]:
            rec["sections"].append(name)

    scores: dict[tuple[int, int], dict] = {}
    for s in client.get_all(f"courses/{course_id}/students/submissions",
                            [("student_ids[]", "all")]):
        kept = {k: s.get(k) for k in SCORE_FIELDS}
        scores[(kept["user_id"], kept["assignment_id"])] = kept

    students = sorted(by_user.values(),
                      key=lambda r: (r["user"].get("sortable_name") or "").lower())
    return Gradebook(assignments, students, scores)


def _num(v) -> str:
    if v is None or v == "":
        return ""
    try:
        return f"{float(v):.2f}"
    except (TypeError, ValueError):
        return str(v)


def assignment_header(a: dict) -> str:
    return f"{a['name']} ({a['id']})"


def gradebook_rows(gb: Gradebook) -> list[list[str]]:
    """Render a :class:`Gradebook` as Canvas's export: three header rows, then students."""
    headers = IDENTITY_COLS + [assignment_header(a) for a in gb.assignments] + [c for c, _ in TOTAL_COLS]
    posting = [""] * len(IDENTITY_COLS) + [
        "Manual Posting" if a.get("post_manually") else "" for a in gb.assignments
    ] + [""] * len(TOTAL_COLS)
    points = ["    Points Possible"] + [""] * (len(IDENTITY_COLS) - 1) + [
        _num(a.get("points_possible")) for a in gb.assignments
    ] + ["" if c in _POINTS_BLANK else "(read only)" for c, _ in TOTAL_COLS]
    rows = [headers, posting, points]
    for st in gb.students:
        u, g = st["user"], st["grades"]
        row = [u.get("sortable_name") or u.get("name") or "", str(u.get("id", "")),
               u.get("sis_user_id") or "", u.get("login_id") or "", ", ".join(st["sections"])]
        for a in gb.assignments:
            s = gb.scores.get((u.get("id"), a["id"]))
            if not s:
                row.append("")
            elif s.get("excused"):
                row.append("EX")
            else:
                row.append(_num(s.get("score")))
        for _, key in TOTAL_COLS:
            val = g.get(key)
            row.append(_num(val) if key.endswith("score") else (val or ""))
        rows.append(row)
    return rows


def write_csv(rows: list[list[str]], path: Path) -> None:
    """Write student data owner-only (mode 600): it is a FERPA record."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch(mode=0o600, exist_ok=True)
    path.chmod(0o600)
    with path.open("w", newline="", encoding="utf-8") as fh:
        csv.writer(fh).writerows(rows)


def default_export_path(vault: Path, target: Target, term: str, stamp: str) -> Path:
    sec = target.section
    num = sec["course"].split()[-1]
    dept = sec["course"].split()[0]
    return (vault / "classes" / course_dir(sec["course"]) / "archives" / f"{term}-{sec['section']}"
            / "canvas" / f"{stamp}_Grades-{dept}_{num}_Sec{sec['section']}.csv")


def cmd_grades_export(client: CanvasClient, args) -> int:
    stamp = datetime.now().strftime("%Y-%m-%dT%H%M")
    for t in resolve_targets(args):
        gb = read_gradebook(client, t.course_id, args.include_inactive)
        rows = gradebook_rows(gb)
        if args.stdout:
            csv.writer(sys.stdout).writerows(rows)
            continue
        if args.out:
            dest = expand_path(args.out, t, args.term)
            if dest.suffix != ".csv":
                dest = dest / f"{stamp}_Grades-course-{t.course_id}.csv"
        elif t.section and args.vault_root:
            dest = default_export_path(Path(args.vault_root), t, args.term, stamp)
        else:
            raise CanvasCmdError("--course-id needs --out")
        write_csv(rows, dest)
        print(f"{t.label}: {len(gb.students)} students × {len(gb.assignments)} assignments → {dest}")
        # The archive layout keeps exports in <archive>/canvas/ beside grades.csv.
        grades = (dest.parent.parent if dest.parent.name == "canvas" else dest.parent) / "grades.csv"
        if args.do_import:
            from lectern import lms_grades
            extra = ["--exclude-sis", *args.exclude_sis] if args.exclude_sis else []
            lms_grades.main([str(dest), "--out", str(grades), *extra])
        else:
            print(f"  next: reg-lms-grades-import {dest} --out {grades}")
    return 0


# ── roster check ─────────────────────────────────────────────────────────────


def read_roster_ids(path: Path) -> dict[str, str]:
    """``student_id → display name`` from a ``reg-lms-roster-import`` CSV."""
    with path.open(newline="", encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    if rows and "student_id" not in rows[0]:
        raise CanvasCmdError(f"{path}: no student_id column (is this a reg-lms-roster-import CSV?)")
    return {pad_student_id(r["student_id"]): r.get("display_name") or r.get("lms_name", "")
            for r in rows if (r.get("enrollment_status") or "Enrolled").lower() != "dropped"}


def cmd_roster_check(client: CanvasClient, args) -> int:
    drift = 0
    for t in resolve_targets(args):
        roster = read_roster_ids(expand_path(args.roster, t, args.term))
        canvas = {}
        for e in client.get_all(f"courses/{t.course_id}/enrollments",
                                [("type[]", "StudentEnrollment"), ("state[]", "active"),
                                 ("state[]", "invited")]):
            u = e.get("user") or {}
            sis = u.get("sis_user_id") or ""
            if sis and not sis.endswith("SA"):
                canvas[pad_student_id(sis)] = u.get("sortable_name", "")
        only_canvas = sorted(set(canvas) - set(roster))
        only_roster = sorted(set(roster) - set(canvas))
        print(f"{t.label}: roster {len(roster)}, Canvas {len(canvas)}, "
              f"matched {len(set(canvas) & set(roster))}")
        for sid in only_canvas:
            print(f"  in Canvas only (drop still in the shell?)  {sid}  {canvas[sid]}")
        for sid in only_roster:
            print(f"  in roster only (add not yet in Canvas?)    {sid}  {roster[sid]}")
        drift += len(only_canvas) + len(only_roster)
    return 1 if drift else 0


# ── grades push ──────────────────────────────────────────────────────────────


@dataclass
class Change:
    user_id: int
    sis: str
    name: str
    assignment_id: int
    assignment: str
    old: str
    new: str


def parse_import_csv(path: Path) -> tuple[dict[int, str], list[dict]]:
    """Read a Canvas-format import CSV → (assignment id → title, student rows)."""
    with path.open(newline="", encoding="utf-8-sig") as fh:
        rows = list(csv.reader(fh))
    if not rows:
        raise CanvasCmdError(f"{path}: empty")
    headers = rows[0]
    if "SIS User ID" not in headers:
        raise CanvasCmdError(f"{path}: no 'SIS User ID' column; expected a Canvas-format CSV")
    cols = {}
    for h in headers:
        m = _ASSIGNMENT_COL.match(h)
        if m and h not in {c for c, _ in TOTAL_COLS}:
            cols[int(m.group(2))] = h
    # The posting and points-possible rows carry no SIS User ID, so this one
    # filter drops both along with blank lines.
    body = [dict(zip(headers, r)) for r in rows[1:]]
    body = [r for r in body if (r.get("SIS User ID") or "").strip()]
    return cols, body


def _same(a: str, b: str) -> bool:
    if a == b:
        return True
    try:
        return abs(float(a) - float(b)) < 1e-6
    except ValueError:
        return a.strip().upper() == b.strip().upper()


def plan_push(gb: Gradebook, cols: dict[int, str], rows: list[dict],
              only: list[str] | None) -> tuple[list[Change], list[str]]:
    """Diff an import file against live Canvas. Returns (changes, warnings)."""
    live_ids = {a["id"]: a for a in gb.assignments}
    warnings = []
    unknown = [cols[i] for i in cols if i not in live_ids]
    if unknown:
        raise CanvasCmdError(
            "the file names assignments this course does not have (wrong section's file?): "
            + "; ".join(unknown))
    wanted = set(cols)
    if only:
        keys = {o.lower() for o in only}
        wanted = {i for i in cols
                  if str(i) in keys or live_ids[i]["name"].lower() in keys}
        if not wanted:
            raise CanvasCmdError(f"--only matched no assignment column: {', '.join(only)}")
    by_sis = {pad_student_id(s["user"].get("sis_user_id") or ""): s
              for s in gb.students if s["user"].get("sis_user_id")}
    changes = []
    for r in rows:
        sis = pad_student_id(r["SIS User ID"].strip())
        st = by_sis.get(sis)
        if st is None:
            warnings.append(f"{sis} {r.get('Student', '')}: not enrolled in this course; skipped")
            continue
        uid = st["user"]["id"]
        for aid in sorted(wanted):
            new = (r.get(cols[aid]) or "").strip()
            if new == "":
                continue  # a blank cell never clears a grade
            s = gb.scores.get((uid, aid)) or {}
            old = "EX" if s.get("excused") else _num(s.get("score"))
            if new.upper() != "EX":
                try:
                    float(new)
                except ValueError:
                    warnings.append(f"{sis} {cols[aid]}: {new!r} is not a score; skipped")
                    continue
            if _same(old, new):
                continue
            pts = live_ids[aid].get("points_possible")
            if new.upper() != "EX" and pts and float(new) > float(pts):
                warnings.append(f"{sis} {live_ids[aid]['name']}: {new} exceeds {pts} points "
                                "(extra credit?)")
            changes.append(Change(uid, sis, st["user"].get("sortable_name", ""), aid,
                                  live_ids[aid]["name"], old, new))
    return changes, warnings


def apply_push(client: CanvasClient, course_id: int, changes: list[Change]) -> None:
    by_assignment: dict[int, dict] = {}
    for c in changes:
        cell = {"excuse": True} if c.new.upper() == "EX" else {"posted_grade": c.new}
        by_assignment.setdefault(c.assignment_id, {})[str(c.user_id)] = cell
    for aid, grade_data in by_assignment.items():
        prog = client.post(f"courses/{course_id}/assignments/{aid}/submissions/update_grades",
                           {"grade_data": grade_data})
        client.wait_progress(prog)


def cmd_grades_push(client: CanvasClient, args) -> int:
    targets = resolve_targets(args)
    if len(targets) != 1:
        raise CanvasCmdError("grades-push acts on one section at a time; pass --section")
    t = targets[0]
    path = expand_path(args.file, t, args.term)
    cols, rows = parse_import_csv(path)
    gb = read_gradebook(client, t.course_id)
    changes, warnings = plan_push(gb, cols, rows, args.only)
    for w in warnings:
        print(f"  WARNING  {w}")
    print(f"{t.label} (course {t.course_id}): {len(changes)} changed cell(s) from {path.name}")
    for c in changes:
        print(f"  {c.sis}  {c.name:<28}  {c.assignment:<36}  {c.old or '—':>7} → {c.new}")
    if not changes:
        return 0
    if not args.apply:
        print("dry run: nothing written. Re-run with --apply to post these grades.")
        return 0
    apply_push(client, t.course_id, changes)
    print(f"posted {len(changes)} grade(s)")
    return 0


# ── content: announcements, discussions, assignments, syllabus ──────────────


def render_body(path: Path) -> tuple[str | None, str]:
    """Read a content file → (title from a leading H1, HTML body).

    Markdown goes through pandoc (already a lectern dependency for syllabi);
    ``.html`` is sent as-is.
    """
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() in (".html", ".htm"):
        return None, text
    title = None
    m = re.match(r"\A\s*#\s+(.+?)\s*\n", text)
    if m:
        title, text = m.group(1).strip(), text[m.end():]
    try:
        proc = subprocess.run(["pandoc", "-f", "gfm", "-t", "html", "--wrap=none"],
                              input=text, capture_output=True, text=True, check=True)
    except FileNotFoundError:
        raise CanvasCmdError("pandoc is needed to convert Markdown; install it or pass .html") from None
    except subprocess.CalledProcessError as e:
        raise CanvasCmdError(f"pandoc failed on {path}: {e.stderr.strip()}") from None
    return title, proc.stdout


def existing_titles(client: CanvasClient, course_id: int, announcements: bool) -> set[str]:
    params = [("only_announcements", "true")] if announcements else []
    return {d.get("title", "") for d in client.get_all(f"courses/{course_id}/discussion_topics", params)}


def _preview(html: str, n: int = 160) -> str:
    plain = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()
    return plain[:n] + ("…" if len(plain) > n else "")


def _topic(client: CanvasClient, args, *, announcement: bool) -> int:
    kind = "announcement" if announcement else "discussion"
    for t in resolve_targets(args):
        path = expand_path(args.file, t, args.term)
        h1, html = render_body(path)
        title = args.title or h1
        if not title:
            raise CanvasCmdError(f"{path}: no '# Title' line; pass --title")
        print(f"{t.label} (course {t.course_id}): {kind} {title!r} from {path.name}")
        print(f"  {_preview(html)}")
        if title in existing_titles(client, t.course_id, announcement) and not args.force:
            print(f"  already exists with that title; skipped (--force posts a second copy)")
            continue
        data = {"title": title, "message": html}
        if announcement:
            data["is_announcement"] = True
        else:
            data["published"] = bool(args.publish)
            data["discussion_type"] = "threaded"
        if args.delay_until:
            data["delayed_post_at"] = args.delay_until
        if not args.apply:
            when = f"at {args.delay_until}" if args.delay_until else "immediately"
            vis = ("visible to students " + when) if (announcement or args.publish) else "unpublished"
            print(f"  dry run: would create it, {vis}. Re-run with --apply.")
            continue
        made = client.post(f"courses/{t.course_id}/discussion_topics", data)
        print(f"  created {made.get('html_url', made.get('id'))}")
    return 0


def cmd_announce(client: CanvasClient, args) -> int:
    return _topic(client, args, announcement=True)


def cmd_discussion(client: CanvasClient, args) -> int:
    return _topic(client, args, announcement=False)


def _group_id(client: CanvasClient, course_id: int, name: str | None) -> int | None:
    if not name:
        return None
    groups = list(client.get_all(f"courses/{course_id}/assignment_groups"))
    for g in groups:
        if g.get("name", "").lower() == name.lower():
            return g["id"]
    raise CanvasCmdError(f"course {course_id} has no assignment group {name!r}; it has: "
                         + ", ".join(g.get("name", "") for g in groups))


def cmd_assignment(client: CanvasClient, args) -> int:
    name, points = args.name, args.points
    if args.lab is not None:
        if not (args.course and args.vault_root):
            raise CanvasCmdError("--lab needs --course and --vault-root")
        from lectern.c50 import find_lab
        lab = find_lab(Path(args.vault_root), args.course, args.lab)
        name = name or lab.canvas_column or lab.title
        points = points if points is not None else lab.points
    if not name:
        raise CanvasCmdError("pass --name or --lab")
    for t in resolve_targets(args):
        html = render_body(expand_path(args.description, t, args.term))[1] if args.description else ""
        existing = {a.get("name") for a in client.get_all(f"courses/{t.course_id}/assignments")}
        print(f"{t.label} (course {t.course_id}): assignment {name!r}, "
              f"{points if points is not None else '?'} pts, due {args.due or 'none'}, "
              f"group {args.group or 'default'}")
        if name in existing and not args.force:
            print("  already exists with that name; skipped (--force creates a second one)")
            continue
        body = {"name": name, "submission_types": args.submission_types.split(","),
                "published": bool(args.publish), "description": html}
        if points is not None:
            body["points_possible"] = points
        if args.due:
            body["due_at"] = args.due
        gid = _group_id(client, t.course_id, args.group)
        if gid:
            body["assignment_group_id"] = gid
        if not args.apply:
            print(f"  dry run: would create it {'published' if args.publish else 'unpublished'}. "
                  "Re-run with --apply.")
            continue
        made = client.post(f"courses/{t.course_id}/assignments", {"assignment": body})
        print(f"  created {made.get('html_url', made.get('id'))} "
              f"(gradebook column: {assignment_header(made)})")
    return 0


def cmd_syllabus(client: CanvasClient, args) -> int:
    for t in resolve_targets(args):
        path = expand_path(args.file, t, args.term)
        html = path.read_text(encoding="utf-8")
        serial = None
        if t.class_note and t.class_note.exists():
            fm, _ = split_frontmatter(t.class_note.read_text(encoding="utf-8"))
            serial = (fm.get("syllabus") or {}).get("serial")
            distributed = (fm.get("syllabus") or {}).get("distributed")
        else:
            distributed = None
        if serial and str(serial) not in html:
            raise CanvasCmdError(f"{t.label}: {path.name} does not carry serial {serial} from "
                                 "the class note; refusing to post an unstamped syllabus")
        if not serial and not args.allow_unstamped:
            raise CanvasCmdError(f"{t.label}: no syllabus.serial to check against "
                                 "(--allow-unstamped overrides)")
        live = (client.get(f"courses/{t.course_id}", [("include[]", "syllabus_body")])
                or {}).get("syllabus_body") or ""
        same_serial = bool(serial) and str(serial) in live
        print(f"{t.label} (course {t.course_id}): syllabus from {path.name}, serial {serial or '—'}; "
              f"live page {'already carries it' if same_serial else 'differs'}")
        if distributed and not same_serial:
            print(f"  NOTE  distributed {distributed}: a changed syllabus needs a revision-of row")
        if not args.apply:
            print("  dry run: nothing written. Re-run with --apply.")
            continue
        client.put(f"courses/{t.course_id}", {"course": {"syllabus_body": html}})
        print("  syllabus updated")
    return 0


# ── CLI ──────────────────────────────────────────────────────────────────────


def cmd_audit(client: CanvasClient, args) -> int:
    return canvas_grading.cmd_audit(client, args, resolve_targets(args))


def cmd_discussions(client: CanvasClient, args) -> int:
    targets = resolve_targets(args) if args.action == "review" else []
    return canvas_grading.cmd_discussions(client, args, targets)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="reg-canvas",
        description="Canvas API commands. Reads are immediate; writes are dry runs until --apply.")
    sub = p.add_subparsers(dest="cmd", required=True)

    def target(sp, *, need_section=False):
        sp.add_argument("--term", help="term code, e.g. fa26")
        sp.add_argument("--vault-root")
        sp.add_argument("--course", help='e.g. "CECS 326" (default: every course)')
        sp.add_argument("--section", help="e.g. 01" + (" (required)" if need_section else ""))
        sp.add_argument("--course-id", type=int, help="act on this Canvas course id directly "
                        "(the sandbox), bypassing the vault")

    def writes(sp):
        sp.add_argument("--apply", action="store_true", help="actually write to Canvas")

    sp = sub.add_parser("whoami", help="check the token")
    sp.set_defaults(func=cmd_whoami)

    sp = sub.add_parser("courses", help="list your Canvas courses; --bind records ids")
    target(sp)
    sp.add_argument("--bind", action="store_true",
                    help="write canvas.course-id into each section's class note")
    sp.add_argument("--dry-run", action="store_true")
    sp.set_defaults(func=cmd_courses)

    sp = sub.add_parser("grades-export", help="gradebook → Canvas-export CSV")
    target(sp)
    sp.add_argument("--out", help="file or directory ({section}/{term}/{course} expand); "
                    "default <class>/archives/<term>-<sec>/canvas/")
    sp.add_argument("--stdout", action="store_true")
    sp.add_argument("--include-inactive", action="store_true",
                    help="also export inactive and concluded enrolments")
    sp.add_argument("--import", dest="do_import", action="store_true",
                    help="then run reg-lms-grades-import into the archive's grades.csv")
    sp.add_argument("--exclude-sis", nargs="+", default=[], metavar="SIS_ID",
                    help="with --import: course staff enrolled as students (filtered as 'staff')")
    sp.set_defaults(func=cmd_grades_export)

    sp = sub.add_parser("roster-check", help="diff Canvas enrolments against a roster CSV")
    target(sp)
    sp.add_argument("--roster", required=True,
                    help="reg-lms-roster-import CSV ({section}/{term}/{course} expand)")
    sp.set_defaults(func=cmd_roster_check)

    sp = sub.add_parser("audit", help="find ungraded/unposted work and skewed settings")
    target(sp)
    sp.add_argument("--exclude-sis", nargs="+", default=[], metavar="SIS[@SEC]",
                    help="course staff enrolled as students; @326-03 limits to one section")
    sp.set_defaults(func=cmd_audit)

    sp = sub.add_parser("grades-push", help="apply a Canvas-format import CSV (changed cells)")
    target(sp, need_section=True)
    sp.add_argument("--file", required=True,
                    help="e.g. reg-gradebook export-canvas --template output")
    sp.add_argument("--only", nargs="+", help="assignment titles or ids to push")
    writes(sp)
    sp.set_defaults(func=cmd_grades_push)

    for name, helptext in (("announce", "post an announcement"),
                           ("discussion", "create a discussion topic")):
        sp = sub.add_parser(name, help=helptext)
        target(sp)
        sp.add_argument("--file", required=True, help=".md (via pandoc) or .html; "
                        "{section}/{term}/{course} expand")
        sp.add_argument("--title", help="default: the file's leading '# ' heading")
        sp.add_argument("--delay-until", help="ISO time to post at instead of now")
        sp.add_argument("--force", action="store_true", help="post even if the title exists")
        if name == "discussion":
            sp.add_argument("--publish", action="store_true", help="publish (default unpublished)")
        writes(sp)
        sp.set_defaults(func=cmd_announce if name == "announce" else cmd_discussion)

    sp = sub.add_parser("assignment", help="create an assignment")
    target(sp)
    sp.add_argument("--lab", type=int, help="fill name and points from the vault lab index")
    sp.add_argument("--name")
    sp.add_argument("--points", type=float)
    sp.add_argument("--due", help="ISO due timestamp")
    sp.add_argument("--group", help="assignment group name, e.g. 'Assignments and Labs'")
    sp.add_argument("--description", help=".md or .html ({section}/{term}/{course} expand)")
    sp.add_argument("--submission-types", default="none",
                    help="comma list; default none (labs are submitted on GitHub)")
    sp.add_argument("--publish", action="store_true", help="publish (default unpublished)")
    sp.add_argument("--force", action="store_true", help="create even if the name exists")
    writes(sp)
    sp.set_defaults(func=cmd_assignment)

    sp = sub.add_parser("discussions", help="grade discussion assignments by post count")
    act = sp.add_subparsers(dest="action", required=True)
    r = act.add_parser("review", help="write the short list to judge (reads only)")
    target(r)
    r.add_argument("--week", action="append", required=True,
                   help='assignment name prefix, e.g. "Week 5" (repeatable)')
    r.add_argument("--workdir", required=True, help="private working dir (mode 700); "
                   "holds student records, delete after apply")
    r.add_argument("--exclude-sis", nargs="+", default=[], metavar="SIS[@SEC]",
                   help="staff enrolled as students; not graded")
    r.add_argument("--full-credit-sis", nargs="+", default=[], metavar="SIS[@SEC]",
                   help="full credit whatever the count (an agreed arrangement)")
    r.add_argument("--note", help="vault note to write (default with --term/--vault-root: "
                   "classes/semesters/<term>-discussions-<weeks>-grading.md)")
    r.add_argument("--no-note", action="store_true", help="write no vault note")
    r.add_argument("--force", action="store_true", help="overwrite an existing note")
    r.set_defaults(func=cmd_discussions)
    ap_ = act.add_parser("apply", help="set scores and likes from the review")
    ap_.add_argument("--workdir", required=True)
    ap_.add_argument("--note", help="read the ticked deny boxes from this note")
    ap_.add_argument("--post", action="store_true",
                     help="also post the grades (shows students every hidden grade)")
    writes(ap_)
    ap_.set_defaults(func=cmd_discussions)

    sp = sub.add_parser("syllabus", help="set the course syllabus page")
    target(sp)
    sp.add_argument("--file", required=True,
                    help="syllabus_canvas.html ({section}/{term}/{course} expand)")
    sp.add_argument("--allow-unstamped", action="store_true")
    writes(sp)
    sp.set_defaults(func=cmd_syllabus)
    return p


def main(argv=None, client: CanvasClient | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        client = client or CanvasClient.from_config()
        return args.func(client, args)
    except (CanvasError, CanvasCmdError, C50Error, TermSpecError,
            canvas_grading.GradingError) as e:
        print(f"reg-canvas: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
