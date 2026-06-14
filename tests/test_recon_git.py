import subprocess, os
from pathlib import Path
from lectern.recon_git import recon_git, GitRecon

def _mk_repo(tmp_path: Path) -> Path:
    r = tmp_path / "repo"; r.mkdir()
    env = {**os.environ, "GIT_AUTHOR_NAME":"t","GIT_AUTHOR_EMAIL":"t@e",
           "GIT_COMMITTER_NAME":"t","GIT_COMMITTER_EMAIL":"t@e"}
    def git(*a): subprocess.run(["git","-C",str(r),*a], check=True, env=env, capture_output=True)
    git("init","-q","-b","main")
    for i in range(3):
        (r / f"f{i}.py").write_text(f"# work {i}\n")
        git("add","-A"); git("commit","-q","-m",f"step {i}")
    return r

def test_recon_git_counts_commits(tmp_path):
    g = recon_git(_mk_repo(tmp_path))
    assert isinstance(g, GitRecon)
    assert g.commits == 3
    assert g.spread_days >= 0
    assert isinstance(g.notable_messages, list)
    assert len(g.notable_messages) == 3

def test_recon_git_empty_repo_is_safe(tmp_path):
    r = tmp_path / "empty"; r.mkdir()
    subprocess.run(["git","-C",str(r),"init","-q","-b","main"], check=True, capture_output=True)
    g = recon_git(r)
    assert g.commits == 0
