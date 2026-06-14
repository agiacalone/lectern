"""reg-lab-recon — sweep a lab's repo population into a recon bundle (Layer 1)."""
from __future__ import annotations
from pathlib import Path
from typing import Callable
import argparse, tempfile, shutil

from lectern.recon_manifest import load_manifest
from lectern.recon_discover import discover_repos, RepoRef
from lectern.recon_autograde import (fetch_autograde, fetch_autograde_artifact,
                                     scrape_autograde, AutogradeResult)
from lectern.recon_git import recon_git
from lectern.recon_docs import recon_doc
from lectern.recon_links import repo_links
from lectern.recon_record import RepoRecord
from lectern.recon_bundle import write_bundle

def _default_clone(ref: RepoRef, dest: Path, org: str) -> None:
    import subprocess
    subprocess.run(["gh","repo","clone",f"{org}/{ref.repo}",str(dest)],
                   check=True, capture_output=True)

def run_recon(*, manifest_path: Path, roster_csv: Path, out_dir: Path,
              clone: Callable[[RepoRef, Path], None] | None = None,
              autograde: Callable[[RepoRef], AutogradeResult | None] | None = None) -> int:
    m = load_manifest(manifest_path)
    refs = discover_repos(roster_csv, repo_prefix=m.repo_prefix)
    do_clone = clone or (lambda ref, dest: _default_clone(ref, dest, m.org))

    def _default_auto(ref: RepoRef) -> AutogradeResult | None:
        if not m.autograde:
            return None
        # 1. preferred: the durable CI run-artifact contract (result.json)
        r = fetch_autograde_artifact(
            m.org, ref.repo, workflow=m.autograde.workflow, branch=m.autograde.branch,
            artifact=m.autograde.result_artifact, member=m.autograde.result_path)
        # 2. fallback: result.json committed in-repo (labs that publish that way)
        if r is None:
            r = fetch_autograde(m.org, ref.repo, m.autograde.result_path, branch=m.autograde.branch)
        # 3. legacy fallback: parse the run log's PASS/FAIL lines
        if r is None and m.autograde.steps:
            r = scrape_autograde(m.org, ref.repo, m.autograde.workflow, m.autograde.steps,
                                 branch=m.autograde.branch)
        return r

    do_auto = autograde or _default_auto
    doc_path = m.docs[0].file if m.docs else "README.md"
    records: list[RepoRecord] = []
    for ref in refs:
        tmp = Path(tempfile.mkdtemp(prefix="recon-"))
        try:
            try:
                do_clone(ref, tmp / "repo")
                cloned = True
            except Exception:
                cloned = False  # no submission / private-no-access — record as empty
            repo = tmp / "repo"
            if cloned and repo.exists():
                ag = do_auto(ref)
                git = recon_git(repo, profile=m.git_profile)
                docs = {d.label: recon_doc(repo / d.file, label=d.label) for d in m.docs}
            else:
                ag, git, docs = None, None, {d.label: recon_doc(repo / d.file, label=d.label) for d in m.docs}
            commit = ag.commit if ag else None
            links = repo_links(org=m.org, repo=ref.repo, grading_commit=commit, doc_path=doc_path)
            records.append(RepoRecord(github_id=ref.github_id, student=ref.student,
                repo=ref.repo, grading_commit=commit, autograde=ag, git=git, docs=docs, links=links))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    write_bundle(records, out_dir, lab_name=m.name, total_points=m.total_points)
    return len(records)

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="reg-lab-recon",
        description="Sweep a lab's student-repo population into a recon bundle.")
    p.add_argument("--manifest", required=True, type=Path)
    p.add_argument("--roster", required=True, type=Path, help="github.csv roster")
    p.add_argument("--out", required=True, type=Path)
    a = p.parse_args(argv)
    n = run_recon(manifest_path=a.manifest, roster_csv=a.roster, out_dir=a.out)
    print(f"recon: {n} repos → {a.out}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
