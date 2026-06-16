"""``reg-term-create`` — scaffold a term from a term-spec.

Idempotently materializes, from ``classes/semesters/<term>.spec.yaml``:
  1. the semester note ``classes/semesters/<term>.md``;
  2. one class note per section ``classes/<dir>/<num>-<sec>-<term>.md``;
  3. one manifest skeleton per section under ``archives/<term>-<sec>/``;
  4. MOC wiring (append a section link under "Sections taught" if the MOC exists).

Existing files are skipped (never overwritten). ``--init`` writes a stub spec.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

import yaml

from lectern.manifest_schema import default_manifest
from lectern.term_spec import load_term_spec, stub_spec_text
from lectern.vault_notes import set_frontmatter_fields

MOC_HEADING = "## ☷ Sections taught"


def _now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def _expand(text: str, mapping: dict) -> str:
    """Replace every ``{{key}}`` with ``mapping[key]`` (str)."""
    for k, v in mapping.items():
        text = text.replace("{{" + k + "}}", str(v))
    return text


def _write_new(path: Path, content: str, created: list, skipped: list) -> bool:
    """Write ``content`` to ``path`` only if absent. Returns True if created."""
    if path.exists():
        skipped.append(path)
        print(f"skip {path}")
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    created.append(path)
    print(f"+    {path}")
    return True


def _semester_note(spec: dict, vault: Path, created: list, skipped: list) -> None:
    term = spec["term"]
    tmpl = (vault / "templates" / "semester-note.md").read_text()
    text = _expand(tmpl, {
        "term": term,
        "term-name": spec["term-name"],
        "year": spec["year"],
        "semester-code": spec["semester-code"],
        "datetime": _now_iso(),
    })
    courses = sorted({s["course"] for s in spec["sections"]})
    text = set_frontmatter_fields(text, {
        "start": str(spec["start"]),
        "end": str(spec["end"]),
        "finals-week-start": str(spec["finals-week-start"]),
        "finals-week-end": str(spec["finals-week-end"]),
        "grade-submission-deadline": str(spec["grade-submission-deadline"]),
        "section-count": len(spec["sections"]),
        "courses": courses,
    })
    _write_new(vault / "classes" / "semesters" / f"{term}.md", text, created, skipped)


def _class_note(spec: dict, sec: dict, vault: Path, created: list, skipped: list) -> None:
    term = spec["term"]
    num = sec["course"].split()[-1]
    cdir = sec["course-dir"]
    tmpl = (vault / "templates" / "class-note.md").read_text()
    text = _expand(tmpl, {
        "course": sec["course"],
        "course-num": num,
        "section": sec["section"],
        "term": term,
        "term-name": spec["term-name"],
        "class-number": sec["class-number"],
        "datetime": _now_iso(),
    })
    text = set_frontmatter_fields(text, {
        "headcount.enrolled": sec["enrolled"],
        "schedule.meets": sec["meets"],
        "schedule.room": sec["room"],
        "schedule.final-exam-date": str(sec["final-exam-date"]),
    })
    path = vault / "classes" / cdir / f"{num}-{sec['section']}-{term}.md"
    _write_new(path, text, created, skipped)


def _manifest(spec: dict, sec: dict, vault: Path, created: list, skipped: list) -> None:
    term = spec["term"]
    cdir = sec["course-dir"]
    path = (vault / "classes" / cdir / "archives"
            / f"{term}-{sec['section']}" / "manifest.yaml")
    man = default_manifest(sec["course"], term, str(sec["section"]), spec["instructor"])
    _cn = sec["class-number"]
    man["class_number"] = None if _cn is None else str(_cn)
    man["headcount"]["enrolled"] = sec["enrolled"]
    man["schedule"]["meets"] = sec["meets"]
    man["schedule"]["room"] = sec["room"]
    man["schedule"]["final_exam"] = str(sec["final-exam-date"])
    _write_new(path, yaml.dump(man, sort_keys=False, allow_unicode=True),
               created, skipped)


def _moc_wire(spec: dict, vault: Path) -> None:
    term = spec["term"]
    # Group section links per distinct course-dir's MOC file.
    for sec in spec["sections"]:
        cdir = sec["course-dir"]
        num = sec["course"].split()[-1]
        moc = vault / "notes" / f"MOC-cecs-{cdir}.md"
        if not moc.exists():
            continue  # never create a MOC
        link = (f"- [[{num}-{sec['section']}-{term}|"
                f"{sec['course']} §{sec['section']} — {spec['term-name']}]]")
        text = moc.read_text()
        anchor = f"{num}-{sec['section']}-{term}"
        if anchor in text:
            continue  # idempotent — already wired
        # Insert after the "Sections taught" heading line.
        lines = text.split("\n")
        out = []
        inserted = False
        for ln in lines:
            out.append(ln)
            if not inserted and ln.strip() == MOC_HEADING:
                out.append(link)
                inserted = True
        if not inserted:
            # heading absent — append heading + link at end
            out.append("")
            out.append(MOC_HEADING)
            out.append(link)
        moc.write_text("\n".join(out))
        print(f"moc  {moc} += {anchor}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="reg-term-create")
    ap.add_argument("--term", required=True)
    ap.add_argument("--vault-root", required=True, type=Path)
    ap.add_argument("--init", action="store_true",
                    help="write a stub term-spec and exit")
    args = ap.parse_args(argv)

    vault = args.vault_root
    spec_path = vault / "classes" / "semesters" / f"{args.term}.spec.yaml"

    if args.init:
        if spec_path.exists():
            print(f"refusing to overwrite existing spec: {spec_path}",
                  file=sys.stderr)
            return 1
        spec_path.parent.mkdir(parents=True, exist_ok=True)
        spec_path.write_text(stub_spec_text(args.term))
        print(f"+    {spec_path}")
        return 0

    spec = load_term_spec(spec_path)
    created: list = []
    skipped: list = []

    _semester_note(spec, vault, created, skipped)
    for sec in spec["sections"]:
        _class_note(spec, sec, vault, created, skipped)
        _manifest(spec, sec, vault, created, skipped)
    _moc_wire(spec, vault)

    print(f"\nsummary: {len(created)} created, {len(skipped)} skipped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
