"""Per-section archive bundle orchestrator.

Two modes:
  build  — create classes/<course>/archives/<term>-<section>/, run the B-phase
           importers in sequence (roster→grades→github→gradebook→exams→
           lectures→syllabus), emit manifest.yaml + README.md, validate.
  check  — walk an existing bundle, verify every file referenced by manifest.yaml
           exists, recompute exam source serials, recompute grade distribution,
           report drift.

Term-wide rollup: pa-term-archive --term <t> (no --section) iterates every
classes/<course>/archives/<term>-NN/ directory and refreshes each.

Join doctrine (Option A — local join):
  Canvas grades + MyCSULB roster are left-joined on student_id BEFORE the
  schema-aware gradebook step. The bundle's `grades.csv` is the joined form
  (withdrawn-in-roster + missing-in-Canvas → row with letter_grade='W'). The
  `gradebook.csv` (if schema provided) is the schema-weighted view on top.
  Canvas-not-in-roster (post-ISA-filter) is fatal — real student off the
  MyCSULB list.

CLI: pa-term-archive --course CECS_NNN --course-dir <d> --term <t> --section NN
                     --vault-root <p> [...inputs] [--instructor ...]
     pa-term-archive --check --course CECS_NNN --course-dir <d> --term <t> --section NN --vault-root <p>
     pa-term-archive --term <t> --vault-root <p>   # term-wide rollup
"""
from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from lectern.exam_serial import source_serial_from_tex
from lectern.github_bind import (
    bind_from_classroom,
    bind_from_form,
    write_audit_csv,
    write_github_csv,
)
from lectern.gradebook import (
    grade_distribution,
    import_canvas as gradebook_import_canvas,
    load_schema,
    render_view as gradebook_render_view,
)
from lectern.lms_grades import (
    normalize_grades,
    parse_canvas_csv,
    write_filtered_csv,
    write_grades_csv,
    write_points_possible_json,
)
from lectern.lms_roster import (
    normalize_to_roster_csv,
    parse_mycsulb_xls,
    write_roster_csv,
)
from lectern.manifest_schema import (
    ManifestValidationError,
    default_manifest,
    validate_manifest,
)


ARCHIVED_BY = "pa-term-archive v0.1"


# ── config ──────────────────────────────────────────────────────────────────


@dataclass
class ArchiveConfig:
    course: str
    course_dir: str
    term: str
    section: str
    vault_root: Path
    instructor: str = "Anthony Giacalone"

    roster_xls: Path | None = None
    canvas_grades_csv: Path | None = None
    github_form_csv: Path | None = None
    github_classroom_csv: Path | None = None

    syllabus_pdf: Path | None = None
    exam_dirs: list[Path] = field(default_factory=list)
    lecture_dirs: list[Path] = field(default_factory=list)

    schema_path: Path | None = None
    class_number: str | None = None


# ── helpers ─────────────────────────────────────────────────────────────────


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _today() -> str:
    return datetime.now().astimezone().date().isoformat()


def _copy(src: Path, dst: Path) -> None:
    """shutil.copy2 with parent-dir creation."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def _bundle_dir(cfg: ArchiveConfig) -> Path:
    return (
        cfg.vault_root
        / "classes"
        / cfg.course_dir
        / "archives"
        / f"{cfg.term}-{cfg.section}"
    )


# ── ingest steps ────────────────────────────────────────────────────────────


def _ingest_roster(cfg: ArchiveConfig, bundle: Path, manifest: dict) -> None:
    if cfg.roster_xls is None:
        return
    if not cfg.roster_xls.exists():
        sys.exit(f"roster xls not found: {cfg.roster_xls}")

    raw = parse_mycsulb_xls(cfg.roster_xls)
    norm = normalize_to_roster_csv(
        raw,
        course=cfg.course,
        section=cfg.section,
        class_number=cfg.class_number or "",
        term=cfg.term,
    )
    roster_csv = bundle / "roster.csv"
    write_roster_csv(norm, roster_csv)
    # Provenance copy.
    (bundle / "roster.raw.xls").write_bytes(cfg.roster_xls.read_bytes())

    withdrew = sum(1 for r in norm if r.enrollment_status == "withdrawn")
    enrolled_total = len(norm)
    completed = enrolled_total - withdrew

    manifest["roster"] = {
        "source": "csulb-faculty-center",
        "exported": _today(),
        "csv": "roster.csv",
        "rows": enrolled_total,
    }
    manifest["headcount"] = {
        "enrolled": enrolled_total,
        "completed": completed,
        "withdrew": withdrew,
    }


def _ingest_canvas_grades(cfg: ArchiveConfig, bundle: Path, manifest: dict) -> None:
    """Parse + normalize Canvas. Provenance + filtered + points-possible files."""
    if cfg.canvas_grades_csv is None:
        return
    if not cfg.canvas_grades_csv.exists():
        sys.exit(f"canvas grades csv not found: {cfg.canvas_grades_csv}")

    parsed = parse_canvas_csv(cfg.canvas_grades_csv)
    norm = normalize_grades(parsed)

    # Provenance copy.
    (bundle / "grades.raw.csv").write_bytes(cfg.canvas_grades_csv.read_bytes())
    # ISA-filtered sidecar + points-possible JSON live alongside the joined grades.csv.
    write_filtered_csv(norm, bundle / "grades.filtered.csv")
    write_points_possible_json(norm, bundle / "grades.points-possible.json")

    # Stash the un-joined normalized form in a temp file the join step will
    # consume — we don't write it as grades.csv since that slot is the joined
    # output.
    intermediate = bundle / ".grades-canvas-only.csv"
    write_grades_csv(norm, intermediate)

    manifest["grades"] = manifest.get("grades", {}) or {}
    manifest["grades"].update({
        "source": "canvas",
        "exported": _today(),
    })


def _join_roster_and_grades(cfg: ArchiveConfig, bundle: Path, manifest: dict) -> None:
    """Left-join roster.csv with the normalized canvas grades into grades.csv.

    - In roster + in Canvas → standard row (Canvas columns preserved).
    - In roster + NOT in Canvas + withdrawn → row with letter_grade='W'.
    - In roster + NOT in Canvas + enrolled → fatal (data inconsistency).
    - In Canvas + NOT in roster → fatal.
    """
    roster_csv = bundle / "roster.csv"
    intermediate = bundle / ".grades-canvas-only.csv"
    if not roster_csv.exists() or not intermediate.exists():
        # If either is missing, no joined grades.csv is produced; that's fine
        # for minimal bundles.
        return

    with roster_csv.open(newline="", encoding="utf-8") as fh:
        roster_rows = list(csv.DictReader(fh))
    with intermediate.open(newline="", encoding="utf-8") as fh:
        canvas_reader = csv.DictReader(fh)
        canvas_fields = canvas_reader.fieldnames or []
        canvas_rows = list(canvas_reader)

    canvas_by_sid: dict[str, dict] = {}
    for cr in canvas_rows:
        sid = (cr.get("student_id") or "").strip()
        if sid:
            canvas_by_sid[sid] = cr

    roster_sids = {(r.get("student_id") or "").strip() for r in roster_rows}
    extras = sorted(set(canvas_by_sid) - roster_sids)
    if extras:
        names = ", ".join(
            f"{sid} ({canvas_by_sid[sid].get('display_name', '?')})"
            for sid in extras
        )
        sys.exit(
            f"{cfg.canvas_grades_csv}: {len(extras)} student(s) in Canvas "
            f"but not in MyCSULB roster: {names}. Re-export the roster (late "
            "add?) or remove the entries from Canvas."
        )

    # Output schema: roster columns ∪ canvas columns, plus a 'letter_grade'
    # slot used to mark W rows distinctly from Canvas-provided final_grade.
    roster_fields = list(roster_rows[0].keys()) if roster_rows else []
    out_fields: list[str] = []
    for col in roster_fields + canvas_fields + ["letter_grade"]:
        if col not in out_fields:
            out_fields.append(col)

    out_rows: list[dict] = []
    for rrow in roster_rows:
        sid = (rrow.get("student_id") or "").strip()
        roster_status = (rrow.get("enrollment_status") or "enrolled").strip()
        crow = canvas_by_sid.get(sid)

        merged: dict[str, str] = {col: "" for col in out_fields}
        for k, v in rrow.items():
            merged[k] = v if v is not None else ""
        if crow is not None:
            for k, v in crow.items():
                merged[k] = v if v is not None else ""
            # If roster says withdrawn but Canvas has a row, prefer 'W' marker.
            if roster_status == "withdrawn":
                merged["letter_grade"] = "W"
                merged["final_grade"] = "W"
            else:
                merged["letter_grade"] = merged.get("final_grade") or ""
        else:
            # Missing from Canvas.
            if roster_status == "withdrawn":
                merged["letter_grade"] = "W"
                merged["final_grade"] = "W"
            else:
                sys.exit(
                    f"roster student {sid} ({rrow.get('display_name')}) is "
                    f"'{roster_status}' but has no Canvas row. Add them to "
                    "Canvas or update their roster status."
                )
        out_rows.append(merged)

    grades_csv = bundle / "grades.csv"
    with grades_csv.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=out_fields)
        writer.writeheader()
        for r in out_rows:
            writer.writerow(r)

    # Clean up intermediate.
    intermediate.unlink()

    manifest["grades"] = manifest.get("grades", {}) or {}
    manifest["grades"].update({
        "csv": "grades.csv",
        "rows": len(out_rows),
    })


def _resolve_schema_path(cfg: ArchiveConfig) -> Path | None:
    if cfg.schema_path is not None:
        return cfg.schema_path if cfg.schema_path.exists() else None
    candidate = cfg.vault_root / "classes" / cfg.course_dir / "gradebook-schema.yaml"
    return candidate if candidate.exists() else None


def _ingest_gradebook(cfg: ArchiveConfig, bundle: Path, manifest: dict) -> None:
    """Run pa.gradebook.import_canvas on the un-joined canvas grades + roster.

    gradebook.import_canvas does its own join (and its own enforcement of
    'canvas not in roster' — duplicating what _join_roster_and_grades already
    enforced; the second check is idempotent on clean data).
    """
    schema_path = _resolve_schema_path(cfg)
    if schema_path is None:
        return
    # Need the un-joined Canvas form: pa.lms_grades.write_grades_csv output.
    # If grades.csv was produced (joined), regenerate the Canvas-only form
    # in memory from the raw input.
    if cfg.canvas_grades_csv is None or not cfg.canvas_grades_csv.exists():
        return
    canvas_only = bundle / ".grades-canvas-only.csv"
    if not canvas_only.exists():
        parsed = parse_canvas_csv(cfg.canvas_grades_csv)
        norm = normalize_grades(parsed)
        write_grades_csv(norm, canvas_only)
    roster_csv = bundle / "roster.csv"
    if not roster_csv.exists():
        return

    schema = load_schema(schema_path)
    rows = gradebook_import_canvas(canvas_only, roster_csv, schema, bundle)
    gradebook_render_view(
        bundle / "gradebook.csv", schema, bundle,
        section=cfg.section, term=cfg.term,
    )
    if canvas_only.exists():
        canvas_only.unlink()

    dist = grade_distribution(bundle / "gradebook.csv")
    manifest["grades"] = manifest.get("grades", {}) or {}
    manifest["grades"]["distribution"] = dist["distribution"]
    manifest["grades"]["dfw_rate"] = round(dist["dfw_rate"], 4)


def _ingest_github(cfg: ArchiveConfig, bundle: Path, manifest: dict) -> None:
    roster_csv = bundle / "roster.csv"
    if not roster_csv.exists():
        return

    rows = None
    source = None
    raw_src: Path | None = None

    if cfg.github_form_csv is not None and cfg.github_form_csv.exists():
        rows = bind_from_form(cfg.github_form_csv, roster_csv, section=cfg.section)
        source = "form"
        raw_src = cfg.github_form_csv
    elif cfg.github_classroom_csv is not None and cfg.github_classroom_csv.exists():
        rows = bind_from_classroom(cfg.github_classroom_csv, roster_csv)
        source = "classroom"
        raw_src = cfg.github_classroom_csv

    if rows is None:
        return

    github_csv = bundle / "github.csv"
    audit_csv = bundle / "github.audit.csv"
    write_github_csv(rows, github_csv)
    write_audit_csv(rows, audit_csv)
    if raw_src is not None:
        (bundle / "github.raw.csv").write_bytes(raw_src.read_bytes())

    verified = sum(
        1 for r in rows
        if r.verified in ("consistent_dedup", "classroom_oauth", "github_exists")
    )
    missing = sum(1 for r in rows if r.verified == "missing")
    flagged = sum(
        1 for r in rows
        if r.notes
        or r.verified in ("missing", "github_404", "rate_limited")
    )

    manifest["github"] = {
        "source": source,
        "csv": "github.csv",
        "raw": "github.raw.csv" if raw_src is not None else None,
        "audit": "github.audit.csv",
        "rows": len(rows),
        "verified": verified,
        "unverified": len(rows) - verified - missing,
        "missing": missing,
        "flagged": flagged,
        "verified_at": _now_iso(),
    }


def _ingest_exams(cfg: ArchiveConfig, bundle: Path, manifest: dict) -> None:
    if not cfg.exam_dirs:
        return
    exams_dir = bundle / "exams"
    exams_dir.mkdir(parents=True, exist_ok=True)

    by_stem: dict[str, dict[str, Path]] = {}

    for src_dir in cfg.exam_dirs:
        if not src_dir.exists():
            continue
        for entry in sorted(src_dir.iterdir()):
            if not entry.is_file():
                continue
            name = entry.name
            stem = entry.stem
            # Categorize by suffix patterns.
            ext = entry.suffix.lower()
            base_stem = stem
            kind: str | None = None
            if name.endswith("_key.pdf"):
                base_stem = stem[: -len("_key")]
                kind = "key_pdf"
            elif name.endswith("_spec.json"):
                base_stem = stem[: -len("_spec")]
                kind = "spec_json"
            elif name.endswith("_serials.csv"):
                base_stem = stem[: -len("_serials")]
                kind = "serials_csv"
            elif name.endswith("_combined.pdf"):
                base_stem = stem[: -len("_combined")]
                kind = "combined_pdf"
            elif ext == ".tex":
                kind = "tex"
            elif ext == ".pdf":
                kind = "pdf"
            else:
                continue
            slot = by_stem.setdefault(base_stem, {})
            slot[kind] = entry

    notes_lines: list[str] = []
    exams_manifest: list[dict] = []
    for stem in sorted(by_stem):
        slot = by_stem[stem]
        # Copy each file we recognised.
        entry: dict[str, Any] = {"name": stem}
        if "tex" in slot:
            dst = exams_dir / slot["tex"].name
            _copy(slot["tex"], dst)
            entry["tex"] = slot["tex"].name
            try:
                entry["source_serial"] = source_serial_from_tex(
                    dst.read_text(encoding="utf-8")
                )
            except Exception as e:
                notes_lines.append(f"source_serial compute failed for {stem}: {e}")
        if "pdf" in slot:
            _copy(slot["pdf"], exams_dir / slot["pdf"].name)
            entry["pdf"] = slot["pdf"].name
        if "key_pdf" in slot:
            _copy(slot["key_pdf"], exams_dir / slot["key_pdf"].name)
            entry["key_pdf"] = slot["key_pdf"].name
        if "spec_json" in slot:
            _copy(slot["spec_json"], exams_dir / slot["spec_json"].name)
            entry["spec_json"] = slot["spec_json"].name
        else:
            entry["spec_json"] = None
            if "tex" in slot:
                notes_lines.append(
                    f"spec_json missing for {stem}: pre-Su26 generator gap, "
                    "documented at docs/exam-tex-doctrine"
                )
        if "serials_csv" in slot:
            _copy(slot["serials_csv"], exams_dir / slot["serials_csv"].name)
            entry["serials_csv"] = slot["serials_csv"].name
        if "combined_pdf" in slot:
            _copy(slot["combined_pdf"], exams_dir / slot["combined_pdf"].name)
        entry.setdefault("per_student_ids", False)
        exams_manifest.append(entry)

    if exams_manifest:
        manifest["exams"] = exams_manifest
    if notes_lines:
        existing = manifest["audit"].get("notes") or ""
        joined = ("\n".join(notes_lines)) if not existing else (existing + "\n" + "\n".join(notes_lines))
        manifest["audit"]["notes"] = joined


def _ingest_lectures(cfg: ArchiveConfig, bundle: Path, manifest: dict) -> None:
    if not cfg.lecture_dirs:
        return
    lectures_dir = bundle / "lectures"
    lectures_dir.mkdir(parents=True, exist_ok=True)
    entries: list[dict] = []
    for src_dir in cfg.lecture_dirs:
        if not src_dir.exists():
            continue
        for f in sorted(src_dir.iterdir()):
            if f.is_file():
                _copy(f, lectures_dir / f.name)
                entries.append({"file": f.name, "delivered": None})
    if entries:
        manifest["lectures"] = entries


def _ingest_syllabus(cfg: ArchiveConfig, bundle: Path, manifest: dict) -> None:
    if cfg.syllabus_pdf is None or not cfg.syllabus_pdf.exists():
        return
    _copy(cfg.syllabus_pdf, bundle / "syllabus.pdf")
    manifest["syllabus"] = manifest.get("syllabus", {}) or {}
    manifest["syllabus"]["pdf"] = "syllabus.pdf"


# ── orchestration ──────────────────────────────────────────────────────────


def build_bundle(cfg: ArchiveConfig) -> Path:
    """Create or refresh the archive bundle. Returns path to the bundle directory."""
    bundle = _bundle_dir(cfg)
    bundle.mkdir(parents=True, exist_ok=True)

    manifest = default_manifest(cfg.course, cfg.term, cfg.section, cfg.instructor)
    if cfg.class_number:
        manifest["class_number"] = cfg.class_number

    _ingest_roster(cfg, bundle, manifest)
    _ingest_canvas_grades(cfg, bundle, manifest)
    _join_roster_and_grades(cfg, bundle, manifest)
    _ingest_gradebook(cfg, bundle, manifest)
    _ingest_github(cfg, bundle, manifest)
    _ingest_exams(cfg, bundle, manifest)
    _ingest_lectures(cfg, bundle, manifest)
    _ingest_syllabus(cfg, bundle, manifest)

    manifest["audit"]["archived"] = _now_iso()
    manifest["audit"]["archived_by"] = ARCHIVED_BY

    # Validate before declaring success.
    try:
        validate_manifest(manifest)
    except ManifestValidationError as e:
        sys.exit(f"manifest validation failed: {e}")

    (bundle / "manifest.yaml").write_text(
        yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    (bundle / "README.md").write_text(render_readme(manifest, bundle), encoding="utf-8")
    return bundle


# ── README ──────────────────────────────────────────────────────────────────


def render_readme(manifest: dict, bundle_dir: Path) -> str:
    """Render a human-readable README.md from a validated manifest dict."""
    course = manifest["course"]
    term = manifest["term"]
    section = manifest["section"]
    instructor = manifest["instructor"]
    hc = manifest["headcount"]

    lines: list[str] = []
    lines.append(f"# {course} §{section} — {term} archive")
    lines.append("")
    lines.append(f"- **Instructor:** {instructor}")
    if manifest.get("class_number"):
        lines.append(f"- **Class number:** {manifest['class_number']}")
    lines.append(
        f"- **Headcount:** enrolled {hc['enrolled']} · "
        f"completed {hc['completed']} · withdrew {hc['withdrew']}"
    )
    lines.append("")

    syll = manifest.get("syllabus") or {}
    if syll.get("pdf"):
        lines.append(f"## Syllabus\n\n- [{syll['pdf']}]({syll['pdf']})")
        if syll.get("serial"):
            lines.append(f"- Serial: `{syll['serial']}`")
        lines.append("")

    roster = manifest.get("roster") or {}
    grades = manifest.get("grades") or {}
    if roster.get("csv") or grades.get("csv"):
        lines.append("## Roster + grades")
        lines.append("")
        if roster.get("csv"):
            lines.append(f"- Roster: [{roster['csv']}]({roster['csv']}) "
                         f"({roster.get('rows', '?')} rows, "
                         f"exported {roster.get('exported', '?')})")
        if grades.get("csv"):
            lines.append(
                f"- Grades: [{grades['csv']}]({grades['csv']}) "
                f"({grades.get('rows', '?')} rows, source: {grades.get('source', '?')})"
            )
        if grades.get("distribution"):
            dist_str = ", ".join(
                f"{k}: {v}" for k, v in sorted(grades["distribution"].items())
            )
            lines.append(f"- Distribution: {dist_str}")
        if grades.get("dfw_rate") is not None:
            lines.append(f"- DFW rate: {grades['dfw_rate']*100:.1f}%")
        lines.append("")

    gh = manifest.get("github") or {}
    if gh.get("csv"):
        lines.append("## GitHub bindings")
        lines.append("")
        lines.append(
            f"- Source: {gh.get('source', '?')} · {gh.get('rows', '?')} rows · "
            f"{gh.get('verified', 0)} verified · {gh.get('missing', 0)} missing · "
            f"{gh.get('flagged', 0)} flagged"
        )
        lines.append(f"- [{gh['csv']}]({gh['csv']}) — full register")
        if gh.get("audit"):
            lines.append(f"- [{gh['audit']}]({gh['audit']}) — flagged subset for review")
        lines.append("")

    exams = manifest.get("exams") or []
    if exams:
        lines.append("## Exams")
        lines.append("")
        for ex in exams:
            bits = []
            if ex.get("tex"):
                bits.append(f"tex `{ex['tex']}`")
            if ex.get("pdf"):
                bits.append(f"pdf `{ex['pdf']}`")
            if ex.get("source_serial"):
                bits.append(f"serial `{ex['source_serial']}`")
            lines.append(f"- **{ex['name']}** — " + " · ".join(bits) if bits else f"- **{ex['name']}**")
        lines.append("")

    lectures = manifest.get("lectures") or []
    if lectures:
        lines.append("## Lectures")
        lines.append("")
        for lec in lectures:
            lines.append(f"- `{lec['file']}`")
        lines.append("")

    audit = manifest["audit"]
    lines.append("## Audit")
    lines.append("")
    lines.append(f"- Archived: {audit['archived']}")
    lines.append(f"- Archived by: {audit['archived_by']}")
    if audit.get("notes"):
        lines.append("")
        lines.append("### Notes")
        lines.append("")
        for note_line in audit["notes"].split("\n"):
            lines.append(f"- {note_line}")
    lines.append("")
    return "\n".join(lines)


# ── check mode ──────────────────────────────────────────────────────────────


def check_bundle(bundle_dir: Path) -> tuple[int, int, list[str]]:
    """Walk bundle, verify manifest-referenced files exist + serials match.

    Returns (ok_count, fail_count, issues). Each issue is a single human-readable
    line that names the file or item at fault.
    """
    bundle_dir = Path(bundle_dir)
    issues: list[str] = []
    ok = 0
    fail = 0

    manifest_path = bundle_dir / "manifest.yaml"
    if not manifest_path.exists():
        return (0, 1, [f"manifest.yaml missing in {bundle_dir}"])

    try:
        manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        return (0, 1, [f"manifest.yaml unparseable: {e}"])

    try:
        validate_manifest(manifest)
        ok += 1
    except ManifestValidationError as e:
        fail += 1
        issues.append(f"manifest.yaml schema invalid: {e}")

    # Top-level file refs.
    file_refs: list[tuple[str, str]] = []  # (manifest field, relative path)
    for key in ("syllabus.pdf",):
        syll = manifest.get("syllabus") or {}
        if syll.get("pdf"):
            file_refs.append(("syllabus.pdf", syll["pdf"]))
    for sect, fld in (("roster", "csv"), ("grades", "csv"),
                       ("github", "csv"), ("github", "audit"), ("github", "raw")):
        block = manifest.get(sect) or {}
        if block.get(fld):
            file_refs.append((f"{sect}.{fld}", block[fld]))

    for label, rel in file_refs:
        full = bundle_dir / rel
        if full.exists():
            ok += 1
        else:
            fail += 1
            issues.append(f"missing: {rel} (referenced by manifest.{label})")

    # Exams: file existence + source_serial drift.
    for ex in manifest.get("exams") or []:
        for fld in ("tex", "pdf", "key_pdf", "spec_json", "serials_csv"):
            v = ex.get(fld)
            if v:
                full = bundle_dir / "exams" / v
                if full.exists():
                    ok += 1
                else:
                    fail += 1
                    issues.append(f"missing: exams/{v} (exam {ex['name']!r}.{fld})")
        # Source serial drift.
        if ex.get("tex") and ex.get("source_serial"):
            tex_path = bundle_dir / "exams" / ex["tex"]
            if tex_path.exists():
                actual = source_serial_from_tex(tex_path.read_text(encoding="utf-8"))
                if actual != ex["source_serial"]:
                    fail += 1
                    issues.append(
                        f"serial drift: exam {ex['name']!r} manifest "
                        f"{ex['source_serial']} != recomputed {actual}"
                    )
                else:
                    ok += 1

    # Lectures.
    for lec in manifest.get("lectures") or []:
        v = lec.get("file")
        if v:
            full = bundle_dir / "lectures" / v
            if full.exists():
                ok += 1
            else:
                fail += 1
                issues.append(f"missing: lectures/{v}")

    # Grade distribution drift.
    gb = bundle_dir / "gradebook.csv"
    grades = manifest.get("grades") or {}
    if gb.exists() and grades.get("distribution"):
        dist = grade_distribution(gb)
        if dist["distribution"] != grades["distribution"]:
            fail += 1
            issues.append(
                f"grade distribution drift: manifest={grades['distribution']!r} "
                f"recomputed={dist['distribution']!r}"
            )
        else:
            ok += 1

    return ok, fail, issues


# ── CLI ─────────────────────────────────────────────────────────────────────


def _build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="pa-term-archive",
        description="Per-section semester archive bundle orchestrator + check mode.",
    )
    p.add_argument("--check", action="store_true",
                   help="check mode: walk existing bundle and report drift")
    p.add_argument("--course", help="course code, e.g. 'CECS 478'")
    p.add_argument("--course-dir", dest="course_dir",
                   help="vault folder under classes/, e.g. '378-478'")
    p.add_argument("--term", required=True, help="term code, e.g. sp26")
    p.add_argument("--section", help="section number, e.g. '04' (omit for term-wide rollup)")
    p.add_argument("--vault-root", dest="vault_root", type=Path, required=True,
                   help="vault root (parent of classes/)")
    p.add_argument("--instructor", default="Anthony Giacalone")
    p.add_argument("--class-number", dest="class_number")

    p.add_argument("--roster-xls", dest="roster_xls", type=Path)
    p.add_argument("--canvas-csv", dest="canvas_csv", type=Path)
    p.add_argument("--form-csv", dest="form_csv", type=Path)
    p.add_argument("--classroom-csv", dest="classroom_csv", type=Path)
    p.add_argument("--schema", type=Path)
    p.add_argument("--syllabus-pdf", dest="syllabus_pdf", type=Path)
    p.add_argument("--exam-dir", dest="exam_dirs", type=Path, action="append", default=[])
    p.add_argument("--lecture-dir", dest="lecture_dirs", type=Path, action="append", default=[])
    return p


def _cfg_from_args(args) -> ArchiveConfig:
    if not args.course or not args.course_dir or not args.section:
        sys.exit("--course, --course-dir, --section are required (omit --section only for term-wide rollup)")
    return ArchiveConfig(
        course=args.course,
        course_dir=args.course_dir,
        term=args.term,
        section=args.section,
        vault_root=args.vault_root,
        instructor=args.instructor,
        class_number=args.class_number,
        roster_xls=args.roster_xls,
        canvas_grades_csv=args.canvas_csv,
        github_form_csv=args.form_csv,
        github_classroom_csv=args.classroom_csv,
        schema_path=args.schema,
        syllabus_pdf=args.syllabus_pdf,
        exam_dirs=list(args.exam_dirs or []),
        lecture_dirs=list(args.lecture_dirs or []),
    )


def _term_rollup(args) -> int:
    """Iterate every classes/<course>/archives/<term>-NN bundle and refresh."""
    classes = args.vault_root / "classes"
    if not classes.exists():
        print(f"no classes/ under {args.vault_root}", file=sys.stderr)
        return 1
    refreshed = 0
    for course_dir in sorted(classes.iterdir()):
        arch = course_dir / "archives"
        if not arch.exists():
            continue
        for bundle in sorted(arch.iterdir()):
            if not bundle.is_dir() or not bundle.name.startswith(f"{args.term}-"):
                continue
            # In check mode, re-validate; otherwise the orchestrator can't fully
            # rebuild without the raw inputs, so just re-validate either way.
            ok, fail, issues = check_bundle(bundle)
            tag = "OK" if fail == 0 else "FAIL"
            print(f"  [{tag}] {bundle.relative_to(args.vault_root)}  ok={ok} fail={fail}")
            for i in issues:
                print(f"      - {i}")
            refreshed += 1
    print(f"\n{refreshed} bundle(s) inspected for term {args.term}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _build_argparser().parse_args(argv)

    if args.check:
        if not args.section:
            sys.exit("--check requires --section")
        cfg = _cfg_from_args(args)
        bundle = _bundle_dir(cfg)
        if not bundle.exists():
            print(f"bundle not found: {bundle}", file=sys.stderr)
            return 1
        ok, fail, issues = check_bundle(bundle)
        for i in issues:
            print(f"  - {i}")
        mark_ok = "✓"
        mark_fail = "✗"
        print(f"{mark_ok} {ok}  {mark_fail} {fail}")
        return 1 if fail else 0

    if not args.section:
        return _term_rollup(args)

    cfg = _cfg_from_args(args)
    bundle = build_bundle(cfg)
    print(f"→ {bundle}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
