"""Classroom 50 — create classrooms and post labs from the vault's records.

Classroom 50 replaced GitHub Classroom (sunset 2026-08-28). Its ``gh teacher``
CLI is complete but knows nothing about a course: every command wants an org, a
short-name, a slug, a template and a due date typed by hand. The vault already
holds all five, so this module resolves them from the term-spec, the lab-index
notes and the gradebook schema, then drives ``gh teacher``.

Three verbs:

``classroom-add``
    Create one C50 classroom per section of a term (``cecs-326-fa26-01``).

``post``
    Register a lab as an assignment in every section that teaches it, then emit
    the student-facing announcement. This is the verb that "posts a lab".

``status``
    Read back what is actually registered, per section, from the config repo.

The grade of record stays in Canvas and the vault gradebook; C50 is the
distribution surface, exactly as GitHub Classroom was. So ``post`` does not
touch grading configuration beyond registering the template.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import yaml

from lectern.term_spec import TermSpecError, load_term_spec
from lectern.vault_notes import course_dir, split_frontmatter

DEFAULT_ORG = "Giacalone-CECS"
CONFIG_REPO = "classroom50"

# `gh teacher` short-name and assignment-slug shape, quoted from its own help.
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,38}$")


class C50Error(Exception):
    """Raised when the vault's records can't answer what C50 is being asked."""


# ── vault resolution ─────────────────────────────────────────────────────────


@dataclass
class Lab:
    """A lab as the vault describes it, before C50 sees it."""

    number: int
    course: str
    title: str
    slug: str  # lab-slug, the vault directory name
    assignment_slug: str  # the C50 assignment slug
    template: str  # "<owner>/<repo>"
    points: int | None
    canvas_column: str | None
    index_path: Path


def spec_path(vault_root: Path, term: str) -> Path:
    """Locate a term-spec, preferring ``classes/semesters/``."""
    for cand in (
        vault_root / "classes" / "semesters" / f"{term}.spec.yaml",
        vault_root / "classes" / f"{term}.spec.yaml",
    ):
        if cand.exists():
            return cand
    raise C50Error(f"no term-spec for {term} under {vault_root}/classes")


def classroom_name(course: str, term: str, section: str) -> str:
    """Derive the C50 short-name: ``cecs-326-fa26-01``.

    The short-name flows into every student repo name, so it is derived once,
    here, and never typed.
    """
    num = course.split()[-1]
    dept = course.split()[0].lower()
    name = f"{dept}-{num}-{term}-{section}"
    if not SLUG_RE.match(name):
        raise C50Error(f"derived classroom short-name is invalid: {name!r}")
    return name


def derive_assignment_slug(lab_number: int, lab_slug: str) -> str:
    """Derive ``lab-01-threads`` from a lab number and the vault's lab-slug.

    Course-number prefixes (``378-symmetric_cryptography``) are stripped —
    the classroom short-name already carries the course — and underscores
    become hyphens.
    """
    stem = re.sub(r"^\d{3}-", "", lab_slug).replace("_", "-")
    slug = f"lab-{lab_number:02d}-{stem}"
    if not SLUG_RE.match(slug):
        raise C50Error(f"derived assignment slug is invalid: {slug!r}")
    return slug


def _schema_points(vault_root: Path, course: str, lab_number: int) -> tuple[int | None, str | None]:
    """Return ``(points, canvas_title)`` for a lab from the gradebook schema.

    The schema is rewritten each term against the syllabus, so it outranks the
    lab-index note's ``points:`` — which is authored once and drifts.
    """
    cdir = vault_root / "classes" / course_dir(course)
    num = course.split()[-1]
    for cand in (cdir / f"gradebook-schema-{num}.yaml", cdir / "gradebook-schema.yaml"):
        if not cand.exists():
            continue
        schema = yaml.safe_load(cand.read_text()) or {}
        if schema.get("course") not in (None, course):
            continue
        for col in schema.get("columns", []):
            if col.get("short_name") == f"lab{lab_number}":
                return col.get("points"), col.get("canvas_title")
    return None, None


def find_lab(vault_root: Path, course: str, lab_number: int) -> Lab:
    """Find the lab-index note for ``course`` Lab ``lab_number``."""
    labs_dir = vault_root / "classes" / course_dir(course) / "labs"
    if not labs_dir.is_dir():
        raise C50Error(f"no labs directory at {labs_dir}")

    matches: list[tuple[dict, Path]] = []
    for index in sorted(labs_dir.glob("*/index.md")):
        try:
            fm, _ = split_frontmatter(index.read_text())
        except ValueError:
            continue
        if fm.get("type") != "lab-index":
            continue
        if fm.get("course") != course:
            continue
        if fm.get("lab-number") != lab_number:
            continue
        matches.append((fm, index))

    if not matches:
        raise C50Error(
            f"no lab-index note for {course} Lab {lab_number} under {labs_dir} "
            "(check `course:` and `lab-number:` in the note's frontmatter)"
        )
    if len(matches) > 1:
        paths = ", ".join(str(p) for _, p in matches)
        raise C50Error(f"{course} Lab {lab_number} matches more than one note: {paths}")

    fm, index = matches[0]
    template = fm.get("github-template")
    if not template:
        raise C50Error(f"{index}: frontmatter has no `github-template:`")
    if "/" not in template:
        # The notes store a bare repo name plus a URL that carries the owner.
        url = fm.get("github-template-url") or ""
        m = re.search(r"github\.com/([^/]+)/", url)
        if not m:
            raise C50Error(
                f"{index}: `github-template: {template}` has no owner and "
                "`github-template-url:` doesn't supply one"
            )
        template = f"{m.group(1)}/{template}"

    lab_slug = fm.get("lab-slug") or index.parent.name
    points, canvas_title = _schema_points(vault_root, course, lab_number)

    return Lab(
        number=lab_number,
        course=course,
        title=str(fm.get("title") or f"{course} Lab {lab_number}"),
        slug=lab_slug,
        assignment_slug=fm.get("c50-slug") or derive_assignment_slug(lab_number, lab_slug),
        template=template,
        points=points if points is not None else fm.get("points"),
        canvas_column=canvas_title or fm.get("gradebook-column"),
        index_path=index,
    )


def sections_for(spec: dict, course: str | None, section: str | None) -> list[dict]:
    """Filter a term-spec's sections by course and/or section."""
    out = [
        s
        for s in spec["sections"]
        if (course is None or s["course"] == course)
        and (section is None or str(s["section"]) == section)
    ]
    if not out:
        what = " ".join(x for x in (course, f"§{section}" if section else None) if x)
        raise C50Error(f"term-spec has no section matching {what or 'the filter'}")
    return out


# ── gh teacher ───────────────────────────────────────────────────────────────


def _run(cmd: list[str], dry_run: bool) -> tuple[int, str]:
    """Run a ``gh teacher`` command; return ``(returncode, combined output)``."""
    if dry_run:
        print("  would run: " + " ".join(_quote(c) for c in cmd))
        return 0, "DRY-RUN"
    proc = subprocess.run(cmd, capture_output=True, text=True)
    return proc.returncode, (proc.stdout + proc.stderr).strip()


def _quote(s: str) -> str:
    return f'"{s}"' if " " in s else s


def ensure_classroom(
    org: str, short_name: str, display: str, term: str, dry_run: bool
) -> str:
    """Create a classroom if it doesn't exist. Returns 'created' or 'exists'.

    ``gh teacher classroom add`` deliberately fails rather than overwrite an
    existing classroom's state, so an "already exists" failure is the success
    path on a re-run, not an error.
    """
    rc, out = _run(
        [
            "gh", "teacher", "classroom", "add", org, short_name,
            "--name", display, "--term", term,
        ],
        dry_run,
    )
    if rc == 0:
        return "would create" if dry_run else "created"
    if "already exists" in out.lower() or "exists in the repo" in out.lower():
        return "exists"
    raise C50Error(f"classroom add {short_name} failed:\n{out}")


def register_assignment(
    org: str,
    short_name: str,
    lab: Lab,
    due: str | None,
    available_from: str | None,
    submission_mode: str,
    dry_run: bool,
) -> str:
    """Register (or replace) the lab's assignment entry in a classroom."""
    cmd = [
        "gh", "teacher", "assignment", "add", org, short_name, lab.assignment_slug,
        "--name", lab.canvas_column or lab.title,
        "--template", lab.template,
        "--submission-mode", submission_mode,
    ]
    if due:
        cmd += ["--due", due]
    if available_from:
        cmd += ["--available-from", available_from]
    rc, out = _run(cmd, dry_run)
    if rc != 0:
        raise C50Error(f"assignment add {lab.assignment_slug} failed:\n{out}")
    return out


def read_assignments(org: str, short_name: str) -> list[dict]:
    """Read a classroom's registered assignments back from the config repo."""
    path = f"{short_name}/assignments.json"
    proc = subprocess.run(
        ["gh", "api", f"repos/{org}/{CONFIG_REPO}/contents/{path}", "--jq", ".content"],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return []
    import base64

    try:
        blob = base64.b64decode(proc.stdout.strip())
        return json.loads(blob).get("assignments", [])
    except (ValueError, json.JSONDecodeError):
        return []


# ── products ─────────────────────────────────────────────────────────────────


def classroom_url(org: str, short_name: str) -> str:
    return f"https://github.com/{org}/{CONFIG_REPO}/tree/main/{short_name}"


def announcement(
    org: str, short_name: str, lab: Lab, sec: dict, due: str | None
) -> str:
    """Render the Canvas-pasteable announcement for one section."""
    due_line = _human_due(due) if due else "announced in class"
    points = f"{lab.points} points" if lab.points else "see the README"
    heading = lab.canvas_column or lab.title
    return f"""\
# {heading}

**{sec['course']} §{sec['section']}** · due **{due_line}** · {points}

Lab 1 is posted. It is distributed through Classroom 50, so you accept it from
the command line and it creates a private repository for you under our course
organization.

**To accept it:**

```
gh student accept {org} {short_name} {lab.assignment_slug}
```

If you have not used `gh` before, install the GitHub CLI, then run `gh auth
login` and `gh extension install foundation50/gh-student` once. After that the
accept command above is all you need, for this lab and every later one.

Accepting creates `{org}/{short_name}-{lab.assignment_slug}-<your-username>`.
Clone it, do the work there, and commit and push. **Your last push before the
deadline is what gets graded.** Read the repository's `README.md` first: it
carries the task, the deliverable paths, and the grading breakdown.

Bring questions to class or office hours.
"""


def _human_due(due: str) -> str:
    """Render an ISO due timestamp the way a syllabus would say it."""
    try:
        dt = datetime.fromisoformat(due)
    except ValueError:
        return due
    stamp = dt.strftime("%A, %B %-d at %-I:%M %p")
    return re.sub(r"\s+", " ", stamp)


_FRONTMATTER_RE = re.compile(r"\A---\n(.*?\n)---\n", re.S)
_GH_CLASSROOM_RE = re.compile(r"^github-classroom:\n(?:[ \t]+\S.*\n)*", re.M)
_UPDATED_RE = re.compile(r"^updated:.*$", re.M)


def _patch_frontmatter(text: str, short_name: str, url: str, now: str) -> str:
    """Patch the binding into a note's frontmatter **textually**.

    Deliberately not a YAML round-trip. Class notes are hand-authored, and
    dumping the parsed frontmatter back reformats everything it touches:
    ``tags`` collapses from flow to block style, quotes come and go, and
    PyYAML re-emits a parsed timestamp as ``2026-07-08 11:31:22-07:00`` —
    dropping the ``T`` that the vault's ``created:`` fields and Dataview's
    date parsing both rely on. A targeted edit leaves every untouched line
    byte-identical.
    """
    m = _FRONTMATTER_RE.match(text)
    if not m:
        raise C50Error("class note does not begin with a frontmatter fence")
    fm = m.group(1)
    block = f"github-classroom:\n  id: {short_name}\n  url: {url}\n"

    if _GH_CLASSROOM_RE.search(fm):
        fm = _GH_CLASSROOM_RE.sub(lambda _: block, fm, count=1)
    elif re.search(r"^tags:", fm, re.M):
        fm = re.sub(r"^tags:", lambda _: block + "tags:", fm, count=1, flags=re.M)
    else:
        fm = fm + block

    if _UPDATED_RE.search(fm):
        fm = _UPDATED_RE.sub(lambda _: f"updated: {now}", fm, count=1)
    else:
        fm = fm + f"updated: {now}\n"

    return "---\n" + fm + "---\n" + text[m.end():]


def write_back(class_note: Path, org: str, short_name: str, dry_run: bool) -> bool:
    """Record the C50 binding in a class-note's frontmatter.

    Returns True when the note changed. Under Classroom 50 the classroom's
    identity is its short-name, not the numeric id legacy Classroom used.
    """
    if not class_note.exists():
        return False
    text = class_note.read_text()
    fm, _ = split_frontmatter(text)
    url = classroom_url(org, short_name)
    current = fm.get("github-classroom") or {}
    if current.get("id") == short_name and current.get("url") == url:
        return False
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    if not dry_run:
        class_note.write_text(_patch_frontmatter(text, short_name, url, now))
    return True


def class_note_path(vault_root: Path, sec: dict, term: str) -> Path:
    num = sec["course"].split()[-1]
    return (
        vault_root
        / "classes"
        / course_dir(sec["course"])
        / f"{num}-{sec['section']}-{term}.md"
    )


# ── commands ─────────────────────────────────────────────────────────────────


def cmd_classroom_add(args) -> int:
    vault_root = Path(args.vault_root)
    spec = load_term_spec(spec_path(vault_root, args.term))
    secs = sections_for(spec, args.course, args.section)
    term_name = spec.get("term-name", args.term)

    for sec in secs:
        short = classroom_name(sec["course"], args.term, str(sec["section"]))
        display = f"{sec['course']} §{sec['section']} — {term_name}"
        state = ensure_classroom(args.org, short, display, args.term, args.dry_run)
        print(f"{short}: {state}")
        note = class_note_path(vault_root, sec, args.term)
        if write_back(note, args.org, short, args.dry_run):
            print(f"  bound in {note.relative_to(vault_root)}")
    return 0


def cmd_post(args) -> int:
    vault_root = Path(args.vault_root)
    spec = load_term_spec(spec_path(vault_root, args.term))
    secs = sections_for(spec, args.course, args.section)
    lab = find_lab(vault_root, args.course, args.lab)
    term_name = spec.get("term-name", args.term)

    print(lab.title)
    print(f"  template  {lab.template}")
    print(f"  slug      {lab.assignment_slug}")
    print(f"  points    {lab.points if lab.points is not None else '(unknown)'}")
    if lab.canvas_column:
        print(f"  canvas    {lab.canvas_column}")
    print()

    out_dir = Path(args.out) if args.out else lab.index_path.parent / "posted"
    written: list[Path] = []

    for sec in secs:
        short = classroom_name(sec["course"], args.term, str(sec["section"]))
        display = f"{sec['course']} §{sec['section']} — {term_name}"
        state = ensure_classroom(args.org, short, display, args.term, args.dry_run)
        register_assignment(
            args.org, short, lab, args.due, args.available_from,
            args.submission_mode, args.dry_run,
        )
        print(f"{short}: classroom {state}, assignment {lab.assignment_slug} registered")

        note = class_note_path(vault_root, sec, args.term)
        if write_back(note, args.org, short, args.dry_run):
            print(f"  bound in {note.relative_to(vault_root)}")

        text = announcement(args.org, short, lab, sec, args.due)
        if args.stdout_only:
            print()
            print(text)
        elif not args.dry_run:
            out_dir.mkdir(parents=True, exist_ok=True)
            dest = out_dir / f"{args.term}-{sec['section']}-ANNOUNCE.md"
            dest.write_text(text)
            written.append(dest)

    if written:
        print()
        print("Announcements (paste into Canvas):")
        for p in written:
            print(f"  {p}")
    return 0


def cmd_status(args) -> int:
    vault_root = Path(args.vault_root)
    spec = load_term_spec(spec_path(vault_root, args.term))
    secs = sections_for(spec, args.course, args.section)

    for sec in secs:
        short = classroom_name(sec["course"], args.term, str(sec["section"]))
        entries = read_assignments(args.org, short)
        print(f"{short} ({sec['course']} §{sec['section']})")
        if not entries:
            print("  no classroom, or no assignments registered")
            continue
        for a in entries:
            due = a.get("due_meta", {}).get("input") or a.get("due") or "no due date"
            tmpl = a.get("template") or {}
            origin = f"{tmpl.get('owner')}/{tmpl.get('repo')}" if tmpl else "no template"
            print(f"  {a['slug']:<28} due {due}  ← {origin}")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="reg-c50",
        description="Create Classroom 50 classrooms and post labs from the vault.",
    )
    p.add_argument("--org", default=DEFAULT_ORG, help=f"GitHub org (default {DEFAULT_ORG})")
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp):
        sp.add_argument("--term", required=True, help="term code, e.g. fa26")
        sp.add_argument("--vault-root", required=True)
        sp.add_argument("--course", help='e.g. "CECS 326" (default: every course)')
        sp.add_argument("--section", help="e.g. 01 (default: every section)")

    ca = sub.add_parser("classroom-add", help="create a classroom per section")
    common(ca)
    ca.add_argument("--dry-run", action="store_true")
    ca.set_defaults(func=cmd_classroom_add)

    po = sub.add_parser("post", help="register a lab and write its announcement")
    common(po)
    po.add_argument("--lab", type=int, required=True, help="lab number, e.g. 1")
    po.add_argument("--due", help="ISO due timestamp, e.g. 2026-09-24T23:59:00-07:00")
    po.add_argument("--available-from", help="ISO release timestamp (lists the assignment)")
    po.add_argument(
        "--submission-mode",
        default="tag",
        choices=["every-push", "tag"],
        help="when C50's shim grades (default tag — no Actions burn per push)",
    )
    po.add_argument("--out", help="announcement output directory")
    po.add_argument("--stdout-only", action="store_true", help="print announcements only")
    po.add_argument("--dry-run", action="store_true")
    po.set_defaults(func=cmd_post)

    st = sub.add_parser("status", help="read back what is registered")
    common(st)
    st.set_defaults(func=cmd_status)

    args = p.parse_args(argv)
    if args.course is None and getattr(args, "lab", None) is not None:
        p.error("post requires --course")
    try:
        return args.func(args)
    except (C50Error, TermSpecError) as e:
        print(f"reg-c50: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
