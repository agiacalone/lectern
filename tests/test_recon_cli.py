import subprocess, os
from pathlib import Path
from lectern.recon import run_recon

def _seed_repo(root: Path, gid: str, with_doc: bool):
    r = root / gid; r.mkdir(parents=True)
    env = {**os.environ, "GIT_AUTHOR_NAME":"t","GIT_AUTHOR_EMAIL":"t@e",
           "GIT_COMMITTER_NAME":"t","GIT_COMMITTER_EMAIL":"t@e"}
    def git(*a): subprocess.run(["git","-C",str(r),*a], check=True, env=env, capture_output=True)
    git("init","-q","-b","main")
    (r / "student").mkdir()
    if with_doc:
        (r/"student"/"WRITEUP.md").write_text("---\nhonor: X\n---\n# G\n## Ward I\nx\n")
    else:
        (r/"student"/".gitkeep").write_text("")  # git won't commit an empty dir
    git("add","-A"); git("commit","-q","-m","work")
    return r

def test_run_recon_end_to_end(tmp_path):
    fix = Path(__file__).parent / "fixtures" / "recon"
    workdir = tmp_path / "clones"; workdir.mkdir()
    _seed_repo(workdir, "ChaoticNerd", True)
    _seed_repo(workdir, "alpha-coder", False)
    def fake_clone(ref, dest): import shutil; shutil.copytree(workdir/ref.github_id, dest)
    def fake_autograde(ref): return None  # no CI in this test
    out = tmp_path / "bundle"
    n = run_recon(manifest_path=fix / "spellbreaker.recon.yaml",
                  roster_csv=fix / "github.csv", out_dir=out,
                  clone=fake_clone, autograde=fake_autograde)
    assert n == 2
    assert (out / "cohort.csv").exists()
    assert (out / "repos" / "ChaoticNerd.json").exists()
    assert (out / "FACTS.md").read_text().count("|") > 10
