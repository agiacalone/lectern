"""Gradebook analysis layer over Canvas exports.

Pulls together:
  - normalized Canvas grades.csv (from pa.lms_grades)
  - normalized roster.csv (from pa.lms_roster)
  - per-course gradebook-schema.yaml (canvas-title → short-name + group + weight)

Produces:
  - gradebook.csv (canonical row-per-student with weighted_score + letter_grade)
  - gradebook.md (DataviewJS view for the vault)
  - DFW rollups across sections of a term

CLI: pa-gradebook {import,dfw,dist,check} ...
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import dataclass, field, fields, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from lectern.student_id import pad_student_id


# ── schema ──────────────────────────────────────────────────────────────────


@dataclass
class GradebookSchema:
    course: str
    term_default: str
    columns: list[dict]        # canvas_title, short_name, title, points, group
    weights: dict[str, float]  # group → weight (must sum to ~1.0)
    letter_cuts: dict[str, int]
    flags: list[str]


def load_schema(path: Path) -> GradebookSchema:
    """Read YAML schema. Validates weights sum to ~1.0 (tolerance 0.001).
    Validates letter_cuts has A and F entries."""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        sys.exit(f"{path}: schema root must be a mapping")

    weights = data.get("weights") or {}
    if not isinstance(weights, dict):
        sys.exit(f"{path}: weights must be a mapping")
    total = sum(float(v) for v in weights.values())
    if abs(total - 1.0) > 0.001:
        sys.exit(
            f"{path}: weights must sum to 1.0 (got {total:.4f}); "
            "fix the schema so groups partition 100% of the grade."
        )

    letter_cuts = data.get("letter_cuts") or {}
    if not isinstance(letter_cuts, dict):
        sys.exit(f"{path}: letter_cuts must be a mapping")
    if "A" not in letter_cuts or "F" not in letter_cuts:
        sys.exit(f"{path}: letter_cuts must include at least 'A' and 'F'")

    return GradebookSchema(
        course=str(data.get("course") or ""),
        term_default=str(data.get("term_default") or ""),
        columns=list(data.get("columns") or []),
        weights={k: float(v) for k, v in weights.items()},
        letter_cuts={k: int(v) for k, v in letter_cuts.items()},
        flags=list(data.get("flags") or []),
    )


# ── computation ────────────────────────────────────────────────────────────


def compute_weighted(
    raw_scores: dict[str, float],
    schema: GradebookSchema,
    *,
    graded_only: bool = False,
    graded_cols: set[str] | None = None,
) -> float:
    """raw_scores: {short_name: float}. Returns weighted percentage 0-100.

    Default (graded_only=False): per group, group_pct = sum(earned) /
    sum(max) * 100; weighted = sum(weights[group] * group_pct); missing
    assignments count as 0 earned with max still counting. (Legacy import path.)

    graded_only=True: restrict earned/max to columns in `graded_cols`, drop
    groups with no graded column, and RENORMALIZE the remaining group weights to
    sum to 1.0. This yields an in-progress "current standing" that does not zero
    ungraded work, and converges to the full-schema number once every column is
    graded.
    """
    gc = graded_cols or set()
    # Bucket columns by group, summing earned + max points.
    by_group: dict[str, dict[str, float]] = {}
    for col in schema.columns:
        short = col.get("short_name") or ""
        if graded_only and short not in gc:
            continue
        group = col.get("group") or ""
        try:
            max_pts = float(col.get("points") or 0)
        except (TypeError, ValueError):
            max_pts = 0.0
        earned = float(raw_scores.get(short, 0) or 0)
        bucket = by_group.setdefault(group, {"earned": 0.0, "max": 0.0})
        bucket["earned"] += earned
        bucket["max"] += max_pts

    # Renormalize over groups that have at least one graded column (graded_only).
    graded_groups = {
        g: w for g, w in schema.weights.items()
        if by_group.get(g, {}).get("max", 0.0) > 0
    }
    denom = sum(graded_groups.values()) if graded_only else 1.0
    if denom <= 0:
        return 0.0

    total = 0.0
    for group, weight in schema.weights.items():
        bucket = by_group.get(group, {"earned": 0.0, "max": 0.0})
        if bucket["max"] <= 0:
            # Group has no columns or all-zero max → contributes 0
            continue
        pct = (bucket["earned"] / bucket["max"]) * 100.0
        total += (float(weight) / denom) * pct

    return round(total, 2)


def apply_letter_cuts(weighted: float, schema: GradebookSchema) -> str:
    """Apply schema.letter_cuts. Returns highest-letter where weighted >= cut.

    Iterates cuts sorted descending by threshold. Defaults to the lowest-letter
    (smallest cut value) if nothing matches — typically 'F'.
    """
    # Sort cuts: highest threshold first.
    ranked = sorted(schema.letter_cuts.items(), key=lambda kv: -kv[1])
    for letter, cut in ranked:
        if weighted >= cut:
            return letter
    # Fallback: letter with smallest cut value.
    return ranked[-1][0] if ranked else "F"


def dfw_rate(grades: list[dict]) -> float:
    """grades: list of dicts each carrying 'letter_grade'.
    DFW = (count of D/F/W letters) / total. Returns 0.0 for empty list."""
    if not grades:
        return 0.0
    dfw = sum(1 for g in grades if (g.get("letter_grade") or "") in ("D", "F", "W"))
    return dfw / len(grades)


# ── gradebook row + canvas import ──────────────────────────────────────────


@dataclass
class GradebookRow:
    student_id: str
    display_name: str
    raw_scores: str            # JSON blob from grades.csv (Canvas titles as keys)
    short_scores: str          # JSON blob keyed by schema short_names
    weighted_score: float      # schema-computed (analytical; should ≈ canvas_final_score)
    canvas_final_score: str    # from grades.csv (Canvas's auto-computed Final Score)
    canvas_final_grade: str    # from grades.csv (Canvas's auto-computed Final Grade letter)
    override_score: str        # instructor's manual Override Score from Canvas (when set)
    override_grade: str        # instructor's manual Override Grade letter from Canvas (when set)
    letter_grade: str          # truth-of-record: override → canvas_final → schema-derived
    grade_source: str          # 'override' | 'canvas' | 'schema' | 'withdrawn'
    enrollment_status: str     # joined from roster.csv: 'enrolled' | 'withdrawn'
    flags: str                 # comma-separated subset of schema.flags


def _title_to_short(schema: GradebookSchema) -> dict[str, str]:
    """Map canvas_title (suffix-stripped) → short_name."""
    return {col["canvas_title"]: col["short_name"] for col in schema.columns}


def _parse_score(v: Any) -> float:
    """Coerce a Canvas score cell to float; empty / non-numeric → 0.0."""
    if v is None:
        return 0.0
    s = str(v).strip()
    if not s:
        return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


def import_canvas(
    canvas_csv: Path,
    roster_csv: Path,
    schema: GradebookSchema,
    out: Path,
) -> list[GradebookRow]:
    """Pull Canvas grades + roster + schema → emit gradebook.csv at `out`.

    Join semantics (per Part 5 §Two-LMS join):
      - In roster + in Canvas → standard row, scored.
      - In roster + NOT in Canvas + enrollment_status=withdrawn → row with
        letter_grade='W', empty scores, enrollment_status='withdrawn'.
      - In Canvas + NOT in roster → fatal: real student not on the MyCSULB list.
    """
    out.parent.mkdir(parents=True, exist_ok=True)

    # Load grades by student_id. Defensive zero-pad — without it, a Canvas
    # CSV that was opened in Excel (Sheets, Numbers) and re-saved will have
    # 8-digit sids that don't join against the roster's 9-digit canonical IDs,
    # producing a false "Canvas has students not in roster" fatal.
    grades_by_sid: dict[str, dict] = {}
    with canvas_csv.open("r", newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            sid = pad_student_id(row.get("student_id") or "")
            if not sid or sid == "000000000":
                continue
            grades_by_sid[sid] = row

    # Load roster by student_id.
    roster_by_sid: dict[str, dict] = {}
    with roster_csv.open("r", newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            sid = pad_student_id(row.get("student_id") or "")
            if not sid or sid == "000000000":
                continue
            roster_by_sid[sid] = row

    # Canvas students not in roster → fatal.
    extras = sorted(set(grades_by_sid) - set(roster_by_sid))
    if extras:
        names = ", ".join(
            f"{sid} ({grades_by_sid[sid].get('display_name', '?')})"
            for sid in extras
        )
        sys.exit(
            f"{canvas_csv}: {len(extras)} student(s) in Canvas but not in roster: {names}. "
            "Either re-export the MyCSULB roster (student may have added late) "
            "or remove them from Canvas before re-running."
        )

    title_to_short = _title_to_short(schema)
    rows: list[GradebookRow] = []

    for sid, rrow in roster_by_sid.items():
        grow = grades_by_sid.get(sid)
        roster_status = (rrow.get("enrollment_status") or "enrolled").strip()
        display = (rrow.get("display_name") or "").strip()

        if grow is None:
            # In roster, not in Canvas. If withdrawn, emit a W row; otherwise fatal.
            if roster_status == "withdrawn":
                rows.append(GradebookRow(
                    student_id=sid,
                    display_name=display,
                    raw_scores="{}",
                    short_scores="{}",
                    weighted_score=0.0,
                    canvas_final_score="",
                    canvas_final_grade="",
                    override_score="",
                    override_grade="",
                    letter_grade="W",
                    grade_source="withdrawn",
                    enrollment_status="withdrawn",
                    flags="withdrew" if "withdrew" in schema.flags else "",
                ))
                continue
            sys.exit(
                f"{roster_csv}: student {sid} ({display}) is in roster as "
                f"'{roster_status}' but has no Canvas row. Add them to Canvas "
                "or update their roster status."
            )

        # Standard path: parse assignment_scores, map to short_names.
        raw_blob = grow.get("assignment_scores") or "{}"
        try:
            raw_scores = json.loads(raw_blob)
        except json.JSONDecodeError:
            raw_scores = {}

        short_scores: dict[str, float] = {}
        for title, val in raw_scores.items():
            short = title_to_short.get(title)
            if short is None:
                # Title not in schema — skip; harmless.
                continue
            short_scores[short] = _parse_score(val)

        weighted = compute_weighted(short_scores, schema)

        # Truth-of-record letter grade: prefer the instructor's Canvas
        # Override Grade when set (the column that drives MyCSULB submission),
        # else Canvas's auto-computed Final Grade, else schema-derived as a
        # last-resort fallback. Withdrawal trumps everything — a roster-status
        # of 'withdrawn' yields a W regardless of Canvas data.
        canvas_final_grade = (grow.get("final_grade") or "").strip()
        override_score = (grow.get("override_score") or "").strip()
        override_grade = (grow.get("override_grade") or "").strip()

        if roster_status == "withdrawn":
            letter = "W"
            grade_source = "withdrawn"
        elif override_grade:
            letter = override_grade
            grade_source = "override"
        elif canvas_final_grade:
            letter = canvas_final_grade
            grade_source = "canvas"
        else:
            letter = apply_letter_cuts(weighted, schema)
            grade_source = "schema"

        rows.append(GradebookRow(
            student_id=sid,
            display_name=display or (grow.get("display_name") or ""),
            raw_scores=raw_blob,
            short_scores=json.dumps(short_scores, ensure_ascii=False, sort_keys=True),
            weighted_score=weighted,
            canvas_final_score=(grow.get("final_score") or "").strip(),
            canvas_final_grade=canvas_final_grade,
            override_score=override_score,
            override_grade=override_grade,
            letter_grade=letter,
            grade_source=grade_source,
            enrollment_status=roster_status,
            flags="withdrew" if roster_status == "withdrawn" and "withdrew" in schema.flags else "",
        ))

    # Write canonical gradebook.csv
    gradebook_csv = out if out.suffix == ".csv" else (out / "gradebook.csv")
    gradebook_csv.parent.mkdir(parents=True, exist_ok=True)
    field_names = [f.name for f in fields(GradebookRow)]
    with gradebook_csv.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=field_names)
        writer.writeheader()
        for r in rows:
            writer.writerow(asdict(r))

    return rows


# ── markdown view ───────────────────────────────────────────────────────────


_MD_TEMPLATE = """---
type: gradebook
course: "{course}"
term: "{term}"
section: "{section}"
tags: [gradebook, teaching, {course_tag}, term-{term}]
source: gradebook.csv
schema: ../gradebook-schema.yaml
last_imported: {ts}
icon: LiTable
iconColor: var(--text-normal)
---
# {course} §{section} — Gradebook ({term})

> [!info] Source
> Generated by `pa-gradebook import` from Canvas CSV + roster CSV. Read-only view —
> regenerate after each Canvas pull. Hand-edits should be done in Canvas; the
> vault picks them up on next import.

## Summary

```dataviewjs
const csvPath = dv.current().file.folder + "/gradebook.csv";
const text = await app.vault.adapter.read(csvPath);
const lines = text.trim().split("\\n");
const headers = lines[0].split(",");
const rows = lines.slice(1).map(l => {{
  const cells = l.split(",");
  return Object.fromEntries(headers.map((h, i) => [h, cells[i]]));
}});
const n = rows.length;
// Total % (canvas_final_score = raw calculated grade) avg/median, excluding W
const tscores = rows.filter(r => r.letter_grade !== "W" && r.canvas_final_score).map(r => parseFloat(r.canvas_final_score)).filter(x => !isNaN(x));
const avg = tscores.length ? tscores.reduce((a,b)=>a+b,0)/tscores.length : 0;
const ts = [...tscores].sort((a,b)=>a-b);
const median = ts.length ? (ts.length%2 ? ts[(ts.length-1)/2] : (ts[ts.length/2-1]+ts[ts.length/2])/2) : 0;
// Dual distribution: Calculated (Total letter) vs Official (Override-adjusted effective)
const tally = (letterOf) => {{ const d = {{A:0,B:0,C:0,D:0,F:0,W:0}}; rows.forEach(r => {{ const L = ((letterOf(r))||"").trim().charAt(0).toUpperCase(); if (d[L] !== undefined) d[L]++; }}); return d; }};
const calc = tally(r => r.canvas_final_grade || r.letter_grade);
const offi = tally(r => r.letter_grade);
const dfwOf = (d) => n ? (d.D+d.F+d.W)/n*100 : 0;
const fmt = (d) => `A:${{d.A}} B:${{d.B}} C:${{d.C}} D:${{d.D}} F:${{d.F}} W:${{d.W}}`;
dv.paragraph(`**n**: ${{n}} · **Total avg**: ${{avg.toFixed(1)}}% · **median**: ${{median.toFixed(1)}}%`);
dv.table(["View", "Letter distribution", "DFW"], [
  ["Calculated (Total)", fmt(calc), dfwOf(calc).toFixed(1) + "%"],
  ["Official (Override-adjusted)", fmt(offi), dfwOf(offi).toFixed(1) + "%"],
]);
```

## Roster + grades

```dataviewjs
const csvPath = dv.current().file.folder + "/gradebook.csv";
const text = await app.vault.adapter.read(csvPath);
const lines = text.trim().split("\\n");
const headers = lines[0].split(",");
const rows = lines.slice(1).map(l => {{
  const cells = l.split(",");
  return Object.fromEntries(headers.map((h, i) => [h, cells[i]]));
}});
// Unified standing view (vault-native `build` is primary; legacy `import` rows
// also carry weighted_score + letter_grade). in_progress → "B*"; graded_cols/
// total_cols → progress chip. Override detail (import path) folds into Status.
const tbl = rows.map(r => {{
  const inProg = String(r.in_progress) === "true";
  const standing = (r.weighted_score ?? r.canvas_final_score ?? "");
  const letterCell = (r.letter_grade || "") + (inProg ? "*" : "");
  const prog = (r.graded_cols !== undefined && r.total_cols !== undefined)
    ? `${{r.graded_cols}}/${{r.total_cols}}` : "—";
  const status = (r.override_grade
    ? `${{r.enrollment_status}} · ovr ${{r.override_grade}}`
    : r.enrollment_status);
  return [r.display_name, standing, letterCell, prog, status];
}});
dv.table(["Name", "Standing %", "Letter", "Graded", "Status"], tbl);
```

> [!note] Footer
> Source: `gradebook.csv` · Schema: `../gradebook-schema.yaml` · Last import: {ts}
"""


def render_view(gradebook_csv: Path, schema: GradebookSchema, out: Path,
                section: str = "", term: str = "") -> None:
    """Generate gradebook.md alongside gradebook.csv."""
    course = schema.course or ""
    course_tag = course.lower().replace(" ", "-")
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    md_path = out if out.suffix == ".md" else (out / "gradebook.md")
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(_MD_TEMPLATE.format(
        course=course,
        course_tag=course_tag,
        term=term or schema.term_default or "",
        section=section,
        ts=ts,
    ), encoding="utf-8")


# ── DFW rollup ─────────────────────────────────────────────────────────────


def dfw_rollup(term: str, course: str | None = None,
               archives_root: Path | None = None) -> dict:
    """Walk classes/<course>/archives/<term>-<sec>/gradebook.csv across sections.

    Returns {'sections': [{course, section, n, dfw_count, dfw_rate}, ...],
             'by_course': {course: {n, dfw_count, dfw_rate}},
             'overall': {n, dfw_count, dfw_rate}}.
    """
    if archives_root is None:
        sys.exit("dfw_rollup: archives_root is required")

    sections: list[dict] = []
    by_course: dict[str, dict] = {}
    overall_n = 0
    overall_dfw = 0

    course_dirs = []
    if course:
        course_dirs = [archives_root / course]
    else:
        if archives_root.exists():
            course_dirs = [p for p in archives_root.iterdir() if p.is_dir()]

    for cdir in course_dirs:
        arch_dir = cdir / "archives"
        if not arch_dir.exists():
            continue
        for bundle in sorted(arch_dir.iterdir()):
            if not bundle.is_dir():
                continue
            # Bundle name pattern: <term>-<section>
            if not bundle.name.startswith(f"{term}-"):
                continue
            gb = bundle / "gradebook.csv"
            if not gb.exists():
                continue
            section = bundle.name[len(term) + 1:]
            with gb.open("r", newline="", encoding="utf-8") as fh:
                rows = list(csv.DictReader(fh))
            n = len(rows)
            d = sum(1 for r in rows if (r.get("letter_grade") or "") in ("D", "F", "W"))
            rate = (d / n) if n else 0.0
            sections.append({
                "course": cdir.name,
                "section": section,
                "n": n,
                "dfw_count": d,
                "dfw_rate": rate,
            })
            agg = by_course.setdefault(cdir.name, {"n": 0, "dfw_count": 0})
            agg["n"] += n
            agg["dfw_count"] += d
            overall_n += n
            overall_dfw += d

    for c, agg in by_course.items():
        agg["dfw_rate"] = (agg["dfw_count"] / agg["n"]) if agg["n"] else 0.0

    return {
        "sections": sections,
        "by_course": by_course,
        "overall": {
            "n": overall_n,
            "dfw_count": overall_dfw,
            "dfw_rate": (overall_dfw / overall_n) if overall_n else 0.0,
        },
    }


# ── grade distribution ─────────────────────────────────────────────────────


def grade_distribution(gradebook_csv: Path) -> dict:
    """Compute {letter: count} + summary stats for a gradebook.csv."""
    with gradebook_csv.open("r", newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    dist: dict[str, int] = {}
    scores: list[float] = []
    for r in rows:
        letter = (r.get("letter_grade") or "").strip() or "?"
        dist[letter] = dist.get(letter, 0) + 1
        if letter != "W":
            try:
                scores.append(float(r.get("weighted_score") or 0))
            except ValueError:
                pass
    scores_sorted = sorted(scores)
    n = len(scores)
    avg = sum(scores) / n if n else 0.0
    median = 0.0
    if n:
        median = scores_sorted[n // 2] if n % 2 else (scores_sorted[n // 2 - 1] + scores_sorted[n // 2]) / 2
    return {
        "n_total": len(rows),
        "n_scored": n,
        "distribution": dist,
        "avg": round(avg, 2),
        "median": round(median, 2),
        "dfw_rate": dfw_rate([{"letter_grade": (r.get("letter_grade") or "")} for r in rows]),
    }


# ── CLI ─────────────────────────────────────────────────────────────────────


def _default_archives_root() -> Path:
    """Best-effort vault classes root for dfw rollups."""
    candidates = [
        Path.home() / "documents" / "obsidian" / "vault" / "classes",
    ]
    for c in candidates:
        if c.exists():
            return c
    return candidates[0]


def _schema_for_course(course: str) -> Path:
    """Resolve <vault>/classes/<dir>/gradebook-schema.yaml for a course code.

    Prefers a course-specific override (`gradebook-schema-<num>.yaml`) before
    falling back to the shared `gradebook-schema.yaml` in the same folder.
    This lets 378 and 478 — which share the `378-478/` folder but diverge in
    Canvas column layout — each carry their own schema.
    """
    classes = _default_archives_root()
    # Course code "CECS_478" → folder "378-478" or "478", num "478"
    num = course.split("_")[-1] if "_" in course else course.split()[-1]
    candidates = [
        # Per-course overrides in the shared folder (e.g. 378-478/gradebook-schema-378.yaml)
        classes / "378-478" / f"gradebook-schema-{num}.yaml",
        classes / num / f"gradebook-schema-{num}.yaml",
        # Shared / generic schemas as fallback
        classes / "378-478" / "gradebook-schema.yaml",
        classes / num / "gradebook-schema.yaml",
        classes / course / "gradebook-schema.yaml",
    ]
    # Pick first that exists; if none, return the first canonical guess.
    for c in candidates:
        if c.exists():
            return c
    return candidates[0]


def _cmd_import(args: argparse.Namespace) -> int:
    schema_path = args.schema or _schema_for_course(args.course)
    if not schema_path.exists():
        sys.exit(f"schema not found: {schema_path}; pass --schema explicitly")
    schema = load_schema(schema_path)

    out_dir = args.out
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = import_canvas(args.canvas_csv, args.roster_csv, schema, out_dir)
    render_view(out_dir / "gradebook.csv", schema, out_dir,
                section=args.section, term=args.term)

    print(f"→ {out_dir}/gradebook.csv ({len(rows)} rows)")
    print(f"→ {out_dir}/gradebook.md")
    return 0


def _cmd_build(args: argparse.Namespace) -> int:
    from lectern.gradebook_build import build_gradebook
    schema_path = args.schema or _schema_for_course(args.course)
    schema = load_schema(schema_path)
    rows = build_gradebook(
        args.registry, args.roster, schema, args.out,
        section=args.section, term=args.term,
    )
    in_prog = sum(1 for r in rows if r["in_progress"] == "true")
    print(f"→ {args.out}/gradebook.csv ({len(rows)} students, {in_prog} in-progress)")
    return 0


def _cmd_export_canvas(args: argparse.Namespace) -> int:
    from lectern.gradebook_build import export_canvas
    schema_path = args.schema or (_schema_for_course(args.course) if args.course else None)
    if schema_path is None:
        sys.exit("export-canvas needs --schema or --course to resolve the schema")
    schema = load_schema(schema_path)
    export_canvas(args.gradebook, schema, args.out)
    print(f"→ {args.out}")
    return 0


def _cmd_dfw(args: argparse.Namespace) -> int:
    root = args.archives_root or _default_archives_root()
    result = dfw_rollup(args.term, course=args.course, archives_root=root)
    print(f"DFW rollup · term={args.term}"
          + (f" · course={args.course}" if args.course else ""))
    print()
    for s in result["sections"]:
        print(f"  {s['course']:<10} §{s['section']:<3}  "
              f"n={s['n']:>3}  dfw={s['dfw_count']:>2}  "
              f"rate={s['dfw_rate']*100:>5.1f}%")
    if result["by_course"]:
        print()
        for c, agg in sorted(result["by_course"].items()):
            print(f"  {c:<10} TOTAL  n={agg['n']:>3}  dfw={agg['dfw_count']:>2}  "
                  f"rate={agg['dfw_rate']*100:>5.1f}%")
    print()
    o = result["overall"]
    print(f"  OVERALL    n={o['n']:>3}  dfw={o['dfw_count']:>2}  "
          f"rate={o['dfw_rate']*100:>5.1f}%")
    return 0


def _cmd_dist(args: argparse.Namespace) -> int:
    root = args.archives_root or _default_archives_root()
    # course_dir layout: <root>/<course-dir>/archives/<term>-<section>/gradebook.csv
    # course arg may be "CECS_478" → folder is "378-478"
    num = args.course.split("_")[-1] if "_" in args.course else args.course.split()[-1]
    course_dirs = [root / "378-478", root / num, root / args.course]
    csv_path = None
    for cd in course_dirs:
        candidate = cd / "archives" / f"{args.term}-{args.section}" / "gradebook.csv"
        if candidate.exists():
            csv_path = candidate
            break
    if csv_path is None:
        sys.exit(f"no gradebook.csv found for {args.course} {args.term}-{args.section}")
    result = grade_distribution(csv_path)
    print(f"Distribution · {args.course} §{args.section} ({args.term})")
    print(f"  n_total={result['n_total']}  n_scored={result['n_scored']}  "
          f"avg={result['avg']}  median={result['median']}  "
          f"dfw={result['dfw_rate']*100:.1f}%")
    for letter in sorted(result["distribution"].keys()):
        print(f"    {letter}: {result['distribution'][letter]}")
    return 0


def _cmd_check(args: argparse.Namespace) -> int:
    """Validate all gradebook.csv files for the term parse cleanly."""
    root = args.archives_root or _default_archives_root()
    errors = 0
    checked = 0
    for course_dir in sorted(root.iterdir()) if root.exists() else []:
        arch = course_dir / "archives"
        if not arch.exists():
            continue
        for bundle in sorted(arch.iterdir()):
            if not bundle.name.startswith(f"{args.term}-"):
                continue
            gb = bundle / "gradebook.csv"
            if not gb.exists():
                continue
            checked += 1
            try:
                with gb.open("r", newline="", encoding="utf-8") as fh:
                    list(csv.DictReader(fh))
            except Exception as e:
                print(f"  FAIL {gb}: {e}", file=sys.stderr)
                errors += 1
    print(f"checked {checked} gradebooks, {errors} errors")
    return 1 if errors else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="pa-gradebook",
        description="Schema-aware Canvas→vault gradebook + DFW rollup + DataviewJS view.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    pi = sub.add_parser("import", help="import Canvas grades + roster → gradebook.csv + .md")
    pi.add_argument("--course", required=True, help="course code, e.g. CECS_478")
    pi.add_argument("--term", required=True, help="term code, e.g. sp26")
    pi.add_argument("--section", required=True, help="section number, e.g. 04")
    pi.add_argument("--canvas-csv", type=Path, required=True, dest="canvas_csv",
                    help="normalized grades.csv from pa-lms-grades-import")
    pi.add_argument("--roster-csv", type=Path, required=True, dest="roster_csv",
                    help="normalized roster.csv from pa-lms-roster-import")
    pi.add_argument("--out", type=Path, required=True,
                    help="output directory (gradebook.csv + gradebook.md written here)")
    pi.add_argument("--schema", type=Path,
                    help="path to gradebook-schema.yaml (else resolved by --course)")
    pi.set_defaults(func=_cmd_import)

    pb = sub.add_parser("build", help="build gradebook from per-component score files (vault SoT)")
    pb.add_argument("--course", required=True, help="course code, e.g. CECS_378")
    pb.add_argument("--term", required=True)
    pb.add_argument("--section", required=True)
    pb.add_argument("--registry", type=Path, required=True, help="components.yaml")
    pb.add_argument("--roster", type=Path, required=True, help="normalized roster.csv")
    pb.add_argument("--out", type=Path, required=True, help="output directory")
    pb.add_argument("--schema", type=Path, help="schema yaml (else resolved by --course)")
    pb.set_defaults(func=_cmd_build)

    pe = sub.add_parser("export-canvas", help="emit Canvas bulk-upload CSV from gradebook.csv")
    pe.add_argument("--gradebook", type=Path, required=True)
    pe.add_argument("--schema", type=Path, help="schema yaml (else resolved by --course)")
    pe.add_argument("--course", help="course code (used only to resolve --schema)")
    pe.add_argument("--out", type=Path, required=True)
    pe.set_defaults(func=_cmd_export_canvas)

    pd = sub.add_parser("dfw", help="roll up DFW rate across sections of a term")
    pd.add_argument("--term", required=True)
    pd.add_argument("--course", help="filter to one course (e.g. CECS_478)")
    pd.add_argument("--archives-root", type=Path, dest="archives_root")
    pd.set_defaults(func=_cmd_dfw)

    pdist = sub.add_parser("dist", help="grade distribution + summary for one section")
    pdist.add_argument("--course", required=True)
    pdist.add_argument("--term", required=True)
    pdist.add_argument("--section", required=True)
    pdist.add_argument("--archives-root", type=Path, dest="archives_root")
    pdist.set_defaults(func=_cmd_dist)

    pc = sub.add_parser("check", help="verify all gradebooks in a term parse cleanly")
    pc.add_argument("--term", required=True)
    pc.add_argument("--archives-root", type=Path, dest="archives_root")
    pc.set_defaults(func=_cmd_check)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
