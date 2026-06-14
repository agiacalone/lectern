"""Load and validate <lab>.recon.yaml into typed objects."""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
import yaml

@dataclass
class AutogradeSpec:
    workflow: str = "autograde.yml"
    branch: str = "main"               # branch the autograde workflow runs on
    result_path: str = "grading/result.json"   # filename inside the artifact (and legacy in-repo path)
    result_artifact: str = "grading-result"    # CI run-artifact name carrying result.json (durable home)
    steps: list = field(default_factory=list)  # legacy scrape: [{name,key,points,optional?}]

@dataclass
class DocSpec:
    file: str
    label: str
    summarize: bool = False
    points: int = 0

@dataclass
class ReconManifest:
    course: str; section: str; term: str; name: str
    org: str; repo_prefix: str; total_points: int
    classroom_assignment_id: str | None = None
    autograde: AutogradeSpec | None = None
    docs: list[DocSpec] = field(default_factory=list)
    git_profile: str = "short-project"
    triage: str = "surface"

def load_manifest(path: Path) -> ReconManifest:
    data = yaml.safe_load(Path(path).read_text()) or {}
    a = data.get("assignment") or {}
    missing = [req for req in
               ("course", "section", "term", "name", "org", "repo_prefix", "total_points")
               if req not in a]
    if missing:
        raise ValueError(
            "manifest missing required field(s): "
            + ", ".join(f"assignment.{m}" for m in missing))
    ag = data.get("autograde")
    autograde = AutogradeSpec(**{k: ag[k] for k in
                ("workflow","branch","result_path","result_artifact","steps") if k in ag}) if ag else None
    docs = [DocSpec(file=d["file"], label=d["label"],
                    summarize=d.get("summarize", False), points=d.get("points", 0))
            for d in (data.get("docs") or [])]
    return ReconManifest(
        course=a["course"], section=str(a["section"]), term=a["term"], name=a["name"],
        org=a["org"], repo_prefix=a["repo_prefix"], total_points=int(a["total_points"]),
        classroom_assignment_id=a.get("classroom_assignment_id"),
        autograde=autograde, docs=docs,
        git_profile=(data.get("git") or {}).get("profile", "short-project"),
        triage=(data.get("report") or {}).get("triage", "surface"),
    )
