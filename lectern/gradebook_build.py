"""Vault-native gradebook: build gradebook.csv from per-component score files.

The vault is the grade source of truth. Each graded artifact (exam, lab) emits a
normalized scores CSV (sid, score, status). A per-section registry
(components.yaml) binds each file to a gradebook-schema column. This module rolls
them up into gradebook.csv (with an in-progress "current standing") and a
Canvas-import CSV — the inverse of the Canvas→vault `import` path.
"""
from __future__ import annotations

import csv
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

from lectern.gradebook import (
    GradebookSchema, apply_letter_cuts, compute_weighted, render_view,
)
from lectern.student_id import pad_student_id
from lectern import gradebook_ledger


def _vault_root(p: Path) -> Path:
    """Walk up from p to the dir containing an `.obsidian` folder (the vault root)."""
    for parent in [p, *p.resolve().parents]:
        if (parent / ".obsidian").is_dir():
            return parent
    raise RuntimeError("no .obsidian vault root above " + str(p))


@dataclass(frozen=True)
class RegistryEntry:
    short_name: str
    scores_path: Path
    link: str | None = None              # vault note path (no ext) — assignment header → grading note
    analysis: str | None = None          # vault note path (no ext) — → ITEM_ANALYSIS (exam stats)
    breakdown: tuple[Path, ...] = ()     # per-student×question matrices (one per form; empty = none)
    kind: str | None = None              # 'exam' | 'lab' | 'reading'; None → inferred


def load_registry(path: Path) -> list[RegistryEntry]:
    """Parse components.yaml → [RegistryEntry]. `scores` is resolved relative to
    the registry file. Missing file / malformed entry → SystemExit naming it."""
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    comps = data.get("components")
    if not isinstance(comps, list) or not comps:
        sys.exit(f"{path}: 'components' must be a non-empty list")
    base = path.resolve().parent
    out: list[RegistryEntry] = []
    for c in comps:
        if not isinstance(c, dict) or "short_name" not in c or "scores" not in c:
            sys.exit(f"{path}: each component needs 'short_name' and 'scores' (got {c!r})")
        sp = (base / str(c["scores"])).resolve()
        if not sp.exists():
            sys.exit(f"{path}: scores file not found: {c['scores']} (resolved {sp})")
        bp = c.get("breakdown")
        breakdown: tuple[Path, ...]
        if bp is None:
            breakdown = ()
        elif isinstance(bp, list):
            breakdown = tuple(
                (base / str(item)).resolve()
                for item in bp
                if (base / str(item)).resolve().exists()
            )
        elif isinstance(bp, str) and "*" in bp:
            breakdown = tuple(sorted(p.resolve() for p in base.glob(bp)))
        else:
            resolved = (base / str(bp)).resolve()
            breakdown = (resolved,) if resolved.exists() else ()
        out.append(RegistryEntry(
            short_name=str(c["short_name"]),
            scores_path=sp,
            link=str(c["link"]) if c.get("link") else None,
            analysis=str(c["analysis"]) if c.get("analysis") else None,
            breakdown=breakdown,
            kind=str(c["kind"]) if c.get("kind") else None,
        ))
    return out


def read_component_scores(path: Path) -> dict[str, tuple[float, str]]:
    """Read a component scores CSV → {padded_sid: (earned, status)}.

    Requires columns sid, score, status (extra columns ignored). Semantics:
    - status == 'Graded'      → earned = float(score)
    - status startswith 'No-show' → earned = 0.0 (the L counts)
    - blank score AND blank status → ungraded: row excluded entirely
    A non-numeric score on a 'Graded' row → SystemExit (never silently zero).
    """
    out: dict[str, tuple[float, str]] = {}
    with path.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            sid_raw = (r.get("sid") or "").strip()
            if not sid_raw:
                continue
            sid = pad_student_id(sid_raw)
            score_s = (r.get("score") or "").strip()
            status = (r.get("status") or "").strip()
            if not score_s and not status:
                continue  # ungraded
            if status.lower().startswith("no-show"):
                out[sid] = (0.0, status)
                continue
            try:
                out[sid] = (float(score_s), status or "Graded")
            except ValueError:
                sys.exit(f"{path}: non-numeric score {score_s!r} for sid {sid}")
    return out


def _read_roster(roster_csv: Path) -> dict[str, dict]:
    """{padded_sid: {display_name, enrollment_status}}. Empty dict if no file."""
    if not roster_csv or not roster_csv.exists():
        return {}
    out: dict[str, dict] = {}
    with roster_csv.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            sid = pad_student_id((r.get("student_id") or "").strip())
            if not sid:
                continue
            out[sid] = {
                "display_name": (r.get("display_name") or "").strip(),
                "enrollment_status": (r.get("enrollment_status") or "enrolled").strip(),
            }
    return out


def _name_from_scores_row(sc_path: Path, sid: str) -> str:
    """Best-effort 'First Last' from a component scores file (last,first cols)."""
    with sc_path.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if pad_student_id((r.get("sid") or "").strip()) == sid:
                first = (r.get("first") or "").strip()
                last = (r.get("last") or "").strip()
                return f"{first} {last}".strip()
    return ""


def build_gradebook(
    registry_csv: Path, roster_csv: Path, schema: GradebookSchema, out: Path,
    *, section: str = "", term: str = "",
) -> list[dict]:
    """Roll per-component score files into gradebook.csv (+ gradebook.md).

    Returns the list of row dicts (also written to out/gradebook.csv)."""
    entries = load_registry(registry_csv)
    # short_name -> {sid: (earned, status)}
    comp_scores = {e.short_name: read_component_scores(e.scores_path) for e in entries}
    comp_path = {e.short_name: e.scores_path for e in entries}
    roster = _read_roster(roster_csv)
    total_cols = len(schema.columns)

    # union of all student SIDs across roster + every component file
    sids: set[str] = set(roster)
    for sc in comp_scores.values():
        sids |= set(sc)

    rows: list[dict] = []
    for sid in sorted(sids):
        raw: dict[str, float] = {}
        graded: set[str] = set()
        real_grade = False  # ≥1 genuinely-graded (not No-show) outcome
        for short, scmap in comp_scores.items():
            if sid in scmap:
                earned, status = scmap[sid]
                raw[short] = earned
                graded.add(short)
                if not status.lower().startswith("no-show"):
                    real_grade = True
        rinfo = roster.get(sid)
        # A student absent from the roster who only ever NO-SHOWED is a dropped
        # student resurrected by the union — exclude. Off-roster students with a
        # real grade (e.g. a new enrollee) are kept and flagged stale-roster.
        if rinfo is None and not real_grade:
            continue
        standing = compute_weighted(raw, schema, graded_only=True, graded_cols=graded)
        name = (rinfo or {}).get("display_name") or ""
        flags: list[str] = []
        if not rinfo:
            flags.append("stale-roster")
            # pull a name from whichever component file scored this student
            for short in graded:
                name = _name_from_scores_row(comp_path[short], sid) or name
                if name:
                    break
        enroll = (rinfo or {}).get("enrollment_status", "unknown" if not rinfo else "enrolled")
        # Withdrawal trumps the computed standing: a roster status of 'withdrawn'
        # yields a W (and the 'withdrew' flag), mirroring the Canvas-import path.
        if enroll == "withdrawn":
            letter = "W"
            if "withdrew" in schema.flags:
                flags.append("withdrew")
        else:
            letter = apply_letter_cuts(standing, schema)
        rows.append({
            "student_id": sid,
            "display_name": name,
            "enrollment_status": enroll,
            "raw_scores": json.dumps(raw),
            "standing_score": standing,
            "weighted_score": standing,           # cockpit-compat alias
            "letter_grade": letter,
            "in_progress": "true" if len(graded) < total_cols else "false",
            "graded_cols": str(len(graded)),
            "total_cols": str(total_cols),
            "flags": ",".join(flags),
        })

    out.mkdir(parents=True, exist_ok=True)
    csv_path = out / "gradebook.csv"
    fieldnames = ["student_id", "display_name", "enrollment_status", "raw_scores",
                  "standing_score", "weighted_score", "letter_grade",
                  "in_progress", "graded_cols", "total_cols", "flags"]
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    # ── ledger surfaces ──────────────────────────────────────────────
    by_short = {e.short_name: e for e in entries}
    # vault-relative path to the assignments dir (for header wikilinks)
    try:
        vault_rel = out.resolve().relative_to(_vault_root(out))
        assign_dir_rel = str(vault_rel / "assignments")
    except (ValueError, RuntimeError):
        assign_dir_rel = "assignments"
    overview = gradebook_ledger.render_overview(
        rows, schema, entries, assign_dir_rel=assign_dir_rel,
        course=schema.course, term=term, section=section)
    student_block = gradebook_ledger.render_student_view_block(schema)
    (out / "GRADEBOOK.md").write_text(
        "---\ntype: gradebook\n"
        f"tags: [gradebook, teaching, {schema.course.lower().replace(' ', '-')}, term-{term}]\n"
        f"course: \"{schema.course}\"\nterm: \"{term}\"\nsection: \"{section}\"\n"
        "visibility: private\nicon: LiBookCheck\niconColor: var(--text-normal)\n---\n"
        f"# {schema.course} §{section} — Gradebook ({term})\n\n"
        + overview + "\n\n" + student_block, encoding="utf-8")
    adir = out / "assignments"; adir.mkdir(exist_ok=True)
    for e in entries:
        (adir / f"{e.short_name}.md").write_text(
            gradebook_ledger.render_assignment_page(e, schema, rows), encoding="utf-8")
    # The new GRADEBOOK.md ledger supersedes the legacy standalone gradebook.md view;
    # `build` no longer emits it (render_view remains for the legacy `import` path).
    return rows


def export_canvas(gradebook_csv: Path, schema: GradebookSchema, out: Path) -> None:
    """Emit a Canvas bulk-upload CSV: 'SIS User ID' + one column per GRADED
    component (its schema canvas_title), values = raw earned points. A component
    that no student has graded gets no column (never upload-zeroes ungraded work).
    A student with no score on an otherwise-graded component gets a blank cell.
    """
    short_to_title = {c["short_name"]: c["canvas_title"] for c in schema.columns}
    schema_order = [c["short_name"] for c in schema.columns]

    rows: list[dict] = []
    graded_shorts: set[str] = set()
    with gradebook_csv.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            raw = json.loads(r.get("raw_scores") or "{}")
            graded_shorts |= set(raw)
            rows.append({"sid": r["student_id"], "raw": raw})

    cols = [s for s in schema_order if s in graded_shorts]
    header = ["SIS User ID"] + [short_to_title[s] for s in cols]
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        for row in rows:
            cells = [row["sid"]]
            for s in cols:
                v = row["raw"].get(s)
                cells.append("" if v is None else str(v))
            w.writerow(cells)
