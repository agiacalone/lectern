"""Deterministic grading-recommendations engine for the instructor report.

Sorts each student into one of four advisory buckets from recon facts + digest
flags + standing. Advisory only — never writes a score. Each item carries the
evidence that triggered it so the instructor can confirm fast.
"""
from dataclasses import dataclass, field


@dataclass
class Recommendations:
    confirm: list = field(default_factory=list)
    edge_cases: list = field(default_factory=list)
    low_confidence: list = field(default_factory=list)
    upward: list = field(default_factory=list)


LOW_CONF_FLAGS = {"student-comment:needs-review", "digest:invalid",
                  "digest:total-drift", "needs-human-read"}


def _item(r, reason):
    return {"github_id": r["github_id"], "student": r["student"], "reason": reason}


def _near_cut(pct, cuts, band):
    for letter, cut in cuts.items():
        if cut and 0 <= (cut - pct) <= band:
            return letter
    return None


def recommend(cohort, standing, manifest) -> Recommendations:
    rec = Recommendations()
    for r in cohort:
        gid = r["github_id"]
        pct = standing.get(gid)
        flags = set(r.get("writeup_flags") or [])
        if not r.get("honor_ok", True) or r.get("points", 0) == 0:
            rec.edge_cases.append(_item(r, "honor-gate fail / non-submission — late-policy call"))
            continue
        if r.get("triage_bucket") in ("REVIEW", "FLAG"):
            rec.edge_cases.append(_item(r, f"triage {r['triage_bucket']} — review before posting"))
            continue
        if flags & LOW_CONF_FLAGS or any(f.startswith("partial-ward-zeroed") for f in flags):
            hit = sorted(flags & LOW_CONF_FLAGS) or ["partial-ward-zeroed"]
            rec.low_confidence.append(_item(r, f"automated score withheld/suspect: {hit}"))
            continue
        near = _near_cut(pct, manifest.letter_cuts, manifest.bump_band) if pct is not None else None
        if near:
            rec.upward.append(_item(r, f"{pct:.1f}% — within {manifest.bump_band} of {near} cut"))
        rec.confirm.append(_item(r, f"proposed {r.get('proposed')} — routine"))
    return rec
