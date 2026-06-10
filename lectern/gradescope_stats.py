"""reg-gradescope-stats — per-outcome item analysis from Gradescope evaluations.

Parses Gradescope's *Export Evaluations* dump (one CSV per question, under
``<eval-dir>/group<Form>/``) and joins each rubric-item column back to the stable
``form·Qn·slot`` keys in the exam's grading note. Computes per-question difficulty
(p-value) + per-distractor selection counts, with flags for non-functioning
distractors (✗), distractors more popular than the key (⚠), and the miskey alarm
(a credited item applied yet the question mean is 0 → rubric point value misset).

Emits three artifacts into ``--out-dir``:
  - ``ITEM_ANALYSIS.md``     — Obsidian-tagged Markdown report (ISA/grader-internal)
  - ``item_analysis.html``   — self-contained "broadsheet" (newspaper/agate house style)
  - ``item_analysis.json``   — the underlying stats (re-render / downstream analytics)

It can also splice a *Post-exam statistics* link block into the grading note
(``--link-grading-note``).

This graduates the validated ``build_item_analysis.py`` prototype. The grading
note supplies question names, point values, types, and the per-outcome key map;
the evaluations supply who-picked-what. The two share one SID-free join key per
distractor, so the analytics round-trip is exact.

CLI:
  reg-gradescope-stats --eval-dir DIR --grading-note NOTE.md --scores SCORES.csv \
      --out-dir DIR --course "CECS 378" --term "Summer 2026" --section 01 \
      --exam "Exam 1" --graded 2026-06-09 [--link-grading-note]

Evaluation-CSV column shape (validated against the Su26 Exam 1 export):
  Assignment Submission ID, Question Submission ID, First Name, Last Name, SID,
  Email, Sections, Score, Submission Time, <one bool column per rubric item…>,
  Adjustment, Comments, Grader, Tags
Each rubric-item column header IS the item text; each cell is ``true``/``false``.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import statistics as st
import sys
from collections import Counter
from pathlib import Path

PREFIX_LAST = "Submission Time"   # last identity column before the rubric items
SUFFIX_FIRST = "Adjustment"       # first trailing column after the rubric items
QHEAD = re.compile(r"^####\s+(\w+)·Q(\d+)\s+·\s+(.+?)\s+·\s+(\d+)\s+pts\s+·\s+(\w+)")
ROW = re.compile(r"^\|\s*([+\-]?\d+|·)\s*\|\s*`([^`]+)`\s*\|\s*(.+?)\s*\|\s*$")
# Soft "no-credit blank" markers. Deliberately EXCLUDES "blank" — FIB items read
# "blank 1 = …", so "blank" would wrongly swallow them / their order columns.
NONE_WORDS = ("no answer", "no response", "no marks", "unknown",
              "multiple marks", "both /")
TEMPLATE = Path(__file__).resolve().parent / "references" / "item_analysis.template.html"


# ── grading-note parse + join ───────────────────────────────────────────────

def parse_grading_note(path: Path) -> dict:
    """form -> {qnum: {"name","pts","type","items":[(pts,key,text)…]}}."""
    forms: dict[str, dict] = {}
    cur = None
    for ln in path.read_text(encoding="utf-8").splitlines():
        m = QHEAD.match(ln)
        if m:
            f, n, name, pts, typ = m.groups()
            cur = {"name": name, "pts": int(pts), "type": typ, "items": []}
            forms.setdefault(f, {})[int(n)] = cur
            continue
        m = ROW.match(ln)
        if m and cur is not None and m.group(2) != "Key":
            cur["items"].append((m.group(1), m.group(2), m.group(3)))
    return forms


def norm(s: str) -> str:
    """Collapse whitespace + unify quote glyphs so note text == CSV header."""
    s = s.replace("“", '"').replace("”", '"').replace("’", "'")
    return re.sub(r"\s+", " ", s).strip()


def join_key(item_text: str, keymap: dict) -> tuple:
    """Resolve a CSV column header to (pts, key). Exact text first, then robust
    fallbacks: an MC ``(letter)`` prefix (survives prose typos); a no-credit blank
    column → the question's ``none`` key; an "(incorrect)"/"Incorrect order"
    column → the ``order`` key."""
    n = norm(item_text)
    if n in keymap:
        return keymap[n]
    low = n.lower()
    m = re.match(r"\(([a-h])\)", low)
    if m:
        want = m.group(1)
        for (pp, kk) in keymap.values():
            if kk.rsplit("·", 1)[-1] == want:
                return (pp, kk)
    none_key = next((v for v in keymap.values() if v[1].endswith("·none")), None)
    # explicit no-answer column wins even when it tacks on "/ incorrect"
    if none_key and low.startswith(("no answer", "no response")):
        return none_key
    # per-blank mis-order / wrong-mapping column → the order outcome
    if "incorrect" in low or "wrong" in low:
        base = next(iter(keymap.values()), ("0", "?·Q?"))[1].rsplit("·", 1)[0]
        return ("0", f"{base}·order")
    # remaining no-credit blank markers ("Both / No marks / Unknown", …)
    if none_key and any(w in low for w in NONE_WORDS):
        return none_key
    return ("0", "?")


def read_eval(path: Path, qmax: float):
    """Return (n, item_pairs, scores, anomalies, skipped).

    Excludes Gradescope's ``Rubric Numbers`` legend row (non-numeric submission
    id) and rows whose Score exceeds the question max (data-entry anomalies)."""
    with path.open(encoding="utf-8") as fh:
        rows = list(csv.reader(fh))
    header = rows[0]
    lo = header.index(PREFIX_LAST) + 1
    hi = header.index(SUFFIX_FIRST)
    score_idx = header.index("Score")
    items = header[lo:hi]
    counts = [0] * len(items)
    scores, anomalies, skipped = [], [], 0
    for r in rows[1:]:
        if not r or score_idx >= len(r) or not r[score_idx].strip():
            continue
        if not r[0].strip().isdigit():
            skipped += 1
            continue
        sc = float(r[score_idx])
        if qmax and sc > qmax + 1e-9:
            anomalies.append(((r[4].strip() if len(r) > 4 else "") or "no-SID", sc))
            continue
        scores.append(sc)
        for i, col in enumerate(range(lo, hi)):
            if col < len(r) and r[col].strip().lower() == "true":
                counts[i] += 1
    return len(scores), list(zip(items, counts)), scores, anomalies, skipped


# ── exam-level grade summary (from normalized scores csv) ───────────────────

def exam_summary(scores_path: Path, maxpts: int) -> dict | None:
    """Compute n / mean / median / sd / range / letter-distribution / per-form
    mean from a normalized exam scores CSV (last,first,sid,version,score,status).
    Only identified, graded papers count. Returns None if the file is absent."""
    if not scores_path or not scores_path.exists():
        return None
    rows = []
    with scores_path.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if (r.get("score") or "").strip() and (r.get("status") or "").strip() == "Graded" \
                    and (r.get("sid") or "").strip():
                rows.append(r)
    if not rows:
        return None
    sc = [float(r["score"]) for r in rows]

    def band(s):
        p = s / maxpts if maxpts else 0
        return "A" if p >= .9 else "B" if p >= .8 else "C" if p >= .7 else "D" if p >= .6 else "F"
    dist = Counter(band(s) for s in sc)
    form_means = {}
    for v in sorted({r["version"] for r in rows if r.get("version")}):
        vs = [float(r["score"]) for r in rows if r["version"] == v]
        if vs:
            form_means[v] = round(st.mean(vs), 1)
    return {
        "n": len(sc), "mean": round(st.mean(sc), 1), "median": round(st.median(sc), 1),
        "sd": round(st.pstdev(sc), 1), "min": int(min(sc)), "max": int(max(sc)),
        "maxpts": maxpts, "dist": {k: dist[k] for k in "ABCDF" if dist[k]},
        "form_means": form_means,
        # back-compat aliases used by older templates
        "formA_mean": form_means.get("A"), "formB_mean": form_means.get("B"),
    }


# ── core: compute the full stats dict ───────────────────────────────────────

def _form_dirs(eval_dir: Path) -> dict[str, Path]:
    """Map form label -> its group dir (``group<Form>``), sorted by label."""
    out = {}
    for p in sorted(eval_dir.glob("group*")):
        if p.is_dir():
            out[p.name[len("group"):]] = p
    return out


def compute_stats(eval_dir: Path, note_path: Path, scores_path: Path | None,
                  meta: dict) -> dict:
    note = parse_grading_note(note_path)
    forms_out: dict[str, list] = {}
    for f, gdir in _form_dirs(eval_dir).items():
        files = {}
        for p in gdir.glob("*.csv"):
            mm = re.match(r"(\d+)_", p.name)
            if mm:
                files[int(mm.group(1))] = p
        qs = []
        for n in sorted(files):
            qmeta = note.get(f, {}).get(n, {})
            qpts = qmeta.get("pts", 0)
            keymap = {norm(t): (p, k) for (p, k, t) in qmeta.get("items", [])}
            nrows, pairs, scores, anom, _sk = read_eval(files[n], qpts)
            denom = qpts or (max(scores) if scores else 1)
            full = sum(1 for s in scores if abs(s - denom) < 1e-9)
            credited = [(t, c, join_key(t, keymap)) for (t, c) in pairs]
            keyc = [c for (t, c, (pp, kk)) in credited if str(pp).startswith("+")]
            topc = max(keyc) if keyc else 0
            mean = sum(scores) / nrows if nrows else 0.0
            dists = []
            for (t, c, (pp, kk)) in credited:
                is_key = str(pp).startswith("+")
                dists.append({
                    "key": kk, "text": t, "n": c,
                    "pct": round(100 * c / nrows) if nrows else 0,
                    "is_key": is_key, "dead": (c == 0 and not is_key),
                    "over_key": bool(not is_key and topc and c > topc),
                })
            qs.append({
                "n": n, "name": qmeta.get("name", ""), "type": qmeta.get("type", ""),
                "pts": qpts, "nrows": nrows,
                "p": round(full / nrows, 2) if nrows else 0.0, "mean": round(mean, 2),
                "miskey": bool(mean < 1e-9 and topc > 0 and nrows),
                "anomalies": [{"sid": s, "score": v} for (s, v) in anom],
                "distractors": dists,
            })
        forms_out[f] = qs

    # exam max = total points on the first form
    maxpts = sum(q["pts"] for q in next(iter(forms_out.values()), []))
    return {
        "meta": meta,
        "exam": exam_summary(scores_path, maxpts) if scores_path else None,
        "forms": forms_out,
    }


# ── Markdown emitter ────────────────────────────────────────────────────────

def render_markdown(stats: dict) -> str:
    M = stats["meta"]
    course_tag = M.get("course", "").lower().replace(" ", "-")
    H = [
        "---", "type: item-analysis",
        f"tags: [teaching, {course_tag}, exam, gradescope, item-analysis, internal]",
        "visibility: private", "icon: LiChartBar", "iconColor: var(--color-blue)",
        "---", "",
        f"# {M.get('exam','Exam')} — Item Analysis ({M.get('course','')} {M.get('term','')})", "",
        "> [!info] Internal — generated from Gradescope *Export Evaluations*",
        "> Per-question difficulty + per-distractor selection counts, joined to the "
        "`form·Qn·slot` keys in [[GRADING_NOTE]]. Regenerate with `reg-gradescope-stats`.",
        "",
        "**Reading the tables.** *p* = fraction earning full marks (difficulty; "
        "lower = harder). A distractor chosen by **0** students is non-functioning "
        "(✗). A distractor chosen by **more** students than the key (⚠) is a "
        "miskey-or-genuinely-confusing item worth review.", "",
    ]
    for f, qs in stats["forms"].items():
        miskeyed = [q for q in qs if q["miskey"]]
        anomalies = [(q["n"], q["anomalies"]) for q in qs if q["anomalies"]]
        if miskeyed:
            H.append("> [!danger] Rubric point-value error — correct answers scored 0")
            for q in miskeyed:
                kc = max((d["n"] for d in q["distractors"] if d["is_key"]), default=0)
                H.append(f"> - **{f}·Q{q['n']} · {q['name']}**: the key item was applied to "
                         f"≈{kc} students but every score is 0 → the rubric item's points "
                         f"are set to **0** in Gradescope. Fix the point value, then re-sync.")
            H.append("")
        H.append("> [!abstract]- Difficulty summary (hardest first)")
        H.append(">")
        H.append("> | Q | Topic | Type | p | mean |")
        H.append("> | --- | --- | --- | --: | --: |")
        for q in sorted(qs, key=lambda r: r["p"]):
            H.append(f"> | {f}·Q{q['n']} | {q['name']} | {q['type']} | "
                     f"{q['p']:.2f} | {q['mean']:.2f}/{q['pts']} |")
        H.append("")
        if anomalies:
            H.append("> [!warning] Score anomalies (excluded from stats — likely grader data-entry errors)")
            for (n, anom) in anomalies:
                vals = ", ".join(f"{a['sid']}={a['score']:g}" for a in anom)
                H.append(f"> - **{f}·Q{n}**: {vals} (exceeds question max — verify in Gradescope)")
            H.append("")
        H.append(f"## Form {f}\n")
        for q in qs:
            H.append(f"#### {f}·Q{q['n']} · {q['name']} · {q['type']} · {q['pts']} pts")
            H.append(f"*n = {q['nrows']} · p = {q['p']:.2f} · mean = {q['mean']:.2f}/{q['pts']}*")
            H.append("")
            H.append("| Key | Distractor | n | % | |")
            H.append("| --- | --- | --: | --: | --- |")
            for d in q["distractors"]:
                flag = "✔ key" if d["is_key"] else "✗ dead" if d["dead"] else "⚠ > key" if d["over_key"] else ""
                H.append(f"| `{d['key']}` | {d['text']} | {d['n']} | {d['pct']:.0f}% | {flag} |")
            H.append("")
    return "\n".join(H)


# ── HTML (broadsheet) emitter ───────────────────────────────────────────────

def render_html(stats: dict, template_path: Path = TEMPLATE) -> str:
    tpl = template_path.read_text(encoding="utf-8")
    blob = json.dumps(stats, separators=(",", ":"), ensure_ascii=False).replace("</", "<\\/")
    return tpl.replace("__DATA__", blob)


# ── grading-note cross-link ─────────────────────────────────────────────────

LINK_MARK = "<!-- reg-gradescope-stats:link -->"


def link_into_grading_note(note_path: Path, md_name: str, html_name: str) -> bool:
    """Splice a *Post-exam statistics* section into the grading note (idempotent
    via a sentinel comment). Returns True if it wrote a change."""
    text = note_path.read_text(encoding="utf-8")
    if LINK_MARK in text:
        return False
    block = (
        f"\n{LINK_MARK}\n## Post-exam statistics\n"
        f"Per-distractor item analysis from this exam's Gradescope evaluations "
        f"(difficulty, dead distractors, miskey alarm):\n\n"
        f"- [[{Path(md_name).stem}|Item analysis (Markdown)]]\n"
        f"- `{html_name}` — Item Analysis broadsheet (open in a browser)\n"
    )
    # insert before an "## Appeals" section if present, else append
    if "\n## Appeals" in text:
        text = text.replace("\n## Appeals", block + "\n## Appeals", 1)
    else:
        text = text.rstrip() + "\n" + block
    note_path.write_text(text, encoding="utf-8")
    return True


# ── CLI ─────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="reg-gradescope-stats",
        description="Per-outcome item analysis from Gradescope Export Evaluations.")
    ap.add_argument("--eval-dir", type=Path, required=True,
                    help="dir containing group<Form>/ subdirs of per-question CSVs")
    ap.add_argument("--grading-note", type=Path, required=True,
                    help="GRADING_NOTE.md (supplies names/points/types + key map)")
    ap.add_argument("--scores", type=Path,
                    help="normalized exam scores CSV (for the exam-level summary)")
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--course", default="")
    ap.add_argument("--term", default="")
    ap.add_argument("--section", default="")
    ap.add_argument("--exam", default="Exam")
    ap.add_argument("--graded", default="")
    ap.add_argument("--link-grading-note", action="store_true",
                    help="splice a stats-link section into the grading note")
    ap.add_argument("--no-html", action="store_true", help="skip the HTML broadsheet")
    a = ap.parse_args(argv)

    meta = {"course": a.course, "term": a.term, "section": a.section,
            "exam": a.exam, "graded": a.graded}
    stats = compute_stats(a.eval_dir, a.grading_note, a.scores, meta)
    nq = sum(len(v) for v in stats["forms"].values())
    if not nq:
        sys.exit(f"no question CSVs found under {a.eval_dir}/group*/")

    a.out_dir.mkdir(parents=True, exist_ok=True)
    (a.out_dir / "item_analysis.json").write_text(
        json.dumps(stats, indent=1, ensure_ascii=False), encoding="utf-8")
    (a.out_dir / "ITEM_ANALYSIS.md").write_text(render_markdown(stats), encoding="utf-8")
    outs = ["item_analysis.json", "ITEM_ANALYSIS.md"]
    if not a.no_html:
        (a.out_dir / "item_analysis.html").write_text(render_html(stats), encoding="utf-8")
        outs.append("item_analysis.html")
    if a.link_grading_note and a.grading_note.exists():
        if link_into_grading_note(a.grading_note, "ITEM_ANALYSIS.md", "item_analysis.html"):
            print(f"→ linked stats into {a.grading_note.name}")
    print(f"→ {a.out_dir} : {', '.join(outs)} ({nq} questions, "
          f"{len(stats['forms'])} forms)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
