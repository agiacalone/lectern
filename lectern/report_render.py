"""Render the canonical instructor lab report (REPORT.md) — deterministic.

Pure function of (recon bundle, digest-merged cohort.csv, optional gradebook
standing, ReportManifest). Markdown assembly via f-strings + the agate chart
helpers; no jinja2, no network.
"""
import csv
import statistics
from lectern.report_charts import bar_chart, histogram, funnel
from lectern.report_recommend import recommend
from lectern.report_manifest import load_report_manifest


def _read_cohort(path):
    with open(path) as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["points"] = int(float(r.get("points") or 0))
        r["writeup_score"] = int(float(r.get("writeup_score") or 0))
        r["proposed"] = r["points"] + r["writeup_score"]
        r["honor_ok"] = str(r.get("honor_ok")).lower() in ("true", "1", "yes")
        r["writeup_flags"] = [x for x in (r.get("writeup_flags") or "").split(";") if x]
    return rows


def _letter(pct, cuts):
    for letter, cut in sorted(cuts.items(), key=lambda kv: -kv[1]):
        if pct >= cut:
            return letter
    return "F"


def _standing(rows, manifest):
    """Mid-term fallback: the lab's own proposed % (no gradebook supplied)."""
    denom = (manifest.auto_max + manifest.writeup_max) or 1
    return {r["github_id"]: (r["proposed"] / denom * 100) for r in rows}


def render_report(bundle_dir, cohort_csv, manifest, *, standing_csv=None):
    rows = _read_cohort(cohort_csv)
    # cohort.csv is the enrolled population (withdrawn/dropped excluded upstream by
    # recon). All enrolled count in the distribution — including a non-submission's
    # 0, which is a real enrolled score, not an exclusion. Honor-fail/zero routing
    # happens only in the recommendations (edge cases), never in the stats.
    enrolled = rows
    proposed = [r["proposed"] for r in enrolled]
    n = len(enrolled)
    mean = statistics.mean(proposed) if proposed else 0
    median = statistics.median(proposed) if proposed else 0
    sigma = statistics.pstdev(proposed) if len(proposed) > 1 else 0
    standing = _standing(rows, manifest)

    dist = {}
    for r in enrolled:
        L = _letter(r["proposed"], manifest.letter_cuts)
        dist[L] = dist.get(L, 0) + 1
    grade_rows = [(L, dist.get(L, 0)) for L in ["A", "B", "C", "D", "F"]]
    hist_bins = [("<70", 0, 70), ("70-79", 70, 80), ("80-89", 80, 90), ("90-100", 90, 100)]
    ward_rows = []
    for w in manifest.wards:
        cleared = sum(1 for r in rows if w.key in (r.get("cleared", "") or ""))
        ward_rows.append((w.label, cleared))
    rec = recommend(rows, standing, manifest)

    out = []
    out.append(f"# {manifest.lab} · Instructor Report")
    out.append(f"*{manifest.course} · {manifest.term} · §{manifest.section} — n={n} · "
               f"mean {mean:.1f} · median {median:.0f} · σ {sigma:.1f}*\n")
    out.append("## Distribution\n```")
    out.append(f"GRADE DISTRIBUTION  n={n}  μ={mean:.1f}  σ={sigma:.1f}")
    out.append(bar_chart(grade_rows))
    out.append("\nSCORE HISTOGRAM")
    out.append(histogram(proposed, hist_bins))
    out.append("\nWARD-CLEAR FUNNEL")
    out.append(funnel(ward_rows))
    out.append("```\n")

    out.append("## ➊ Grade table\n")
    out.append("| Student | github | Auto | Writeup | **Proposed** | flags |")
    out.append("| --- | --- | --: | --: | --: | --- |")
    for r in sorted(rows, key=lambda r: -r["proposed"]):
        out.append(f"| {r['student']} | {r['github_id']} | {r['points']} | "
                   f"{r['writeup_score']} | **{r['proposed']}** | {';'.join(r['writeup_flags'])} |")

    out.append("\n## Grading recommendations\n")
    for title, items in [("Confirm (routine)", rec.confirm),
                         ("Edge cases needing a call", rec.edge_cases),
                         ("Low-confidence / needs-human-read", rec.low_confidence),
                         ("Upward-adjustment candidates", rec.upward)]:
        out.append(f"### {title}")
        if items:
            out.extend(f"- **{i['student']}** ({i['github_id']}) — {i['reason']}" for i in items)
        else:
            out.append("- _none_")
        out.append("")

    out.append("## Canvas entry sheet\n")
    out.append("| Student (Last, First) | Proposed |")
    out.append("| --- | --: |")
    for r in sorted(rows, key=lambda r: r["student"].split()[-1] if r["student"] else ""):
        out.append(f"| {r['student']} | {r['proposed']} |")

    out.append("\n## Provenance & caveats\n")
    out.append("Part A (autograde / honor / commits) = audit-grade facts. Part B (writeup "
               "scores + comments) = advisory, instructor-confirmed. Rendered deterministically "
               "by `reg-lab-report`.")
    return "\n".join(out)


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(prog="reg-lab-report render")
    ap.add_argument("--bundle", required=True)
    ap.add_argument("--cohort", required=True)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--standing")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    m = load_report_manifest(a.manifest)
    text = render_report(a.bundle, a.cohort, m, standing_csv=a.standing)
    with open(a.out, "w") as f:
        f.write(text + "\n")
    print(f"wrote {a.out}")
    return 0
