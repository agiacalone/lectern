"""Write the deterministic recon bundle (Part A facts): repos/, cohort.csv, FACTS.md."""
from __future__ import annotations
from pathlib import Path
import csv, json
from lectern.recon_record import RepoRecord, record_to_dict

def write_bundle(records: list[RepoRecord], out_dir: Path, *,
                 lab_name: str, total_points: int) -> None:
    out = Path(out_dir); (out / "repos").mkdir(parents=True, exist_ok=True)
    for r in records:
        (out / "repos" / f"{r.github_id}.json").write_text(
            json.dumps(record_to_dict(r), indent=2, sort_keys=True))
    _write_cohort_csv(records, out / "cohort.csv")
    _write_facts_md(records, out / "FACTS.md", lab_name=lab_name, total_points=total_points)
    (out / "bundle.json").write_text(json.dumps(
        {"lab": lab_name, "total_points": total_points, "n": len(records)}, indent=2))

def _write_cohort_csv(records: list[RepoRecord], path: Path) -> None:
    cols = ["github_id","student","repo","points","honor_ok","all_failed",
            "commits","spread_days","triage_bucket","doc_present","sources",
            "repo_url","feedback_pr"]
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols); w.writeheader()
        for r in records:
            ag, g = r.autograde, r.git
            doc = next(iter(r.docs.values()), None)
            w.writerow({
                "github_id": r.github_id, "student": r.student, "repo": r.repo,
                "points": ag.points if ag else "", "honor_ok": ag.honor_ok if ag else "",
                "all_failed": ag.all_failed if ag else "",
                "commits": g.commits if g else "", "spread_days": g.spread_days if g else "",
                "triage_bucket": g.triage_bucket if g else "",
                "doc_present": doc.present if doc else "", "sources": doc.sources if doc else "",
                "repo_url": r.links.get("repo",""), "feedback_pr": r.links.get("feedback_pr","")})

def _write_facts_md(records: list[RepoRecord], path: Path, *, lab_name: str, total_points: int) -> None:
    lines = [f"# {lab_name} — Recon Facts (Part A)", "",
             f"Population: **{len(records)}** repos · max **{total_points}** pts", "",
             "> Verified record. Each row is reproducible from the repo + commit.", "",
             "| Student | Auto pts | Honor | Commits | Spread (d) | Triage | Doc | Feedback |",
             "| --- | --: | :-: | --: | --: | :-: | :-: | :-: |"]
    for r in sorted(records, key=lambda x: (x.autograde.points if x.autograde else -1)):
        ag, g = r.autograde, r.git
        doc = next(iter(r.docs.values()), None)
        fb = r.links.get("feedback_pr","")
        lines.append("| {gid} | {pts} | {h} | {c} | {s} | {t} | {d} | {fb} |".format(
            gid=r.github_id, pts=ag.points if ag else "—",
            h="✓" if (ag and ag.honor_ok) else "✗", c=g.commits if g else "—",
            s=g.spread_days if g else "—", t=(g.triage_bucket or "—") if g else "—",
            d="✓" if (doc and doc.present) else "✗",
            fb=f"[PR]({fb})" if fb else "—"))
    path.write_text("\n".join(lines) + "\n")
