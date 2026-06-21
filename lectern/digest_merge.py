"""merge: validated digest results -> advisory cohort columns. Never writes scores/gradebook."""
from __future__ import annotations
import csv, json
from dataclasses import dataclass, field
from pathlib import Path
from lectern.digest_rubric import Rubric
from lectern.digest_schema import validate_result

@dataclass
class Merged:
    github_id: str
    score: int | None
    comment: str
    flags: list[str] = field(default_factory=list)

def _cleared(bundle_dir: Path, gid: str) -> set[str]:
    jf = bundle_dir / "repos" / f"{gid}.json"
    if not jf.exists():
        return set()
    ag = (json.loads(jf.read_text()).get("autograde") or {})
    return {k for k, c in (ag.get("challenges") or {}).items() if c.get("passed")}

def merge_results(bundle_dir: Path, rubric: Rubric, results_path: Path) -> list[Merged]:
    bundle_dir = Path(bundle_dir)
    out: list[Merged] = []
    for line in Path(results_path).read_text().splitlines():
        if not line.strip():
            continue
        obj = json.loads(line)
        gid = obj.get("github_id", "?")
        errs = validate_result(obj, rubric)
        if errs:
            out.append(Merged(gid, None, "", ["digest:invalid"] + errs[:1]))
            continue
        flags: list[str] = []
        cleared = _cleared(bundle_dir, gid)
        secs = dict(obj["sections"]); bonus = dict(obj.get("bonus") or {})
        for s in rubric.sections:
            if s.requires_cleared and s.requires_cleared not in cleared and secs.get(s.key, 0):
                secs[s.key] = 0; flags.append(f"partial-ward-zeroed:{s.key}")
        for s in rubric.bonus:
            if s.requires_cleared and s.requires_cleared not in cleared and bonus.get(s.key, 0):
                bonus[s.key] = 0; flags.append(f"partial-ward-zeroed:{s.key}")
        total = min(rubric.cap, sum(secs.values()) + sum(bonus.values()))
        if obj.get("total") != total:
            flags.append("digest:total-drift")
        comment = obj["comment"][:rubric.comment_max_chars]
        if obj.get("abstain") or obj.get("confidence") == "low":
            out.append(Merged(gid, None, comment, flags + ["needs-human-read"]))
        else:
            out.append(Merged(gid, total, comment, flags))
    return out

_NEW_COLS = ["writeup_score", "writeup_comment", "writeup_flags"]

def apply_to_cohort(bundle_dir: Path, merged: list[Merged]) -> None:
    path = Path(bundle_dir) / "cohort.csv"
    with path.open(newline="") as fh:
        rows = list(csv.DictReader(fh))
    fields = list(rows[0].keys()) if rows else ["github_id"]
    for c in _NEW_COLS:
        if c not in fields:
            fields.append(c)
    by_id = {m.github_id: m for m in merged}
    for row in rows:
        m = by_id.get(row["github_id"])
        row["writeup_score"] = "" if (m is None or m.score is None) else str(m.score)
        row["writeup_comment"] = m.comment if m else ""
        row["writeup_flags"] = ";".join(m.flags) if m else ""
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader(); w.writerows(rows)
