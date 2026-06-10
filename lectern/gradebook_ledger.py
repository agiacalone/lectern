"""Render the grades ledger surfaces from the rolled-up gradebook.

Pure functions — data in, markdown out, no I/O beyond an optional breakdown matrix
read. The bookkeeping model: a grouped general ledger (overview), subsidiary ledgers
(per-assignment pages), account statements (per-student view), each reconciled to its
source documents (the component scores files).
"""
from __future__ import annotations

import csv
import json
import statistics
from pathlib import Path

from lectern.gradebook import GradebookSchema, apply_letter_cuts


def _groups_in_order(schema: GradebookSchema) -> list[str]:
    seen: list[str] = []
    for col in schema.columns:
        g = col.get("group") or ""
        if g not in seen:
            seen.append(g)
    return seen


def _cols_by_group(schema: GradebookSchema) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for col in schema.columns:
        out.setdefault(col.get("group") or "", []).append(col)
    return out


def _group_pct(raw: dict, cols: list[dict]) -> float | None:
    earned = maxp = 0.0
    any_graded = False
    for c in cols:
        sn = c.get("short_name") or ""
        if sn in raw:
            any_graded = True
            earned += float(raw[sn])
            maxp += float(c.get("points") or 0)
    if not any_graded or maxp <= 0:
        return None
    return round(earned / maxp * 100)


def render_overview(rows: list[dict], schema: GradebookSchema,
                    registry: list, *, assign_dir_rel: str,
                    course: str = "", term: str = "", section: str = "") -> str:
    groups = _groups_in_order(schema)
    by_group = _cols_by_group(schema)
    weights = schema.weights

    def head_link(col):
        sn = col.get("short_name") or ""
        label = (col.get("title") or sn)
        return f"[[{assign_dir_rel}/{sn}|{label}]]"

    # header: per group → component columns + a "grp%" subtotal
    head = ["Student"]
    for g in groups:
        head += [head_link(c) for c in by_group[g]]
        head.append(f"{g[:3]}%")
    head += ["Standing", "Letter", "Graded"]

    lines = [
        f"_Groups & weights: " +
        " · ".join(f"{g} {int(weights.get(g, 0) * 100)}%" for g in groups) +
        "_  ·  ungraded = `·`, in-progress = `*`",
        "",
        "| " + " | ".join(head) + " |",
        "| " + " | ".join(["---"] + ["--:"] * (len(head) - 2) + ["---"]) + " |",
    ]
    for r in rows:
        raw = json.loads(r.get("raw_scores") or "{}")
        cells = [r.get("display_name") or r["student_id"]]
        for g in groups:
            for c in by_group[g]:
                sn = c.get("short_name") or ""
                cells.append(f"{float(raw[sn]):g}" if sn in raw else "·")
            sub = _group_pct(raw, by_group[g])
            cells.append("·" if sub is None else f"{sub:g}%")
        inprog = str(r.get("in_progress")) == "true"
        cells.append(f"{float(r.get('standing_score') or 0):g}%" + ("*" if inprog else ""))
        cells.append((r.get("letter_grade") or "") + ("*" if inprog else ""))
        cells.append(f"{r.get('graded_cols')}/{r.get('total_cols')}")
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def _col_for(schema: GradebookSchema, short: str) -> dict:
    for c in schema.columns:
        if (c.get("short_name") or "") == short:
            return c
    return {}


def _read_matrix(path: Path | None) -> tuple[list[str], list[list[str]]]:
    if not path or not path.exists():
        return [], []
    with path.open(encoding="utf-8") as fh:
        rows = list(csv.reader(fh))
    return (rows[0], rows[1:]) if rows else ([], [])


def _form_label(path: Path) -> str:
    """Derive a form label from the filename.

    ``item_scores_A.csv`` → ``"A"``; anything else → the stem.
    """
    stem = path.stem  # e.g. "item_scores_A"
    prefix = "item_scores_"
    if stem.startswith(prefix):
        return stem[len(prefix):]
    return stem


def reconcile_assignment(entry, rows: list[dict]) -> dict[str, list[str]]:
    """Reconcile the per-question matrix totals to the recorded component score.

    Iterates ALL matrices in ``entry.breakdown`` (a tuple of Paths). A student
    appears in exactly one form's matrix; the union covers all forms.

    Returns a dict with two keys:
    - ``"mismatches"``: value-mismatch messages (grid total ≠ recorded score) and
      malformed-matrix flags — genuine bookkeeping errors.
    - ``"reconciling"``: roster-difference messages ("recorded but no grid row" /
      "grid row but no recorded score") — legitimate reconciling items, not errors.

    Both lists empty → fully balanced.
    """
    empty: dict[str, list[str]] = {"mismatches": [], "reconciling": []}
    # entry.breakdown is a tuple[Path, ...]; empty → no grid to check
    matrices = entry.breakdown if isinstance(entry.breakdown, tuple) else ()
    if not matrices:
        return empty

    # Build recorded {sid: score} from gradebook rows
    recorded: dict[str, float] = {}
    for r in rows:
        raw = json.loads(r.get("raw_scores") or "{}")
        if entry.short_name in raw:
            recorded[r["student_id"]] = float(raw[entry.short_name])

    mismatches: list[str] = []
    reconciling: list[str] = []
    grid_sids: set[str] = set()
    any_valid_matrix = False

    for matrix_path in matrices:
        header, mrows = _read_matrix(matrix_path)
        if not header:
            continue
        # Guard malformed matrix missing required columns — that IS a problem
        if "student_id" not in header or "total" not in header:
            mismatches.append(
                f"{matrix_path.name}: breakdown matrix missing student_id/total column"
            )
            continue
        any_valid_matrix = True
        sid_i = header.index("student_id")
        tot_i = header.index("total")
        for mr in mrows:
            sid = mr[sid_i]
            grid_sids.add(sid)
            if sid in recorded:
                grid_total = float(mr[tot_i] or 0)
                if abs(grid_total - recorded[sid]) > 1e-6:
                    mismatches.append(
                        f"{sid}: grid total {grid_total:g} ≠ recorded {recorded[sid]:g}"
                    )

    # Sid set differences across ALL forms combined — only when ≥1 valid matrix.
    # These are reconciling items (e.g. no-shows), NOT bookkeeping errors.
    if any_valid_matrix:
        for sid in set(recorded) - grid_sids:
            reconciling.append(f"{sid}: recorded but no grid row")
        for sid in grid_sids - set(recorded):
            reconciling.append(f"{sid}: grid row but no recorded score")
    return {"mismatches": mismatches, "reconciling": reconciling}


def render_assignment_page(entry, schema: GradebookSchema, rows: list[dict]) -> str:
    col = _col_for(schema, entry.short_name)
    title = col.get("title") or entry.short_name
    maxp = float(col.get("points") or 0)
    kind = entry.kind or ("exam" if "exam" in entry.short_name or "final" in entry.short_name else "lab")

    out = [
        "---", "type: gradebook-assignment",
        f"tags: [gradebook, gradebook-assignment, teaching, {schema.course.lower().replace(' ', '-')}]",
        f"component: {entry.short_name}", "visibility: private",
        "icon: LiClipboardList", "iconColor: var(--text-normal)", "---", "",
        f"# {title} — grade breakdown", "",
    ]
    src = []
    if entry.link:
        src.append(f"[[{entry.link}|grading note]]")
    if entry.analysis:
        src.append(f"[[{entry.analysis}|item analysis]]")
    if src:
        out.append("> [!info] Source · " + " · ".join(src))
        out.append("")

    # score roster (a subsidiary ledger: one line per student)
    scored = []
    for r in rows:
        raw = json.loads(r.get("raw_scores") or "{}")
        if entry.short_name in raw:
            scored.append((r.get("display_name") or r["student_id"], float(raw[entry.short_name])))
    out += ["## Scores", "",
            "| Student | Score | % |", "| --- | --: | --: |"]
    for name, sc in sorted(scored, key=lambda t: -t[1]):
        pct = f"{round(sc / maxp * 100)}%" if maxp else "—"
        out.append(f"| {name} | {sc:g}/{maxp:g} | {pct} |")
    out.append("")
    if scored:
        vals = [s for _, s in scored]
        n = len(vals)
        mean = sum(vals) / n
        med = statistics.median(vals)
        sigma = statistics.pstdev(vals) if n > 1 else 0.0
        # IMPORTANT 4a — letter-band distribution at component's own scale
        def _band(sc):
            pct = sc / maxp if maxp else 0
            if pct >= 0.9: return "A"
            if pct >= 0.8: return "B"
            if pct >= 0.7: return "C"
            if pct >= 0.6: return "D"
            return "F"
        bands: dict[str, int] = {"A": 0, "B": 0, "C": 0, "D": 0, "F": 0}
        for v in vals:
            bands[_band(v)] += 1
        dist = " ".join(f"{k}:{v}" for k, v in bands.items())
        out.append(
            f"*n = {n} · mean = {mean:.1f}/{maxp:g} · median = {med:g} · σ = {sigma:.1f} · {dist}*"
        )
        out.append("")

    # reconciliation banners — two separate callouts for two separate concerns
    recon = reconcile_assignment(entry, rows)
    if recon["mismatches"]:
        out.append("> [!danger] Out of balance — grid totals ≠ recorded scores")
        out += [f"> - {f}" for f in recon["mismatches"]]
        out.append("")
    if recon["reconciling"]:
        out.append("> [!note] Reconciling items (e.g. no-shows: recorded score with no graded submission)")
        out += [f"> - {f}" for f in recon["reconciling"]]
        out.append("")

    # exam: item-analysis embed + collapsible per-question grid (one per form)
    if kind == "exam":
        # IMPORTANT 4b — inline item-analysis transclusion
        if entry.analysis:
            out.append(f"![[{entry.analysis}]]")
            out.append("")
        matrices = entry.breakdown if isinstance(entry.breakdown, tuple) else ()
        for matrix_path in matrices:
            header, mrows = _read_matrix(matrix_path)
            if not header:
                continue
            label = _form_label(matrix_path)
            out += [f"> [!abstract]- Per-question grid — Form {label}", ">",
                    "> | " + " | ".join(header) + " |",
                    "> | " + " | ".join(["---"] * len(header)) + " |"]
            for mr in mrows:
                out.append("> | " + " | ".join(mr) + " |")
            out.append("")
    else:
        # IMPORTANT 4c — per-criterion table for labs with extra columns
        if entry.scores_path and entry.scores_path.exists():
            with entry.scores_path.open(encoding="utf-8") as fh:
                sc_reader = csv.DictReader(fh)
                sc_header = sc_reader.fieldnames or []
                _std_cols = {"last", "first", "sid", "version", "score", "status"}
                extra_cols = [h for h in sc_header if h not in _std_cols]
                if extra_cols:
                    sc_rows = list(sc_reader)
                    # build sid → row mapping
                    sid_map: dict[str, dict] = {}
                    for sc_row in sc_rows:
                        from lectern.student_id import pad_student_id
                        sid = pad_student_id((sc_row.get("sid") or "").strip())
                        if sid:
                            sid_map[sid] = sc_row
                    # render per-criterion table: student × extra_cols
                    out.append("## Per-criterion breakdown")
                    out.append("")
                    crit_header = ["Student"] + extra_cols
                    out.append("| " + " | ".join(crit_header) + " |")
                    out.append("| " + " | ".join(["---"] * len(crit_header)) + " |")
                    for r in rows:
                        raw = json.loads(r.get("raw_scores") or "{}")
                        if entry.short_name not in raw:
                            continue
                        sid = r["student_id"]
                        name = r.get("display_name") or sid
                        sc_row = sid_map.get(sid, {})
                        cells = [name] + [sc_row.get(c, "") for c in extra_cols]
                        out.append("| " + " | ".join(cells) + " |")
                    out.append("")
    return "\n".join(out)


def render_student_view_block(schema: GradebookSchema) -> str:
    """A DataviewJS block rendering one compact statement per student from
    gradebook.csv (read live). Component short_name → {title, max} from the schema
    is baked in so the view needs no schema file at render time."""
    cols = [{"short": c.get("short_name") or "", "title": c.get("title") or "",
             "max": float(c.get("points") or 0), "group": c.get("group") or ""}
            for c in schema.columns]
    cols_json = json.dumps(cols)
    # BLOCKER 1 — RFC-4180 compliant JS CSV parser (handles doubled-quote escaping)
    return (
        "## Per-student statements\n\n"
        "```dataviewjs\n"
        f"const COLS = {cols_json};\n"
        "const csvPath = dv.current().file.folder + \"/gradebook.csv\";\n"
        "const text = await app.vault.adapter.read(csvPath);\n"
        "const lines = text.trim().split(/\\r?\\n/);\n"
        "const H = lines[0].split(\",\");\n"
        "const parse = (l) => { const c=[]; let q=false,cur=\"\";\n"
        "  for (let i=0;i<l.length;i++){ const ch=l[i];\n"
        "    if(q){ if(ch=='\"'){ if(l[i+1]=='\"'){cur+='\"';i++;} else q=false; } else cur+=ch; }\n"
        "    else { if(ch=='\"')q=true; else if(ch==',') {c.push(cur);cur=\"\";} else cur+=ch; }\n"
        "  } c.push(cur);\n"
        "  const o={}; H.forEach((h,i)=>o[h]=c[i]||\"\"); return o; };\n"
        "const rows = lines.slice(1).map(parse);\n"
        "for (const r of rows) {\n"
        "  // schema-tolerant: new build uses raw_scores (short-name keyed) + standing_score;\n"
        "  // legacy/backfilled import uses short_scores (short-name keyed) + canvas_final_score.\n"
        "  let raw={}; try{ raw=JSON.parse(r.short_scores||r.raw_scores||\"{}\") }catch(e){}\n"
        "  const items = COLS.filter(c=>c.short in raw)\n"
        "    .map(c=>`[[assignments/${c.short}|${c.title}]] ${raw[c.short]}/${c.max}`).join(\" · \");\n"
        "  const standing = r.standing_score||r.override_score||r.canvas_final_score||r.weighted_score||\"—\";\n"
        "  const letter = r.override_grade||r.letter_grade||\"\";\n"
        "  const star = String(r.in_progress)===\"true\"?\"*\":\"\";\n"
        "  dv.header(4, `${r.display_name} — ${standing}%${star} ${letter}${star}`);\n"
        "  dv.paragraph(items || \"_no graded components yet_\");\n"
        "}\n"
        "```\n"
    )
