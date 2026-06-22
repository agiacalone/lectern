"""Parse + validate a lab report manifest (`<lab>.report.yaml`).

The manifest tells `reg-lab-report` how to render and deliver: the points split
(auto vs writeup), ward labels, letter cuts, repo/org naming, and the feedback
branch + PR conventions. Pure-deterministic; no network.
"""
from dataclasses import dataclass
import yaml


@dataclass
class Ward:
    key: str
    label: str


@dataclass
class ReportManifest:
    course: str
    section: str
    term: str
    lab: str
    org: str
    repo_prefix: str
    auto_max: int
    writeup_max: int
    wards: list
    letter_cuts: dict
    bump_band: float
    feedback_branch: str
    feedback_pr: int
    default_branch: str = "main"


def load_report_manifest(path: str) -> ReportManifest:
    with open(path) as f:
        d = yaml.safe_load(f) or {}
    auto_max = int(d.get("auto_max", 0))
    writeup_max = int(d.get("writeup_max", 0))
    if auto_max < 0 or writeup_max < 0:
        raise ValueError("auto_max/writeup_max must be >= 0")
    wards = [Ward(w["key"], w["label"]) for w in (d.get("wards") or [])]
    return ReportManifest(
        course=d["course"], section=str(d["section"]), term=d["term"],
        lab=d["lab"], org=d["org"], repo_prefix=d["repo_prefix"],
        auto_max=auto_max, writeup_max=writeup_max, wards=wards,
        letter_cuts=d.get("letter_cuts", {}), bump_band=float(d.get("bump_band", 1.0)),
        feedback_branch=d.get("feedback_branch", "feedback"),
        feedback_pr=int(d.get("feedback_pr", 1)),
        default_branch=d.get("default_branch", "main"),
    )
